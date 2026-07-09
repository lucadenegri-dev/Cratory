# Design Brief — Sezione Download unificata

> Prodotto da `/impeccable shape` il 2026-07-09. Confermato dall'utente.
> Precede l'implementazione (`/impeccable craft` o build diretto).
> Critica di partenza: `.impeccable/critique/2026-07-09T09-03-56Z__frontend-app-downloads.md` (22/40).

## Decisioni confermate
- **IA**: una pagina sola. `frontend/app/downloads/issues/page.tsx` viene rimossa; tutto confluisce in `frontend/app/downloads/page.tsx`.
- **Ricerca manuale**: resta in evidenza come blocco di pari livello (cataloga nella playlist virtuale "Soulseek").
- **Revisione file dubbio**: Tieni comunque / Scarta / Sostituisci con… → richiede endpoint backend nuovo.

## 1. Feature Summary
La sezione Download diventa un'unica superficie di lavoro per acquisire file via Soulseek/slskd e sistemare le tracce andate storte. Sostituisce il trittico attuale (home a card + summary card + pagina `/downloads/issues`) con una pagina che segue *acquisisci → monitora → sistema*. Utente: DJ singolo, prep pre-sessione.

## 2. Primary User Action
Sistemare le tracce-problema senza cambiare pagina. La lista canonica "da sistemare" è azionabile inline (scegli file / collega file / tieni dubbio / ignora). L'acquisizione playlist è l'ingresso; la revisione è il cuore ricorrente.

## 3. Design Direction
Invariato dal DS: Restrained/monocromo, dark+paper, squadrato, filetti 1px, monospace, `tnum`. Dark default. Anchor: indice tipografico di un catalogo a stampa; coda trasferimenti di un client; Linear per la densità azionabile delle righe.

## 4. Scope
Intera superficie Download (pagina + revisione modal). Production-ready al build. `/downloads/issues` rimossa.

## 5. Layout Strategy (sezioni hairline, non card impilate)
1. **Barra Acquisizione** (primaria) — select playlist + "Scarica playlist"; se slskd off, alert config + disabilitati.
2. **Striscia Job** (effimera, sessione) — `EqMeter`/barra DS + `processed/total` + label; a fine job collassa in riepilogo che confluisce nel work list. Fonte canonica = work list persistito; job = solo stato live (risolve i due-conteggi).
3. **Work list "Da sistemare"** (cuore) — unica lista persistita. Chip-filtro inline (Tutte/Da rivedere/Non trovate/Fallite) con conteggi + "Riprova tutte". Righe azionabili inline, azioni differenziate per peso (primaria piena, secondarie outline, "Ignora" ghost/defilata, overflow su stretto).
4. **Ricerca manuale** (pari livello, in evidenza) — ricerca libera Soulseek → cataloga in "Soulseek". Etichettata come azione distinta, separata visivamente dal work list.
5. **Empty / offline state** — didattico quando pulito; copre `status` undefined / backend offline (oggi pagina bianca).

## 6. Key States
Idle-con-problemi · Idle-pulito · Acquisizione-in-corso · Job-finito · slskd-non-configurato · Backend-offline · Errore-azione (messaggio leggibile, non `String(e.message)`).

## 7. Interaction Model
Azione primaria per esito:
- `needs_review` con file (durata) → **Rivedi**: atteso vs file scaricato (tag reali, Δ durata, bitrate) → Tieni comunque / Scarta / Sostituisci con…
- `needs_review` confidenza / `not_found` → **Scegli file** (lista candidati).
- Tutte → secondaria **Collega file**, terziaria **Ignora** (conferma).
- Chip-filtro `role="tablist"`; badge-conteggio cliccabili.
- Nav sidebar: contatore "da sistemare" sulla voce "Download".

## 8. Content Requirements
Titoli: Acquisizione / Da sistemare (N) / Ricerca manuale. Chip: Tutte·Da rivedere·Non trovate·Fallite (con count). Revisione: label "atteso" vs "scaricato", Δ come `+10s`/`−8s`. Empty: "Nessun download — scegli una playlist e avvia." Offline: "Backend non raggiungibile." Ranges: 0 / ~5 / 500+ righe → lista densa hairline (paginazione/virtualizzazione se serve).

## 9. Recommended References
`layout.md` (ri-IA, gerarchia flusso, sezioni hairline) · `clarify.md` (terminologia, label ricerca manuale) · `craft.md` (build) · `harden.md` (offline/errore).

## 10. Backend implications
- **"Tieni comunque"**: il path del file dubbio NON è persistito oggi (var locale scartata al bail `needs_review` in `soulseek_download_job.py:127-130`). Serve persistere il candidate path sulla traccia (es. `last_download_path`) o ri-risolverlo per basename nell'inbox `SLSKD_DOWNLOAD_DIR`. Default: persistere il path.
- Nuovi endpoint attesi sotto `/api/downloads`: keep-review (aggancia il file inbox → downloaded), discard-review (elimina il file inbox + azzera esito). Riuso di `attach_local_file`.
- Rimozione route `/downloads/issues`: le azioni review/link/ignore/retry già esistenti restano, si spostano sulla pagina unica.
