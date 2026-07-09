---
target: sezione download (page + issues + modali)
total_score: 22
p0_count: 0
p1_count: 3
timestamp: 2026-07-09T09-03-56Z
slug: frontend-app-downloads
---
## Design Health Score — Sezione Download

| # | Euristica | Punteggio | Problema chiave |
|---|-----------|-------|----------|
| 1 | Visibilità stato sistema | 2 | Job card mostra "3/10" testuale, niente barra di progresso (il DS ha `EqMeter`); due fonti di conteggio (job in-memory vs pending persistito) danno numeri diversi senza spiegazione |
| 2 | Match col mondo reale | 2 | Sovraccarico terminologico: "Da sistemare" / "da rivedere" / "archivio" / "non trovate" per concetti annidati |
| 3 | Controllo e libertà | 3 | Modali chiudibili, "Ignora" con conferma, retry disponibile; ma "Ignora" non è annullabile |
| 4 | Consistenza e standard | 2 | "Scegli file" e "Riprova tutte" duplicati su due superfici; due UI di ricerca Soulseek con semantiche diverse; job progress non usa il pattern del DS |
| 5 | Prevenzione errori | 2 | 409 "download già in corso" emerge solo dopo il click; percorso manuale non validato inline |
| 6 | Riconoscere vs ricordare | 2 | Il conteggio "da rivedere" è in home, ma l'azione per rivederle è due click più in là (→ archivio → filtro → Scegli file) |
| 7 | Flessibilità ed efficienza | 2 | "Riprova tutte" è l'unica bulk action; niente selezione multipla, niente scorciatoie |
| 8 | Estetica e minimalismo | 3 | Monospace pulito, detector clean; ma la home impila card ridondanti (job card + summary card si sovrappongono) |
| 9 | Recupero dagli errori | 2 | Errori mostrati come `String(e.message)` grezzo in un Alert generico "⚠ {error}" |
| 10 | Aiuto e documentazione | 2 | L'alert slskd-non-configurato è ottimo; per il resto niente guida su cosa significhi "rivedere" |
| **Totale** | | **22/40** | **Accettabile (fascia bassa) — servono miglioramenti prima che l'esperienza convinca** |

## Anti-Patterns Verdict

**Detector deterministico**: pulito (`[]`) su tutti e 4 i file. Nessun tell da AI slop (gradient text, side-stripe, eyebrow, ecc.). Il design system editoriale-monocromo è rispettato.

**Valutazione LLM**: il problema non è "sembra fatto dall'AI" — è **strano senza motivo per il compito**. Le tracce-problema vivono in TRE superfici che si sovrappongono (job card live, summary card con soli conteggi, pagina archivio). L'azione "Scegli file" appare e sparisce a seconda che ci sia un job in-memory. Questo è il vero difetto: il tool non sparisce nel compito.

## Overall Impression

La sezione fa cose giuste (persistenza degli esiti, alert di configurazione, tre vie di risoluzione), ma **non racconta un flusso**. La home è uno stack piatto di card di pari peso: azione primaria (scarica playlist), ricerca manuale, conteggi problemi, job live — nessuna gerarchia acquisisci → monitora → sistema. E la domanda dell'utente ("come rivedo le tracce da rivedere?") è il sintomo esatto: la home mostra il *numero* di "da rivedere" ma **nessun modo per agirci lì**.

## What's Working

1. **Persistenza degli esiti** (`last_download_outcome`/`reason` su Track): le tracce-problema sopravvivono a job e riavvii. Architetturalmente corretto.
2. **L'alert slskd** dice esattamente quali env impostare. Documentazione contestuale come si deve.
3. **Tre vie di risoluzione** (Scegli file / Collega file / Ignora) coprono i casi reali: ri-scarica, aggancia file già a disco, archivia.

## Priority Issues

### [P1] "Da rivedere" non è azionabile dove appare
La summary card in home mostra `{count} da rivedere` come badge, ma le uniche azioni lì sono "Riprova tutte" e "Vai all'archivio". Per rivedere davvero: notare il bottone piccolo → andare su `/downloads/issues` → filtrare "Da rivedere" → "Scegli file". Quattro passi per l'operazione centrale.
**Fix**: rendere le righe azionabili in home, o unificare la summary+archivio in un'unica superficie. Il badge-conteggio deve essere un link diretto al filtro corrispondente.
**Comando**: `/impeccable shape`

### [P1] Tre superfici sovrapposte per le tracce-problema
Job card live (`status.items`, in-memory), summary card (`pending`, persistito), pagina archivio (`pending`, persistito). "Scegli file" compare inline nella job card ma sparisce al reload; poi ricompare in un'altra pagina. Due conteggi da fonti diverse confondono.
**Fix**: una sola lista canonica di tracce-problema, persistita, con la job progress come header effimero *sopra* di essa — non come lista concorrente.
**Comando**: `/impeccable shape`

### [P1] "Rivedere" non mostra cosa è stato scaricato
`needs_review` significa "ho scaricato qualcosa ma la durata non torna / confidenza bassa". Ma il modal "Scegli il file" ri-cerca Soulseek da zero, senza mostrare il file già scaricato né un confronto atteso-vs-reale. L'utente non può decidere "tengo quello" — può solo ri-scaricare alla cieca.
**Fix**: nel modal per `needs_review`, mostrare in cima il file scaricato (tag reali, durata, bitrate) accanto all'atteso, con azioni "Tieni questo" / "Sostituisci con…".
**Comando**: `/impeccable craft`

### [P2] La home non ha gerarchia di flusso
`space-y-3` di card di pari peso `p-3`. Azione primaria (scarica) e problemi da sistemare hanno lo stesso peso visivo. Nessun senso di acquisisci → monitora → sistema.
**Fix**: gerarchizzare — azione di acquisizione in alto come blocco primario, stato job come strip, tracce-problema come sezione con divisori hairline (non card annidate).
**Comando**: `/impeccable layout`

### [P2] Tre azioni identiche per riga nell'archivio
"Scegli file", "Collega file", "Ignora" sono tre bottoni outline identici + un badge, che vanno a capo su schermi stretti. Peso visivo pari a un'azione distruttiva-ish ("Ignora" rimuove dall'archivio).
**Fix**: differenziare — azione primaria piena, secondaria outline, "Ignora" ghost/danger e defilata. Considerare un menù overflow per le secondarie.
**Comando**: `/impeccable layout`

## Persona Red Flags

**Alex (power user / il DJ che ci lavora ogni giorno)**: nessuna scorciatoia da tastiera; per sistemare 20 download falliti deve aprire un modal per volta; i badge-conteggio non sono cliccabili come filtro; niente selezione multipla ("scegli file per tutte le needs_review con un solo candidato ovvio"). "Riprova tutte" è l'unica leva bulk ed è cieca.

**Riley (stress tester)**: se il backend è offline al primo load, `status` è undefined → pagina quasi vuota senza empty state (l'empty state richiede `status.total === 0 && available`). Il job in-memory sparisce al reload: se chiudo la tab a metà job, la lista per-traccia con i bottoni "Scegli file" non c'è più, restano solo i conteggi. Gli errori mostrano `String(e.message)` grezzo.

**Jordan (primo utilizzo)**: "Da sistemare" vs "da rivedere" vs "archivio" — quattro parole per concetti annidati, nessuna spiegata. "confidenza X/100" senza legenda. Due ricerche Soulseek (manuale in home, "Scegli file" nel modal) con esiti diversi (una cataloga in una playlist virtuale, l'altra aggancia alla traccia) mai chiarite.

## Minor Observations

- I badge `warning`/`neutral`/`danger` collassano quasi tutti su neutro per la Monochrome Rule: "da rivedere", "non trovate", "fallite" sono quasi indistinguibili a colpo d'occhio (solo "fallite" ha il rosso). Lo scan visivo è di fatto lettura testo.
- L'archivio `/downloads/issues` non ha voce di nav: raggiungibile solo da un bottone. Per un compito ricorrente, un contatore sulla voce "Download" della sidebar sarebbe più scopribile.
- I filtri nell'archivio sono bottoni che si comportano da tab ma non sono `role="tablist"`.
- Job progress usa "3/10" testuale mentre il DS prescrive `EqMeter`/progress bar per i job (DESIGN.md §5).

## Questions to Consider

- E se la home Download fosse una sola lista di lavoro (acquisisci in alto, problemi sotto) invece di quattro card?
- "Rivedere" dovrebbe mostrare cosa ho scaricato prima di offrirmi di ri-scaricare?
- Serve davvero una pagina `/issues` separata, o è un sintomo del fatto che la home non riesce a ospitare le righe azionabili?
