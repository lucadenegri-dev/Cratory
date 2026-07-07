# Product

## Register

product

## Users

Un singolo DJ — utente personale, strumento self-hosted, nessun multi-tenancy. Contesto d'uso: preparazione pre-sessione. L'utente ha una libreria di file audio sul disco (`LIBRARY_ROOT`, fonte di verità del possesso) e usa playlist streaming e tracklist incollate (Spotify o import manuale testo/CSV) come lead. Vuole indicizzare la collezione posseduta, importare BPM/tonalità da Rekordbox, costruire una scaletta, scoprire tracce mancanti e identificarle nei mix esterni, acquisirne i file. L'arricchimento testuale dei metadati (titolo/artista/album/label/genere) e il tagging sul disco sono compiti di DjOrganizer, non di Cratory.

Il job to be done: passare da "ho questi lead streaming e questi file sul disco" a "ho una scaletta pronta con transizioni ragionate, le lacune riempite e i file delle tracce posseduti sul disco".

## Product Purpose

Cratory è un banco di lavoro personale per la preparazione di set DJ. Non è un player, non è un social. È lo spazio dove la libreria prende forma: importazione, normalizzazione, indicizzazione della libreria su disco, import BPM/tonalità da Rekordbox, acquisizione file (Soulseek/slskd) con archivio e revisione dei download, costruzione set, gap analysis, discovery, esplorazione della collezione per etichetta discografica (aggregati deterministici per label, backfill da Spotify), identificazione tracklist da mix.

Il flusso (striscia di orientamento in dashboard, cinque fasi): **Scopri** (playlist/lead) → **Acquisisci** (Soulseek/slskd) → **Organizza⤴** (enrich testuale, tag, organizzazione: in DjOrganizer) → **Analizza⤴** (analisi in Rekordbox, import BPM/key in Cratory) → **Suona** (Set Builder). Le due fasi con ⤴ escono da Cratory verso Rekordbox/DjOrganizer e rientrano con un import. L'indicizzazione della libreria (scan `LIBRARY_ROOT`, il disco è la libreria) non è una fase della striscia: si lancia dal pulsante "Indicizza" nella nav a sinistra (o parte automaticamente all'avvio).

Successo = l'utente entra con playlist grezze ed esce con un set strutturato, annotato, una lista di tracce da aggiungere e i relativi file acquisiti in libreria.

## Brand Personality

Sobria, tipografica, archivistica.

Cratory si legge come un catalogo a stampa di una collezione di dischi: monospace ovunque, griglia a filetti, geometria squadrata, quasi nessun colore. Il crate digging resta un atto creativo — c'è energia nel processo — ma l'energia è resa con densità, peso e gerarchia tipografica, non con il colore. Lo strumento non scompare dietro ai dati né li sovrasta con l'estetica: li compone come un indice tipografico.

Tono: sicuro di sé senza essere arrogante. Preciso senza essere freddo. Non si scusa per essere opinionated. Quieto, non timido.

## Anti-references

- **Consumer music app** (Spotify, Apple Music): troppo morbido, arrotondato, pensato per l'ascolto passivo. Cratory è uno strumento da lavoro, non un jukebox.
- **Generic SaaS dashboard**: card identiche, gradients viola o teal, hero-metric template, layout tutto centrato. Scaffolding AI riconoscibile da lontano.
- **Legacy DJ software** (Traktor, Rekordbox): overloaded di informazioni, griglie dense, UX degli anni 2000. Pesante, non fluidamente navigabile.
- **AI tool hype** (stile "startup AI 2024"): gradients pastello, rounded card enormi, glassmorphism. Da **non** confondere col tema **paper** di Cratory, che è cream deliberato — carta calda con inchiostro quasi nero, filetti a 1px e geometria squadrata, non pastelli né gradient.

## Design Principles

Il sistema visivo completo (token, temi dark/paper, componenti) vive in [DESIGN.md](DESIGN.md).

1. **Dati prima, narrativa dopo.** I numeri (BPM, Camelot, energia) sono il linguaggio. Mostrarli con precisione e densità calibrata. Il layer creativo (AI, narrativa set) avvolge i dati senza sostituirli.

2. **Ogni schermata spinge avanti.** L'utente ha un obiettivo — costruire un set. La nav raggruppa le stazioni in tre macro-fasi, Scopri (Playlist, Discovery, Shazam, Etichette) → Colleziona (Libreria, Download) → Suona (Set builder, Set), non sezioni indipendenti. Il percorso è sempre visibile: la dashboard apre con una pipeline strip a cinque fasi — Scopri → Acquisisci → Organizza⤴ → Analizza⤴ → Suona — che dice a che punto del ciclo sei e qual è il prossimo passo (l'indicizzazione della libreria è un pulsante nella nav, non una fase della striscia).

3. **Denso ma respirabile.** Una libreria DJ è dati densi. L'interfaccia li gestisce senza collassare in un foglio di calcolo. Spaziatura deliberata, gerarchia visiva chiara, raggruppamento semantico.

4. **Opinionated, non decorativo.** Ogni scelta visiva deve sembrare fatta per questo strumento — non presa in prestito da un design system generico. Il linguaggio è monocromo: un solo rosso per errori e azioni distruttive, gerarchia data da peso, maiuscolo, tracking e cifre tabulari (`tnum`), non dal colore.

5. **Energia sperimentale.** La discovery deve sentirsi come scavare in casse di dischi. Il set builder come composizione, non come compilare un form. La texture dell'interfaccia riflette l'atto creativo che supporta.

## Accessibility & Inclusion

WCAG AA sul contrasto del testo (rapporto ≥ 4.5:1 per body text, ≥ 3:1 per large text). Nessun requisito specifico oltre al contrasto — strumento personale, utente singolo. Animazioni gestibili via `prefers-reduced-motion` dove implementate.
