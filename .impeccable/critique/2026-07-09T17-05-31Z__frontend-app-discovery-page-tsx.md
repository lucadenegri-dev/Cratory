---
target: sezione Discovery (frontend/app/discovery/page.tsx)
total_score: 23
p0_count: 0
p1_count: 2
timestamp: 2026-07-09T17-05-31Z
slug: frontend-app-discovery-page-tsx
---
# Critique — Sezione Discovery (frontend/app/discovery/page.tsx)

Nota metodo: Assessment A eseguita inline dal loop principale (subagent terminato per limite di spesa); Assessment B (detector) completata prima da agente isolato con esito zero findings — rischio anchoring nullo. Nessuna ispezione browser (dev server non attivo); review su sorgente + design system.

## Design Health Score

| # | Euristica | Score | Issue chiave |
|---|-----------|-------|--------------|
| 1 | Visibilità stato sistema | 2 | "Scaricato" dopo il pick significa solo "accodato" (page.tsx:361,416); l'esito reale (needs_review/not_found/failed) non è mai visibile qui |
| 2 | Match sistema/mondo reale | 2 | Il lead è una RELEASE Discogs presentata come traccia (page.tsx:381; discovery_dig.py:171): il modello mentale "disco" è tradito dalla riga-traccia |
| 3 | Controllo e libertà | 2 | "Salva" senza undo; il pick crea una traccia in libreria come effetto collaterale non dichiarato (page.tsx:359); nessun cancel del DIG in corso |
| 4 | Consistenza e standard | 3 | Design system rispettato con rigore (rounded-none, hairline, chips, monocromo); pattern coerenti col resto dell'app |
| 5 | Prevenzione errori | 2 | Nulla impedisce di cercare un EP come file singolo; duration_seconds mai passata a downloadCandidates (page.tsx:347) → il discriminatore più forte del ranking resta spento |
| 6 | Riconoscimento vs ricordo | 3 | Chips, datalist, reason badge ottimi; manca memoria "già visto/scartato" tra i dig |
| 7 | Flessibilità ed efficienza | 2 | No bulk-save, no tastiera, no stato del dig nell'URL (non bookmarkabile), no filtri/ordinamenti sui risultati |
| 8 | Estetica e minimalismo | 3 | Pagina pulita e on-brand; ma 80 lead in lista piatta senza raggruppamento né gerarchia interna |
| 9 | Recupero da errori | 2 | "Nessun candidato trovato su Soulseek" è un vicolo cieco (page.tsx:423); 409 "download già in corso" arriva come errore grezzo nel modal |
| 10 | Aiuto e documentazione | 2 | Tooltip preset e placeholder sì; nessuna guida di pagina (il Set Builder ce l'ha) |
| **Totale** | | **23/40** | **Acceptable** |

## Verdetto anti-pattern
Non sembra AI-generated: niente card grid identiche, niente gradient, monocromo disciplinato, reason badge con dati veri (have/want). Detector deterministico: 0 findings su page.tsx e su ui.tsx/page-layout.tsx/jobs-provider.tsx (verificato con controllo positivo). Il problema della pagina non è estetico: è semantico (release vs traccia) e di fine-flusso.

## Carico cognitivo
Falliti 3/8: chunking dei risultati (80 righe piatte), memoria di lavoro (devi ricordare quali lead hai già verificato su Discogs), scelte minime (riga form: input+10 chips+3 preset+select gusto+DIG in un colpo solo). Moderato.

## Percorso emotivo
Il picco (trovare la gemma, reason "raro & richiesto 3/120") è ben servito. La fine del viaggio è la valle: modal tecnico di file, "Nessun candidato" senza uscita, successo etichettato male. Peak-end violato: la sessione si chiude nell'incertezza.

## Punti di forza
1. Reason badge deterministici composti dalla UI (reasonLabel, page.tsx:30-47): trasparenza del "perché" rara in questo genere di feature.
2. Preset Familiare/Bilanciato/Avventuroso al posto dello slider grezzo (page.tsx:52-56): progressive disclosure corretta di adventurousness.
3. Empty state che insegnano il prossimo passo (page.tsx:263-267) e integrazione jobs strip per il DIG.

## Issue prioritarie
- **[P1] Release spacciata per traccia.** Riga identica a una traccia, nessun badge formato (12"/EP/LP), download che si aspetta un file singolo. Fix: dichiarare il lead come disco + step tracklist alla azione (vedi opzioni dischi). Comando: /impeccable shape.
- **[P1] Fine-flusso download disonesto.** Pick = salva in libreria (non dichiarato) + "Scaricato" quando è solo accodato, esito mai riportato qui. Fix: "Accodato" + link a Download, dichiarare il salvataggio. Comando: /impeccable clarify + harden.
- **[P2] Sessione senza memoria.** Risultati persi alla navigazione, nessun seen/dismissed, re-dig identico (stessa pagina Discogs da 100). Fix: stato in URL + memoria lead scartati. Comando: /impeccable harden.
- **[P2] 80 lead piatti.** Nessun raggruppamento (label/anno/stile), score invisibile. Fix: filtri rapidi o raggruppamento per etichetta. Comando: /impeccable layout.
- **[P2] Vicolo cieco Soulseek vuoto.** Fix: fallback a ricerca manuale prefilled / tracklist del disco. Comando: /impeccable harden.

## Red flag personas
**Alex (power user):** nessuna scorciatoia; verifica di ogni lead = tab Discogs (80 tab potenziali); niente bulk-save; il dig non è bookmarkabile né ripetibile con offset. Abbandona dopo due sessioni.
**Riley (stress tester):** artista con " - " nel nome spezzato male da partition (discovery_dig.py:171); secondo download con job attivo → 409 grezzo nel modal; "Scaricato" ma il job può fallire dopo; refresh a metà sessione = tutto perso.

## Osservazioni minori
- "DIG" urlato in inglese in un'interfaccia tutta italiana.
- Tooltip preset solo via title nativo (scopribilità bassa).
- Thumb 48px: per il "discorso dischi" la copertina è il segnale primario e meriterebbe più peso.
- Link Spotify costruito con titolo release: la ricerca funziona per caso, non per progetto.

## Domande da considerare
- Se la Discovery deve sembrare "scavare in casse di dischi", perché il risultato è una lista e non una cassa (griglia di copertine sfogliabile)?
- Un lead È un disco: e se "Salva" salvasse il disco (wishlist-dischi con tracklist) invece di una traccia finta?
- Come dovrebbe *sentirsi* il momento dell'acquisizione, ora che è la valle emotiva del flusso?
