---
target: set-builder
total_score: 29
p0_count: 0
p1_count: 2
timestamp: 2026-06-18T17-45-15Z
slug: frontend-app-set-builder-page-tsx
---
# Critique — Set Builder (`frontend/app/set-builder/page.tsx`)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Loading con fase + secondi + "di solito 1–2 min", progress, badge AI/algoritmico. Manca validazione inline. |
| 2 | Match System / Real World | 3 | Linguaggio DJ naturale (Arco, Peak time, Camelot, mix sicuri). Solido. |
| 3 | User Control and Freedom | 3 | Campi liberi, preset non distruttivi. Nessun reset form, nessun annulla generazione. |
| 4 | Consistency and Standards | 4 | Vocabolario condiviso (Field/Section/Badge) uniforme. Mapping colori transizioni coerente. |
| 5 | Error Prevention | 2 | duration/bpm accettano valori assurdi (0, range invertiti). Nessun pre-flight se la libreria non ha BPM/key. |
| 6 | Recognition Rather Than Recall | 3 | Hint inline su strategia/preset/mode. Relazione preset↔arc-field non spiegata. |
| 7 | Flexibility and Efficiency | 3 | Preset ottimi acceleratori. Nessun Cmd+Enter, nessun "rigenera". |
| 8 | Aesthetic and Minimalist Design | 3 | Pulito e on-brand, ma ~13 input tutti insieme: wall of options al primo accesso. |
| 9 | Error Recovery | 2 | `String(e.message)` grezzo nell'alert, nessuna guida al recupero, empty-state nascosto in errore. |
| 10 | Help and Documentation | 3 | Hint inline adeguati per tool mono-utente. |
| **Total** | | **29/40** | **Good** |

## Anti-Patterns Verdict

**LLM assessment**: NON sembra AI-generated. Studio scuro coerente, lime usato come segnale (un solo primary button, stati attivi), badge semantici, label uppercase legittime (form labels, non eyebrow decorativi). Sezionamento deliberato. Legge come uno strumento, non come uno scaffold.

**Deterministic scan**: `detect.mjs` → `[]`, exit 0. Zero violazioni. Concorda con la review.

## Overall Impression
Una superficie densa ma ben costruita e on-brand. Il motore è chiaramente pensato. I problemi non sono estetici — sono di **robustezza e adattamento**: si rompe su mobile, gestisce male gli errori, e non previene input insensati. La più grande opportunità: rendere il form resiliente (mobile + errori + validazione) senza toccarne l'estetica, che funziona.

## What's Working
1. **Coerenza col design system** (4/4): riusa Field/Section/Badge/Button senza one-off. Il mapping transizioni→colore è coerente con tutta l'app.
2. **Preset come scaffolding**: Warm-up/Peak time/Progressivo/Closing trasformano una decisione complessa (riempire 6 campi) in un tap. Ottima gestione del carico intrinseco.
3. **Feedback di generazione**: fase + secondi trascorsi + "di solito 1–2 min" è esattamente la rassicurazione giusta in un'attesa lunga.

## Priority Issues

- **[P1] Lo shell non collassa su mobile**: a 375px la sidebar resta `w-60` (240px) e schiaccia il form in ~135px — label spezzate parola-per-parola, select tagliato a "Tu", preset in overflow. Il set-builder, denso di form, è il punto dove esplode. Il fix vive nell'app-shell (`layout.tsx` + `sidebar.tsx`): sidebar collassabile/drawer sotto un breakpoint. **Fix**: sidebar off-canvas con trigger sotto `lg`, main a piena larghezza. **Comando**: `/impeccable adapt`.
- **[P1] Error recovery grezzo**: in errore mostra `String(e.message)` nudo (es. "Failed to fetch") senza linguaggio piano né via di recupero, e l'empty-state sparisce (`!error` lo nasconde) lasciando solo l'alert rosso. **Fix**: messaggi in italiano per i casi comuni (backend giù, libreria senza BPM, AI non configurata), bottone "Riprova", mantieni i parametri. **Comando**: `/impeccable harden`.
- **[P2] Error prevention assente sui numerici**: `duration` accetta 0/negativi, BPM accetta range invertiti (da 200 a 50) senza alcun segnale. Nessun pre-flight se la libreria non ha tracce con BPM/key (fallisce solo dopo il submit). **Fix**: min/clamp su duration, warning su range BPM invertito, stato disabilitato+spiegazione se la sorgente non ha tracce mixabili. **Comando**: `/impeccable harden`.
- **[P2] Nessun annulla per la generazione async**: la generazione AI dura 1–2 min, il bottone si limita a disabilitarsi. L'utente è in trappola finché non finisce o fallisce. **Fix**: bottone "Annulla" che ferma il polling e resetta lo stato. **Comando**: `/impeccable harden`.
- **[P2] Carico cognitivo al primo accesso**: ~13 input su 4 sezioni tutti visibili. Un first-timer affronta un muro prima della prima generazione. Disclosure solo parziale (lo Stile AI compare condizionatamente). **Fix**: guida col flusso preset-first; valuta di collassare "Vincoli" e "Mood" dietro un "Opzioni avanzate". **Comando**: `/impeccable distill`.

## Persona Red Flags

**Casey (Mobile)**: Apre Cratory dal telefono in console/cabina → sidebar fissa mangia 2/3 dello schermo, form illeggibile. Il primary "Genera" è raggiungibile solo dopo scroll lungo, fuori dalla thumb zone. Abbandona subito.

**Jordan (First-Timer)**: 13 campi senza un percorso ovvio. Non capisce che i "Preset rapidi" sovrascrivono BPM/Energia/Strategia (nessun feedback). Se la generazione fallisce, vede "Failed to fetch" e non sa cosa fare.

**Alex (Power User)**: Nessun Cmd+Enter per generare. Dopo un risultato deve risalire tutto il form per modificare un parametro e rigenerare. Generazione non annullabile: se sbaglia un parametro deve aspettare 1–2 min.

**Il DJ (project persona)**: Vuole iterare velocemente — generare, valutare le transizioni, ritoccare un vincolo, rigenerare. Il loop "scorri-su, cambia, scorri-giù" rompe il flusso creativo che PRODUCT.md mette al centro.

## Minor Observations
- Preset e dropdown "Strategia" impostano entrambi la strategia ma sono scollegati visivamente: applicare un preset cambia la Strategia senza che il campo "si accenda". (P3)
- `· {model}` accanto a "Usa l'AI Set Agent" è in `text-faint` su sfondo card — metadata glanceable, accettabile, ma è l'unico residuo faint vicino a un controllo.
- Energia ha `min/max` ma non c'è clamp reale: si può digitare 250.

## Questions to Consider
- Cosa succederebbe se il flusso fosse **preset-first**: scegli un preset, generi, e solo dopo affini i vincoli sul risultato?
- Il set-builder deve davvero mostrare tutti i 13 campi prima della prima generazione, o "Arco + Vincoli" sono raffinazioni post-prima-bozza?
- Una versione "confident" gestirebbe l'attesa AI in modo annullabile e mostrerebbe cosa sta facendo l'agente, non solo "Generazione…"?
