# RatingDiamond: livelli in popup flottante

Data: 2026-08-07 · Stato: approvata

## Obiettivo

L'espansione inline del voto (i 3 rombi compaiono nel flusso della riga accanto
al toggle) sposta gli elementi vicini e in righe strette ne nasconde alcuni.
I livelli devono comparire in un **overlay flottante** che non occupa spazio
nel layout.

## Design

- `frontend/components/rating-diamond.tsx` (unico file toccato, + test):
  il contenitore diventa `relative`; i 3 livelli, quando `open`, vengono resi
  in un pannello **`absolute`** ancorato al toggle — sopra (`bottom-full`),
  allineato a destra (`right-0`, il rombo sta sul bordo destro delle righe:
  così il popup non esce dal viewport) — con lo stile dei menu esistenti
  (`z-20 border border-border bg-elevated shadow-lg`, cfr.
  `add-to-playlist-menu.tsx:85`, più `rounded` e padding compatto).
- Interazione invariata: click assegna, ri-click sullo stesso livello toglie,
  click fuori/Esc chiude, update ottimistico con rollback. Nessuna modifica
  ad API, tipi o i18n. Nel player docked (basso-destra) "sopra" funziona già.
- Test (`frontend/tests/rating-diamond.test.tsx`): i casi esistenti restano
  validi; nuova asserzione che il pannello dei livelli è posizionato
  `absolute` (fuori dal flusso), a pinnare la regressione.

## Fuori scope

- Aggiungere il rombo alla vista griglia della Library (minor già deferito).
- Flip automatico del popup quando manca spazio sopra (YAGNI: i mount attuali
  hanno sempre spazio sopra o sono in fondo allo schermo).
