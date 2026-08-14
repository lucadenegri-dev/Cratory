# Riconoscimento mix piu' robusto (Shazam) — design

Data: 2026-07-19. Stato: approvato.

## Problema

L'identificazione dei mix (`services/mix_identify.py` + `integrations/shazam.py`)
sbaglia spesso, per quattro cause strutturali:

1. **Tracce fantasma.** Un singolo match di Shazam su un segmento di 12s diventa
   una voce in tracklist, con confidence fissa 80. Un segmento campionato a meta'
   transizione (due brani sovrapposti, EQ, pitch) produce spesso un match
   sbagliato, che entra dritto in tracklist.
2. **Doppioni attorno ai buchi.** In `dedup_consecutive` un segmento non
   riconosciuto azzera `last_key`: la stessa traccia campionata prima e dopo un
   buco compare due volte.
3. **Griglia fissa, nessun retry.** Un segmento fallito non viene mai ritentato
   a un offset vicino; sui mix lunghi il passo adattivo sale (2h → ~72s) e ogni
   traccia ha solo 2-3 campioni.
4. **Confidence non informativa.** 80 fisso per tutti i match: l'utente non sa
   di quali voci fidarsi.

## Obiettivo

Meno tracce fantasma e doppioni, confidence che riflette le conferme reali, e
una UI che marca le voci dubbie. Tutto nel cuore puro di `mix_identify.py`,
testabile con recognizer finto (zero rete nei test).

## Design

### 1. Retry sui buchi

Nella passata principale, se `recognize_at(offset)` restituisce None (nessun
match) o solleva `RecognizerError`, si ritenta **una volta** a `offset + delta`,
con `delta = clamp(step // 2, 6, 20)` secondi (`step` = distanza tra gli offset
pianificati). Il retry attinge al budget extra (vedi §6). Un errore vale come
buco ai fini del retry; il contatore `MAX_CONSECUTIVE_ERRORS` si azzera a ogni
riconoscimento riuscito, anche se avvenuto sul retry.

### 2. Raggruppamento con conteggio dei hit

I campioni consecutivi con la stessa chiave (`_match_key`: ISRC, altrimenti
artista+titolo normalizzati) diventano una voce con `hits` = numero di campioni
concordi. `start_offset_seconds` resta l'offset del primo campione della serie.

### 3. Dedup con finestra sui buchi

La stessa chiave che ricompare dopo **soli buchi, fino a 2 consecutivi**, si
fonde con la voce precedente (i suoi hit si sommano). Con 3+ buchi di fila o
un'altra traccia in mezzo e' una voce nuova (il DJ l'ha rimessa davvero).
I buchi si contano sugli **offset pianificati**: un offset il cui retry
fallisce vale un solo buco.

### 4. Conferma dei match singoli

Dopo la passata principale, ogni voce con `hits == 1` riceve un campione di
conferma a `offset + 4s` (se `offset + 4 + SEGMENT_LENGTH` supera la durata:
`offset - 4`, con minimo 0). Stessa chiave → la voce e' confermata (`hits = 2`).
Chiave diversa o buco → la voce resta in tracklist come **dubbia** (scelta di
prodotto: non si scarta, si segnala).

### 5. Confidence reale

`hits >= 2` → confidence **90**; `hits == 1` non confermata → confidence **45**.
Sparisce l'80 fisso in `parse_shazam` (la confidence diventa un derivato del
conteggio, calcolata in `mix_identify`, non un campo del parse). I set gia'
analizzati restano a 80 nel DB e non cambiano aspetto.

### 6. Budget chiamate extra

Retry sui buchi e conferme attingono a un budget di **50 chiamate extra** per
mix, consumato in ordine: prima i retry (passata principale), poi le conferme.
A budget esaurito niente piu' retry/conferme: i buchi restano buchi, i singoli
restano dubbi. Tetto totale: 100 pianificate + 50 extra = 150 chiamate
(endpoint shazamio non ufficiale: non va martellato).

### 7. Progresso

La passata principale continua a chiamare `on_progress(i, totale)` sul numero di
offset pianificati; le conferme estendono il totale (`pianificati + conferme da
fare`) e proseguono il conteggio. Nessuna modifica a `mix_identify_job`.

### 8. UI: badge "dubbia"

Nella pagina del set (`frontend/app/shazam/[id]/page.tsx`) le voci con
`confidence < 60` mostrano un badge "Dubbia" / "Uncertain" (i18n in
`lib/i18n/it.ts` / `en.ts`), coerente con i badge esistenti del design system.
Nessuna modifica a DB, API o schema: `confidence` esiste gia' su `DjSetTrack` e
nel serializer.

## Fuori scope

- **Retry pitch-compensato** (ricampionare i buchi persistenti a ±5% via ffmpeg
  per compensare il pitch fader del DJ): eventuale seguito, si misura prima la
  resa di queste migliorie.
- Raffinamento degli offset di inizio traccia (ricerca binaria dei confini).

## Test

Unit puri su `mix_identify` con recognizer finto:

- retry sul buco: buco al primo colpo, match sul retry → la traccia c'e', un
  solo consumo di budget;
- errore → retry come per il buco; azzeramento errori consecutivi su retry
  riuscito;
- conferma: singolo confermato → confidence 90; non confermato → 45, resta in
  lista;
- finestra di dedup: stessa chiave dopo 1-2 buchi → una voce sola (hit sommati);
  dopo 3 buchi o un'altra traccia → due voci;
- budget: a budget 0 niente retry ne' conferme; ordine di consumo
  (retry prima delle conferme);
- `plan_offsets` e comportamento esistente invariati dove non toccati
  (aggiornare `test_mix_identify.py` dove il collasso secco cambia).

Frontend: unit sul rendering del badge sotto/sopra la soglia 60.
