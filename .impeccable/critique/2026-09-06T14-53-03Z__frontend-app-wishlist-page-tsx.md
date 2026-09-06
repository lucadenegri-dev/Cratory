---
target: pagina wishlist
total_score: 25
p0_count: 0
p1_count: 2
timestamp: 2026-09-06T14-53-03Z
slug: frontend-app-wishlist-page-tsx
---
# Critique: pagina Wishlist (frontend/app/wishlist/page.tsx)

Dati live: 40 tracce, 34 "non trovata", 6 "in review", 0 "mai tentata", 0 "fallita".

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Una traccia accodata resta "non trovata / Riprova": l'unico feedback è un Alert transitorio "Accodata." |
| 2 | Match System / Real World | 2 | "confidenza sotto soglia per l'auto-pick" (testo backend, italiano in UI inglese, gergo) ripetuto su 6 righe; "Mai tentate" / "In review" / "Rivedi" = tre parole per lo stesso concetto |
| 3 | User Control and Freedom | 3 | Archivia con conferma, Ripristina, Azzera esito: bene |
| 4 | Consistency and Standards | 3 | Grammatica del sistema rispettata; nav dice "Coda", la pagina dice "Download" |
| 5 | Error Prevention | 3 | Gate su slskd, dedup lato backend |
| 6 | Recognition Rather Than Recall | 3 | Stato in colonna, provenienza in riga |
| 7 | Flexibility and Efficiency | 2 | Nessun "seleziona tutte", nessuna tastiera; 40 click per selezionare la lista |
| 8 | Aesthetic and Minimalist Design | 2 | 34 bottoni primari identici; tre vie per la stessa azione; due tab a zero; hint di aiuto in uno slot permanente |
| 9 | Error Recovery | 3 | Motivi dei fallimenti mappati in lingua piana |
| 10 | Help and Documentation | 2 | Solo l'hint "Riserva: se slskd non risponde…" |
| **Total** | | **25/40** | **Acceptable** |

## Anti-Patterns Verdict
- LLM: nessun tell da AI. Monospace, filetti, stato tipografico, un menu per riga: coerente con DESIGN.md. Il difetto è di architettura delle azioni, non di stile.
- Detector (`detect.mjs`) sui 3 file: 0 rilievi.
- Overlay browser: non tentato (nessuna iniezione), quindi nessun overlay [Human] disponibile. Evidenza raccolta con screenshot e page text.

## What's Working
- Stato come colonna tipografica (`fg-strong` / `muted` / `danger`), non badge: la lista non urla.
- Un solo menu per riga con la sezione "Compra" sotto filetto.
- Filtri persistiti nell'URL + back-link verso dettaglio traccia/playlist; potatura della selezione a ogni ricarica.
- Tre empty state distinti (vuota / filtrata / archiviate).

## Priority Issues
- [P1] Tre vie per una sola azione: "Riprova/Scarica" su ogni riga, checkbox + "Accoda N tracce", "Riprova tutte" in marginalia. 34 bottoni primari identici contraddicono "the single loudest action on a screen". Fix: un'unica barra di lotto sempre presente con "seleziona tutte" in testa lista; azione di riga demotata (ghost/icona) o rimossa; "Riprova tutte" sparisce (= seleziona tutte + Accoda). /impeccable distill
- [P1] Nessuno stato "in coda" sulla riga: `wishlistStatus` deriva solo da `last_download_outcome`. Dopo l'accodamento la riga è identica a prima. Fix: incrociare lo snapshot della coda (jobs-provider) e mostrare "in coda" in colonna stato, bottone disattivato. /impeccable harden
- [P2] Tab con conteggio zero ("Mai tentate 0", "Fallite 0") occupano spazio; "Tutte 40" è il default. Fix: nascondere gli stati assenti o passare a un elenco di stati presenti. /impeccable distill
- [P2] Motivo "confidenza sotto soglia per l'auto-pick": testo backend non tradotto, gergo, ripetuto identico su tutte le righe in review. Fix: mappare nel dizionario frontend (pattern servicesMeta) o eliminarlo, visto che "in review" lo dice già; tenere il motivo solo per "fallita". /impeccable clarify
- [P2] Marginalia "Azioni di gruppo": "Collega tutte" è manutenzione, "Apri slskd" è una riserva con hint di due righe in uno slot permanente. Fix: "Apri slskd" come link testuale in fondo senza hint; "Collega tutte" resta ma sotto un titolo suo. /impeccable distill

## Persona Red Flags
- Alex (power user): 40 checkbox singole, nessun seleziona-tutte, nessuna scorciatoia. Preme "Riprova tutte" e non vede cambiare nulla sulle righe.
- Jordan (prima volta): "Mai tentate", "auto-pick", "In review", "Rivedi": cosa fa "Rivedi"? Differenza fra "Riprova" di riga e "Riprova tutte"?

## Minor Observations
- Sotto `lg` ogni riga diventa due righe: stato + bottone a tutta larghezza dominano il titolo.
- Chiave nav `downloads` etichettata "Wishlist"; pagina Coda titolata "Download".
- Il `MAX_CHIPS=2` con `+N` è ok: nei dati reali solo 2 tracce su 40 hanno più di una playlist.

## Questions to Consider
- La wishlist è una lista di cose da fare o una coda da lanciare? Se è la seconda, la selezione è l'interazione primaria e l'azione di riga è secondaria.
- Serve davvero il filtro per stato, o basta ordinare per stato (review in cima) con i conteggi nel meta del titolo?
- Se la riga mostrasse "in coda", la pagina Coda servirebbe ancora come voce di nav separata?
