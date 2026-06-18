# Product

## Register

product

## Users

Un singolo DJ — utente personale, strumento self-hosted, nessun multi-tenancy. Contesto d'uso: preparazione pre-sessione. L'utente ha una libreria di playlist Spotify, vuole analizzarla, arricchirla con dati di mixing (BPM, tonalità Camelot, mood, energia), costruire una scaletta, scoprire tracce mancanti, e identificare cosa stava suonando in un mix esterno.

Il job to be done: passare da "ho queste playlist Spotify" a "ho una scaletta pronta con transizioni ragionate e le lacune riempite".

## Product Purpose

SetArc è un banco di lavoro personale per la preparazione di set DJ. Non è un player, non è un social. È lo spazio dove la libreria prende forma: importazione, normalizzazione, enrichment deterministico, costruzione set, gap analysis, discovery, identificazione tracklist da mix.

Successo = l'utente entra con playlist grezze ed esce con un set strutturato, annotato, e una lista di tracce da aggiungere.

## Brand Personality

Fluida, creativa, sperimentale.

Lo strumento non deve scomparire dietro ai dati né sovrastarli con estetica. Deve trasmettere che il crate digging è un atto creativo — c'è energia nel processo. L'interfaccia va con il flusso del DJ: navigare la libreria, scoprire connessioni, costruire una storia musicale.

Tono: sicuro di sé senza essere arrogante. Preciso senza essere freddo. Non si scusa per essere opinionated.

## Anti-references

- **Consumer music app** (Spotify, Apple Music): troppo morbido, arrotondato, pensato per l'ascolto passivo. SetArc è uno strumento da lavoro, non un jukebox.
- **Generic SaaS dashboard**: card identiche, gradients viola o teal, hero-metric template, layout tutto centrato. Scaffolding AI riconoscibile da lontano.
- **Legacy DJ software** (Traktor, Rekordbox): overloaded di informazioni, griglie dense, UX degli anni 2000. Pesante, non fluidamente navigabile.
- **AI tool hype** (Notion-like, cream backgrounds, pastel gradients): stile "startup AI 2024" con rounded cards enormi e palette pastello. Tutto quello che il commento in globals.css già rifiuta.

## Design Principles

1. **Dati prima, narrativa dopo.** I numeri (BPM, Camelot, energia) sono il linguaggio. Mostrarli con precisione e densità calibrata. Il layer creativo (AI, narrativa set) avvolge i dati senza sostituirli.

2. **Ogni schermata spinge avanti.** L'utente ha un obiettivo — costruire un set. Dashboard, libreria, discovery e set builder sono stazioni del flusso, non sezioni indipendenti. Il percorso deve sempre essere visibile.

3. **Denso ma respirabile.** Una libreria DJ è dati densi. L'interfaccia li gestisce senza collassare in un foglio di calcolo. Spaziatura deliberata, gerarchia visiva chiara, raggruppamento semantico.

4. **Opinionated, non decorativo.** Ogni scelta visiva deve sembrare fatta per questo strumento — non presa in prestito da un design system generico. L'accento lime è la luce dello studio.

5. **Energia sperimentale.** La discovery deve sentirsi come scavare in casse di dischi. Il set builder come composizione, non come compilare un form. La texture dell'interfaccia riflette l'atto creativo che supporta.

## Accessibility & Inclusion

WCAG AA sul contrasto del testo (rapporto ≥ 4.5:1 per body text, ≥ 3:1 per large text). Nessun requisito specifico oltre al contrasto — strumento personale, utente singolo. Animazioni gestibili via `prefers-reduced-motion` dove implementate.
