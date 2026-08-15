# Ricerca Soulseek integrata (wishlist, sotto-progetto A)

Data: 2026-08-15. Stato: approvata a voce, in attesa di revisione scritta.

## Problema

Il flusso di acquisizione dalla wishlist spinge l'utente fuori dall'app: la
ricerca automatica ha meno recall di una ricerca manuale (esito `not_found` per
tracce che su Soulseek esistono), l'auto-pick finisce spesso in `needs_review` e
il modal di revisione è più scomodo della web UI di slskd, il job è lento e
opaco. Risultato: "faccio prima a cercare a mano in Soulseek".

Questo sotto-progetto attacca il sintomo principale: portare la ricerca manuale
Soulseek dentro Cratory, per traccia. Fuori scope (sotto-progetti successivi):
coda vera dei download (B), riga wishlist più ricca + storia dei tentativi (C),
fix del recall della cascata auto-pick (informato dai dati di C).

## Decisioni chiave

- Un componente nuovo, **`SoulseekSearchModal`**, sostituisce `DownloadReviewModal`
  e diventa l'unico posto dove si lavora una traccia su Soulseek.
- La ricerca manuale mostra i **risultati grezzi** di slskd, senza filtro a
  soglia: il ranking esistente guida ordinamento e badge, non esclude nulla.
- La **cascata di varianti resta esclusiva dell'auto-pick**; la ricerca manuale
  esegue la query letterale dell'utente. Le varianti diventano suggerimenti
  cliccabili nella UI.
- Il download del file scelto riusa `POST /api/downloads/track` (guard durata
  saltato: scelta esplicita dell'utente). Vincolo un-download-alla-volta
  invariato: la UI disabilita con motivo visibile.

## UX e flusso

Punti d'ingresso del modal:

- riga wishlist: il bottone primario per `review` apre il nuovo modal;
  `downloaded_unlinked` mantiene «Collega file» come primaria (il file è già su
  disco); per tutti gli stati il menù `…` offre "Cerca su Soulseek";
- dettaglio traccia: stessa azione dove oggi c'è la revisione.

Dentro il modal, dall'alto in basso:

1. **Blocco file dubbio** (solo se esiste un `needs_review` per durata):
   l'attuale Tieni/Scarta, invariato (`/api/downloads/review/{id}`,
   `keep-review`, `discard-review`).
2. **Campo query** precompilato con `artista titolo`, modificabile; Cerca con
   bottone o invio. Sotto, suggerimenti cliccabili: le varianti che l'auto-pick
   avrebbe provato (titolo pulito, primo artista, solo artista), calcolate dal
   backend — un click compila il campo e rilancia la ricerca.
3. **Risultati grezzi**, tabella scrollabile: nome file (path abbreviato ma
   leggibile), formato, bitrate, durata con **delta rispetto all'attesa**
   (verde ±3s, rosso >20s), dimensione, utente con slot libero/coda. Ordinati
   per score; badge di confidenza sui candidati che l'auto-pick avrebbe
   accettato. All'apertura parte subito la ricerca con la query precompilata.
4. **Azione per riga**: "Scarica questo" → `POST /api/downloads/track`. Con un
   job in corso i bottoni sono disabilitati col motivo visibile.

Il blocco "Soulseek / Apri slskd" in cima alla pagina wishlist scende in fondo
come riga di riserva discreta (serve quando il daemon è irraggiungibile).

## Backend e API

Endpoint nuovo: **`POST /api/downloads/search`**, body `{ query, track_id? }`.

- Una sola ricerca slskd con la query letterale, budget di attesa pieno (~15s,
  come il job in background, non i 5s ridotti di `/candidates`). Niente
  streaming: slskd popola le risposte solo a ricerca conclusa.
- Con `track_id`: carica la traccia e arricchisce i risultati con
  `rank_candidates(min_name_score=0.0)` usando artista/titolo/durata attesa —
  score e confidenza per ordinamento e badge, nessuna esclusione.
- Risposta: per ogni file i campi grezzi (`username, filename, size, bitrate,
  length, format, has_free_slot, queue_length, upload_speed`) più
  `score`/`confidence` quando c'è contesto traccia; in testa alla risposta le
  `query_variants` calcolate (fonte unica: `soulseek_select.query_variants`).
- Errori: `409 slskd_not_configured`; `502 slskd_error` (messaggio con invito
  ad aprire la web UI); `404 track_not_found`. Zero risultati non è un errore:
  lista vuota, empty state con suggerimento di provare una variante più corta.

Riuso senza modifiche di logica: `rank_candidates` e `query_variants` sono già
pubbliche e parametrizzabili; `POST /api/downloads/track`, review/keep/discard
invariati. `/api/downloads/candidates` resta (lo usa Discovery); il nuovo modal
non lo usa — se a fine lavoro risulta orfano ovunque, va segnalato, non rimosso
in questo sotto-progetto.

## Componenti frontend

- **`frontend/components/soulseek-search-modal.tsx`** (nuovo): target
  `{ track_id, artist, title }`, pattern wrapper+`key` per rigenerarsi a ogni
  traccia (come l'attuale review modal). Stato: query, risultati, loading,
  errore. All'apertura: fetch del blocco revisione (solo se serve) + ricerca
  automatica. Tabella risultati scrollabile in `Modal size="lg"`.
- **`lib/api`**: `soulseekSearch(query, trackId?)` con tipo
  `SoulseekSearchResult`.
- **`wishlist-row.tsx`**: `review` apre il nuovo modal come primaria;
  `downloaded_unlinked` mantiene «Collega file» come primaria; voce "Cerca su
  Soulseek" nel menù `…` per tutti gli stati.
- **`wishlist/page.tsx`**: monta il nuovo modal al posto di
  `DownloadReviewModal`; blocco "Apri slskd" spostato in fondo.
- **`tracks/[id]/page.tsx`**: stessa azione al posto della revisione attuale.
- **i18n**: chiavi nuove in `it.ts` e `en.ts` (entrambe le lingue).
- **`DownloadReviewModal` eliminato** quando tutti i punti d'ingresso puntano
  al nuovo componente: niente doppioni che sopravvivono.

## Test (TDD: prima i test, poi l'implementazione)

- **Backend** (pytest, client slskd finto): query letterale passata tal quale
  (nessuna cascata); arricchimento score con e senza `track_id`; nessun filtro
  a soglia (un file con nome pessimo deve comparire nei risultati);
  `query_variants` nella risposta; 409/404/502.
- **Frontend** (vitest, pattern `wishlist-row.test.tsx`): ricerca automatica
  all'apertura; i suggerimenti compilano il campo e ricercano; "Scarica questo"
  chiama `downloadTrack` col candidato giusto; disabilitazione con job in corso.
- **E2e** (`wishlist.spec.ts`): apri il modal da una riga, risultati mockati
  visibili, scegli un file, il job parte.

## Criteri di successo

- Una traccia `not_found` dall'auto-pick si trova e si scarica senza mai aprire
  la web UI di slskd.
- La revisione di un file dubbio e la ricerca di un'alternativa avvengono nello
  stesso pannello.
- Nessuna regressione su auto-pick, review Tieni/Scarta, download da Discovery.
