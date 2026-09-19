# PROGRESS

Cratory is a personal, local/self-hosted, single-user web app to import streaming
playlists, build DJ set drafts on owned tracks, analyze library gaps, discover new
music by taste, and identify mix tracklists via Shazam. It is not a DJ deck and does
not keep third-party audio, aside from the narrow acquisition/preview exceptions
described in `CLAUDE.md`.

## Current state by area

- **Set manuale, tappa 1 (2026-09-18).** Un DJ prepara un set a mano da una playlist:
  "Prepara un set" da `/set-builder` e da `/playlists/detail?id=…` crea un
  `Setlist` `kind="manual"` e apre `/sets/manual?id=…` (tre pannelli — materiale,
  percorso, dettaglio — sopra il player esistente). Il materiale è la playlist di
  origine letta aggiornata più le tracce già nel set più, con una ricerca, la
  libreria. Si inseriscono tracce o un varco, si sposta una riga, si toglie, si
  scrive un appunto libero per riga; ogni mutazione porta `expected_revision` e un
  409 `set_revision_conflict` vuol dire ricaricare. La lista `/sets` instrada per
  `kind` (badge "a mano") e il dettaglio classico rifiuta un set manuale con 409
  `set_is_manual`. Cosa non c'è ancora, di proposito: alternative/riserve/confronto,
  sequenze multiple/banco/undo, note di coppia/stato "provato"/`play_bpm`/pitch,
  durata pianificata, export dedicato, "riempi il varco" — tappe 2-6 del piano in
  `docs/superpowers/plans/2026-09-17-set-manuale-tappa-1.md`.

- **Set manuale, tappa 2 (2026-09-19).** Su una riga il DJ tiene delle candidate e
  ne sceglie una: lo scambio porta l'attiva fra le alternative, così cambiare idea
  non perde nulla, e su un varco la scelta lo trasforma in traccia mantenendone id e
  appunto. Un confronto affiancato da due a quattro mostra BPM, tonalità e durata con
  "sconosciuto" dove il dato manca, e ascolta solo le tracce in confronto. La riserva
  — le tracce da parte per la serata — è fatta di righe senza blocco, non entra nel
  conteggio né nella durata del set, e ha un filtro "da parte" nel materiale; una
  traccia può stare in riserva e nel percorso insieme, il vincolo di unicità vale
  dentro il percorso. `SetlistAlternative` è l'unica tabella nuova; il ciclo di vita
  la conosce (lead orfani, tracce non referenziate, fusione di doppioni con
  deduplica, pulizia dati). Cosa non c'è ancora: sequenze nominate e banco, annulla e
  ripeti, note di coppia e stato "provato", `play_bpm`, durata pianificata, export
  dedicato, "riempi il varco" — tappe 3-6, piano in
  `docs/superpowers/plans/2026-09-19-set-manuale-tappa-2.md`.

- **Set manuale, tappa 3 (2026-09-19).** Il percorso si divide in sequenze: si
  spuntano due o più righe contigue e si raggruppano, con un nome; la sequenza si
  rinomina, si sposta intera (l'ordine interno non si tocca mai), si separa, o si
  parcheggia sul **banco** — fuori dal percorso, senza entrare nel conteggio né nella
  durata. Le frecce di una riga muovono dentro la sua sequenza e ai suoi estremi sono
  spente: per attraversare un confine si sposta la sequenza. **Annulla e ripeti**
  (pulsanti in cima, `cmd/ctrl+z` e `cmd/ctrl+shift+z`, disattivati dentro un campo
  di testo, dove comanda l'annulla del browser) coprono la struttura: dopo ogni gesto
  una `SetlistRevision` salva una fotografia di blocchi, righe e alternative con i
  loro id, e ripristinarla rimette esattamente quelle righe — una riga annullata torna
  con lo stesso id. Le ultime 50; gli edit consecutivi dello stesso appunto si
  accorpano in una revisione sola, ogni altro gesto resta la sua; la prima modifica
  dopo un annulla chiude il ripeti. `Setlist.revision` cresce sempre, annulla
  compreso, ed è solo il controllo di concorrenza: il cursore dell'annulla è
  `undo_seq`, interno, perché un campo solo per entrambi lascerebbe un client fermo a
  un numero già visto credersi aggiornato su uno stato che non esiste più. Cosa non
  c'è ancora: note di coppia e stato "provato", `play_bpm` e percentuale di pitch,
  durata pianificata, export dedicato, "riempi il varco" — tappe 4-6, piano in
  `docs/superpowers/plans/2026-09-19-set-manuale-tappa-3.md`.

- **Set manuale, tappa 4 (2026-09-19).** Selezionata una riga, il dettaglio mostra
  i due passaggi che la riguardano — quello in entrata e quello in uscita — con i
  due tempi, il **pitch che serve in percentuale firmata** (`124 → 123 · −0,8 %`,
  non la differenza secca: a 90 e a 170 lo stesso salto non è lo stesso gesto), le
  due tonalità e un appunto libero. Dove manca un dato si legge «sconosciuto» e non
  compare nessun punteggio: il neutro di `score_transition` sembrerebbe un giudizio
  e non lo è. Un varco aperto spezza la coppia; il confine fra due sequenze no. Il
  campo **«la suono a»** (`play_bpm`) dice il tempo di cabina di quella riga in quel
  set: i vicini si valutano su quel valore e `Track.bpm` in libreria non si tocca
  mai. L'appunto è legato alle due **tracce**, non alle due righe (`SetlistPairNote`,
  terna unica): sostituisci B con C e A→C è da valutare, ma l'appunto su A→B resta e
  torna quando torna B — e il ciclo di vita lo sa, quindi la pulizia non cancella
  più un lead solo perché è uscito dal percorso. La PATCH di riga è diventata
  parziale: un campo non mandato non è un campo da azzerare. Lo stato «da provare /
  provato» della spec **non è stato fatto**, per decisione dell'utente: senza
  «provato» il flag non si chiude mai. Cosa non c'è ancora: durata pianificata ed
  export dedicati, «riempi il varco» — tappe 5-6, piano in
  `docs/superpowers/plans/2026-09-19-set-manuale-tappa-4.md`.

- **Set manuale, tappa 5 e «riempi il varco» (2026-09-19).** Il set dice quanto
  dura: la somma del **percorso risolto** (sequenze principali in ordine, sole
  righe con traccia), con «Quanto la tengo» per riga che vince sulla durata del
  file. Quando il totale è parziale lo dichiara e dice perché — quante tracce senza
  durata, quanti varchi aperti — invece di spacciare una somma incompleta per un
  dato. L'**export** non è più riservato ai set generati: testo, CSV, Markdown e
  M3U8 leggono il percorso risolto, più due formati nuovi, la **scheda di
  preparazione** (sequenze, appunti, alternative, varchi, pitch di ogni passaggio)
  e le **riserve**. Una traccia senza file esce dall'M3U8, che punta ai file, ma
  resta nella scheda segnata «non disponibile»: è una decisione presa, e
  nasconderla sarebbe una bugia. L'anteprima è la risposta stessa dell'endpoint,
  non una seconda resa lato client, quindi non può divergere dal file scaricato.
  **«Riempi il varco»**: il generatore propone N tracce fra le due ai lati del
  varco — lo stesso beam search del set builder, che ora sa fermarsi a conteggio e
  non solo a tempo, con il pool preso dal materiale meno ciò che è già nel
  percorso. Le proposte entrano come righe normali e tutto il riempimento è **una
  sola revisione**: un annulla riapre il varco com'era. Nessuna AI, e c'è un test
  che monkeypatcha l'intera curatela per dimostrare che nessuno la chiama. Cosa
  non c'è ancora: la rimozione del vecchio form di generazione e della curatela
  AI, separata apposta in un cantiere suo. Piano in
  `docs/superpowers/plans/2026-09-19-set-manuale-tappa-5-6a.md`.

- **Via il vecchio generatore e la curatela AI (2026-09-19).** Cratory non genera
  più set interi e non chiama più l'AI per curarli. Spariti: il form di
  `/set-builder` e la sua guida, il job di generazione con i due endpoint,
  `ai_curation.py`, `alternatives.py`, `candidate_engine.py`, `generate_set` con
  scheletro e ancoraggi, l'editor classico per posizione, la pagina di dettaglio
  dei set generati e le colonne `curation`, `mood_tags`, `ai_reason`.
  **Sopravvive il beam search**, che non è un residuo: è il motore di «riempi il
  varco» e, con lo scoring, della pagina Transizioni e della compatibilità dei
  passaggi. `SetGenerationRequest` è diventato `BeamParams` dentro
  `set_generator.py`: senza endpoint non era più il corpo di nessuna richiesta, e
  stare fra gli schemi HTTP diceva una bugia. `/set-builder` è un
  reindirizzamento verso `/sets`, che ora ha «Prepara un set». La suite backend
  scende da 2622 a 2464 test: 158 se ne vanno col codice che esercitavano, e
  restano quelli del beam e dell'export.

  **Se hai ancora un set generato in archivio:** compare in `/sets` marcato
  «vecchio formato», si può esportare e cancellare, e non ha una pagina dove
  aprirsi. Le tre colonne le toglie `_migrate_drop_curation_cols` al primo
  avvio; i set non si toccano. Piano in
  `docs/superpowers/plans/2026-09-19-rimozione-generatore-e-curatela.md`.

- **Origini multiple e set che nasce quando serve (2026-09-19).** Un set può
  pescare da più playlist insieme: l'elenco sta nel pannello del materiale e si
  cambia mentre si lavora. Le playlist si leggono aggiornate come sempre, nel
  loro ordine e senza ripetere una traccia che sta in due; togliere un'origine
  toglie le sue tracce dal materiale ma **non dal percorso**, perché una traccia
  già scelta è una decisione presa. L'annulla non rimette un'origine tolta: lo
  snapshot copre la struttura del percorso, non la provenienza del materiale.

  **«Prepara un set» non salva più niente.** Il banco apre una bozza; il set
  nasce alla prima traccia (o varco, o riserva) che ci metti, e in quel momento
  l'URL prende il suo id. Se chiudi prima, non resta niente. **Un set che svuoti
  dopo resta dov'è**: sono due cose diverse, e cancellartelo sarebbe perdere
  dati, non fare pulizia — la pulizia automatica resta limitata ai vecchi set
  generati. Questo rovescia la riga «un set a mano può essere vuoto» della spec,
  per decisione dell'utente.

  Chi aggiorna non perde niente: `_migrate_setlist_sources` travasa la vecchia
  `source_playlist_id` nella tabella nuova al primo avvio, e la colonna resta
  finché il travaso non avrà girato ovunque. Piano in
  `docs/superpowers/plans/2026-09-19-origini-multiple-e-bozza.md`.

- **Impostazioni in cinque sezioni (2026-09-15).** Generali · Libreria · Download ·
  Collegamenti · Backup, scelte da `?section=` con i pannelli montati e nascosti,
  così una bozza non salvata sopravvive al cambio sezione e ogni form di cartelle
  scrive solo i propri campi. Le chiavi dei servizi si aprono con «Gestisci» e la
  guida al collegamento è ripiegata; i testi sono stati riscritti per l'utente
  (niente nomi di variabili d'ambiente). Dalla review: la riga Soulseek senza URL
  dice «Da configurare», le note del backend sui campi validi e il badge «override
  .env» restano visibili, i link interni puntano alla sezione giusta, il bottone
  Collega Spotify è un `<a>` nudo e non un `next/link` (niente prefetch dell'OAuth).

- **Backup e ripristino (2026-09-13).** I dati che il disco non ricostruisce — voti,
  wishlist, set, playlist, cover, credenziali — stanno in un solo zip, salvato con
  nome da Impostazioni o su richiesta prima di un aggiornamento. Il ripristino non
  tocca mai il DB vivo: valida, mostra il riepilogo, e al riavvio scambia i file
  prima che chiunque li apra, conservando i precedenti in `pre-restore/`.

- **Dig ridisegnato (2026-09-06).** La barra scava per più semi insieme (unione,
  fino a quattro, budget di 300 item diviso fra loro), con i semi come chip e una
  tavolozza dei generi in libreria; i simili si raggiungono anche da lì, con una
  ricerca traccia. Discogs si spegne dalle impostazioni. I simili non collassano
  più a due lead: il cap per artista del dig si applicava all'arco artista, che è
  un artista solo per costruzione — misurato, due su dieci — e i conteggi degli
  archi ora descrivono i lead resi.

- **Discovery "Simili" (2026-09-06).** Dal dettaglio di una traccia posseduta si
  arriva ai suoi parenti su Bandcamp: stessa discografia, stessa etichetta, e con un
  interruttore lo stesso stile nel periodo. Riusa dedup, gusto e griglia del dig; gli
  archi non percorsi dicono perché invece di mostrare uno zero.

- **Wishlist: la riga dice se è in coda, e la lista si sfoltisce** (2026-09-06):
  una traccia accodata restava «non trovata / Riprova», identica a prima del
  click, perché lo stato veniva solo da `last_download_outcome` (l'ultimo esito,
  non il presente). Ora `load()` legge anche lo snapshot di
  `/api/downloads/queue` — riletto subito dopo ogni accodamento, senza un poller
  in più — e la riga in attesa o in corso mostra «in coda» con azione e checkbox
  spente. Tre semplificazioni dalla critique della pagina: le tab di stato a
  conteggio zero non compaiono (resta la tab attiva, per poterla lasciare);
  «Riprova tutte» esce dalla marginalia, sostituito da «seleziona tutte» in
  testa lista che rispetta i filtri e dice quante ne accoda; il motivo dei
  `needs_review` («confidenza sotto soglia per l'auto-pick», frase fissa del
  backend in italiano gergale) è riscritto nei dizionari come i codici dei
  fallimenti, con la durata in m:ss. Via anche l'intestazione «Azioni di
  gruppo» e la nota di due righe su slskd: «Apri slskd» è un link ghost.
  «In coda» è anche una tab: la coda prevale sull'ultimo esito in un solo
  punto (`rowTab`), usato sia dal conteggio delle tab sia dal filtro della
  lista, così una traccia riaccodata esce dalla tab del suo vecchio esito
  invece di comparire in due posti. La colonna destra si intitola «Filtri»
  (prima «Stato», che nominava solo il primo blocco) e l'elenco degli stati ha
  la sua etichetta: era in cima alla colonna e si leggeva come una legenda di
  conteggi, non come il filtro che è. Accanto alla provenienza compare la data
  di primo import (`added_at`, assente su circa metà delle tracce: lì si omette
  invece di stampare un trattino) e un select ordina per quella data, lato
  client come i filtri, con le tracce senza data in fondo in entrambi i versi.

- **L'analisi BPM/key riparte da sola a fine Apply** (2026-09-06): applicare un
  piano Organize lascia tracce possedute senza BPM né key, e finora toccava
  ricordarsi di aprire `/analysis` e premere Avvia. Ora la catena ha tre anelli:
  `apply (con operazioni applicate) → scan → analisi con scope "missing"`.
  L'analisi sta **dopo** la scansione, non a fine apply, perché `apply_plan`
  sposta e rinomina i file senza riscrivere `AudioFile.path` né
  `Track.local_path`: è la scansione a riallinearli, e analizzare prima
  passerebbe a Essentia percorsi morti valorizzando comunque `analyzed_at`, cioè
  mascherando il buco invece di riempirlo. L'innesco vive in un ref del
  `JobsProvider`, si arma solo se la scansione post-apply è stata accettata e si
  consuma al primo esito della scansione, così una scansione manuale non lo
  eredita mai. I valori entrano nei canonici solo via `auto_apply_missing`, che
  riempie i campi vuoti con provenienza `cratory`: la gerarchia
  `manual > rekordbox > cratory` resta intatta.

- **I comandi massivi di Issues agiscono su ciò che vedi** (2026-09-04): la barra
  aveva quattro bottoni per tipo o gravità globali, nessuno che ignorasse la
  lista intera, e "accetta i fixabili" saltava in silenzio ogni valore digitato a
  mano — la bozza viveva nello stato della singola riga, e il backend accettava
  solo issue con un suggerimento già salvato. Ora le bozze salgono alla pagina, i
  tre comandi (alta confidenza, accetta visibili, ignora visibili) lavorano per
  id espliciti sulle issue aperte mostrate dai filtri correnti — con i filtri
  azzerati è l'intera lista — e un `POST /bulk-fix` accetta in blocco i valori
  a mano, anche da "accetta gruppo"; "ignora visibili" chiede conferma col
  conteggio delle proposte pagate. Il salto dei gruppi al click su ✓ era
  l'ordinamento sul conteggio delle sole righe filtrate (aperte): ogni accetta
  toglieva una riga e due gruppi vicini si scavalcavano. Il rango ora si calcola
  sul totale di tutte le issue, che un cambio di stato non muove.
- **DJ GOODGIRL, un easter egg sul frontespizio** (2026-09-04): con l'username
  SoundCloud `xgiorgix` la Home cambia persona — la scritta che si risolve dal
  rumore dice DJ GOODGIRL, la DJ dietro la consolle è una ragazza riccia
  (`()()`, `/(oo)\`, scollo a V) e un terzo del pulviscolo che sale con la
  musica è fatto di cuori nel rosso della cassa. Tutto frontend, tutto a
  prop con default: `AsciiWordmark` prende `word`/`title` (alfabeto esteso a
  D J G I L e spazio), `AsciiDj` prende `figure`, `AsciiAtmosphere` prende
  `hearts`; la decisione sta in `lib/persona.ts`. La scritta aspetta la
  risposta di `/api/soundcloud/status` prima di montarsi, così l'ingresso si
  risolve direttamente nella parola giusta. Spec in
  `docs/superpowers/specs/2026-09-04-dj-goodgirl-easter-egg-design.md`.
- **Il 401 di slskd su installazione fresca** (2026-09-03): il percorso guidato
  scriveva nello `slskd.yml` account, porta e cartella, e nessuna chiave API. Il
  demone partiva per davvero — `/health` è il suo unico endpoint anonimo, ed era
  l'unico che Cratory guardasse per dirlo raggiungibile — cosí il primo errore
  arrivava tre passi dopo, al click su Connetti: un 401 su `PUT /api/v0/server`.
  In sviluppo non si vedeva perché la chiave era stata scritta a mano mesi prima,
  ed è la ragione per cui il buco è sopravvissuto a tutte le prove. Adesso
  `write_config` genera (o riusa, senza mai riscriverla) la voce
  `web.authentication.api_keys.cratory` e la specchia in `slskd_api_key` ad ogni
  salvataggio. Per chi è già bloccato — demone acceso, fase "configura" non piú
  offerta — `GET /api/slskd/status` distingue "ci rifiuta" da "è spento"
  (`unauthorized`), e `POST /api/slskd/daemon/api-key` scrive la chiave e riavvia
  il demone senza richiedere la password Soulseek, che entra e non esce.
- **L'aggiornamento in-place non chiede niente** (2026-08-26, verificato da
  1.0.4 a 1.0.5): l'app ha scaricato, si è riavviata ed è tornata senza il
  dialogo *"Cratory" Not Opened*. Era la domanda che ha motivato l'intero
  lavoro sull'updater, e per due giorni i documenti si sono rifiutati di
  rispondere: il dialogo segue l'attributo di quarantena che un browser attacca
  a ciò che scarichi, e un bundle sostituito dall'app non passa da nessun
  browser. Il giro in Privacy e sicurezza resta solo per la prima
  installazione.
- **slskd è un servizio, non un componente** (2026-08-24): è uscito dal probe
  del wizard, dove restano solo `ffmpeg` e `fpcalc`, e una riga sola copre
  l'intero percorso (scarica, configura, avvia, collega), montata sia dal
  wizard sia da Impostazioni. Le due interfacce precedenti non erano duplicati
  ma due metà — il wizard sapeva installare e configurare, Impostazioni
  collegare e gestire — ed è il motivo per cui la seconda rimandava alla prima.
  Nel bundle il passo dei prerequisiti non si monta affatto: ffmpeg e fpcalc
  viaggiano dentro l'app e non c'è niente da chiedere.
- **The updater that stopped the app from starting** (2026-08-24, released as
  1.0.4): 1.0.3 was published and pulled within the hour because it never
  opened. `tauri-plugin-updater` brought reqwest with rustls and no crypto
  provider, Cargo unified the features, and the shell's own HTTP client — which
  only talks to `127.0.0.1:8000` — began panicking on construction, killing the
  thread that starts the backend. Live process, invisible window, no log at all,
  since the panic preceded the logger. Fixed with `native-tls`; guarded by a
  Rust test that builds that client, and by `pubblica.py`, which now opens the
  bundle and asks it its version before publishing. The real failure was the
  verification: all suites green, none of them opening the app.
- **An updater that updates** (2026-08-23): the app downloads, verifies and
  installs a new version itself, instead of only announcing one.
  `tauri-plugin-updater` reads a `latest.json` published beside the release,
  and the sequence lives in Rust (`src-tauri/src/aggiornamento.rs`) rather than
  in the page, because of an ordering constraint the page must not be able to
  get wrong: the Python backend runs from *inside* the bundle being replaced,
  so it is terminated between the download and the install — which is why
  `download` and `install` are called separately and the documented
  `download_and_install` shortcut is not used. Error codes are the **phase**
  (`permessi`, `controllo`, `scaricamento`, `installazione`), not a guessed
  cause: the plugin's error variants are not a stable contract, the phase is.
  `permessi` is decided before anything is downloaded, via
  `libc::access(W_OK)` on the folder holding the bundle. A provider mounted
  once checks at startup and lights a dot beside Settings; downloading and
  installing sit behind a confirmation that says what it costs (~172 MB, the
  app restarts, running jobs die). Publishing gained a second script,
  `pubblica.py`, separate from `assembla.py` on purpose. **Not yet verified end
  to end**: whether an in-place update also escapes the *"Cratory" Not Opened*
  dialog is the open question, and it needs two real bundles to answer.
- **What the bundle got wrong** (2026-08-23, released as 1.0.2): two visible
  failures in the packaged app, one root — the page is served from
  `tauri://localhost` while everything it touches is somewhere else, which
  `npm run dev` can never show, since there the Next proxy makes the backend
  same-origin and a browser opens `target="_blank"` by itself. The Home
  spectrum was still flat despite 1.0.1 saying otherwise: that fix declared
  `crossOrigin="anonymous"` but `attachAnalyser` bails out before touching the
  element when the source is not same-origin, so it was never reached, and its
  test was a grep over the source — green for the wrong reason. The predicate
  is now "is this ours?" (the page **or** the backend), decided once in
  `frontend/lib/api/base.ts`; `crossOrigin` became conditional as a
  consequence, because the same element plays the dig's previews and
  Bandcamp's host grants no CORS permission, so demanding one silences it.
  Every external link did nothing at all: the webview drops `target="_blank"`
  unless the app registers a new-window handler, and Tauri registers none — a
  single capture-phase listener mounted by the root layout now hands external
  http(s) URLs to `tauri-plugin-opener`. Verified in the release artifact
  itself, mounted from the `.dmg`, not only in a development build. The
  install instructions were wrong too, in the README and in all three
  published releases: macOS says *"Cratory" Not Opened*, not "damaged", and
  the Privacy & Security approval does not survive into the next version —
  it is tied to a signature that ad-hoc signing changes with every build.
- **Release** (2026-08-22): the desktop bundle is shareable. `LICENSE` is the
  AGPL-3.0 (a consequence of shipping Essentia, not a preference), the build
  target is explicitly `dmg`, and the README explains up front that another Mac
  will refuse the first launch (*"Cratory" Not Opened* — Apple could not verify
  it is free of malware) because it is un-notarized, with the exact steps
  through System Settings. No Apple signature and **no auto-updater**: the
  Settings button reports a newer version, installing it is manual. Last of
  four sub-projects toward a Tauri desktop build.
- **Desktop shell** (2026-08-22): `src-tauri/` is a Tauri v2 shell that starts
  the backend as a child process, waits for `/api/setup/state`, then shows
  the window (hidden until then, reloaded once the backend answers so a
  one-shot fetch made during startup doesn't strand the page showing a dead
  backend). The backend runs from a relocatable CPython 3.11 bundled inside
  the app (~195 MB pruned) rather than a frozen binary, because
  `essentia_engine.py`'s subprocess spawn needs `sys.executable -m`, which a
  frozen binary's `sys.executable` doesn't accept. `python3
  src-tauri/scripts/assembla.py` builds `Cratory.app` end to end — frontend
  export, that runtime, ffmpeg relocated from Homebrew (no upstream ships a
  checksummed arm64 build), fpcalc/slskd read from the existing
  `binary_manifest`, ad-hoc signed. Port 8000 stays fixed, never scanned,
  because Spotify's redirect URI is registered on it. The three environment
  seams (`CRATORY_DATA_DIR`/`CRATORY_BIN_DIR`/`CRATORY_VERSION`) needed no
  backend change — the first two sub-projects had already prepared them —
  but the backend was not otherwise untouched: `main.py`'s CORS middleware
  unions in the webview's fixed origin (`tauri://localhost`), and the five
  call sites that actually invoke ffmpeg/ffprobe/fpcalc
  (`integrations/local_files.py`, `services/mix_identify.py`,
  `organize/integrations/integrity.py`, `organize/integrations/acoustid.py`)
  now resolve the binary through `system_probe.resolve_binary` instead of a
  bare name on `PATH` — they used to disagree with the availability probes,
  which already used that seam, so the setup wizard could report every
  component present while the operations that used them broke on a
  Finder-launched app inheriting launchd's minimal `PATH`. Verified against
  a real library: essentia analyzing a real file, the relocated ffmpeg
  decoding a real FLAC, data
  under `~/Library/Application Support/com.cratory.app/` and nothing inside
  the bundle, no orphan process after the window closes. **Not yet
  distributable**: ad-hoc signing only, no Apple notarization, no `LICENSE`,
  no updater, and the `.dmg` produced alongside it is a build side effect,
  not a release artifact — that's the fourth and last sub-project. Step
  three of four toward a Tauri desktop build.
- **Frontend without the Next proxy** (2026-08-22): `CRATORY_STATIC_EXPORT=1`
  builds a static frontend with no `rewrites()`; one shared base URL feeds both
  HTTP clients; the five detail routes read their id from the query string
  instead of the path. Unset, `npm run dev` behaves exactly as before. Step two
  of four toward a Tauri desktop build.
- **Bundle-ready** (2026-08-22): the backend runs entirely from a read-only code
  directory. `CRATORY_DATA_DIR` — same seam shape as `CRATORY_BIN_DIR` and
  `CRATORY_VERSION` — redirects database, logs, caches, managed binaries,
  slskd's own config/downloads/pid/log files and `.env`; unset, nothing
  changes. Step one of four toward a Tauri desktop build.
- **Version and updates** (2026-08-22): the app has a single version (`VERSION` at
  the repository root, `CRATORY_VERSION` overriding it for a packaged build) shown
  in Settings, with a button that compares it against the latest GitHub release.
  Three outcomes kept apart — up to date, update available, could-not-check — and
  the comparison is numeric, so `0.10.0` correctly beats `0.9.0`. Nothing is
  downloaded yet: that arrives with the packaged build, off the same releases.
- **Library**: ownership comes from indexing `LIBRARY_ROOT` on disk (`has_local_file`,
  re-linked by `audio_hash`); streaming playlists (Spotify, SoundCloud) are leads.
  Owned tracks show the physical file's effective tags (genre/album/label/year,
  resolved from the primary file) and are playable read-only, one at a time, through
  the shared bottom player bar (custom transport with seek, prev/next over the
  originating list, auto-advance on owned tracks, OS Media Session).
- **Set Builder**: a deterministic two-phase generator (skeleton first, then beam
  search per segment) always builds the tracklist from owned tracks only; an optional
  AI curation stage judges mood-fit and suggests anchors, never sequences.
- **Discovery**: the "Dig" searches Discogs or Bandcamp by genre/label (taste ranks
  inside a demand-sorted window), with Spotify only as an identity resolver; leads can
  be previewed (iTunes clip / YouTube / Bandcamp stream, ephemeral) before acquisition.
- **Organize** (`/organize`, ex Sortory): the single writer of textual tags — scan,
  issue detection, plan/apply with undo, dedup, provider enrichment
  (MusicBrainz/AcoustID, Discogs, cover art).
- **Analysis**: BPM/key have two deterministic sources, Rekordbox XML import
  (primary) and in-app Essentia analysis (alternative), each with explicit
  provenance (`bpm_source`/`key_source`); `energy` is derived.
- **Shazam**: mix tracklist identification (phase 1) building a corpus of identified
  tracklists; co-occurrence suggestions are backlog.
- **Downloads/Wishlist**: every non-owned track with its download outcome, playlist
  provenance and buy links; acquisition via Soulseek (slskd) or a per-track
  SoundCloud/yt-dlp download links a file back to the existing track. A per-track
  manual Soulseek search (raw slskd results, no variant cascade, no confidence
  filter) lives in a single modal reachable from the wishlist row and the track
  detail page, replacing the old review-only modal. Acquisition runs on a
  persistent SQLite queue, not a single in-memory job: a worker pool
  (`download_slots`, default 3, adjustable in Settings) downloads several tracks
  at once, a circuit breaker pauses and later resumes slskd-dependent work on its
  own if the daemon goes unreachable, and the queue survives a backend restart. Its
  own page, `/downloads`, replaces the redirect that used to send that route back
  to the wishlist; the wishlist itself gained multi-select for batch downloads.

Settings are unified across sections: one external-services endpoint, one AI key
(`ANTHROPIC_API_KEY`), a single `/settings` page.

- **Setup** (2026-08-21): first launch opens a six-step guided wizard (`/setup`) —
  welcome/language, prerequisites, library paths, external services, slskd,
  summary — gated by `GET /api/setup/state` so a down backend never strands the
  user there. A declarative registry (`services/system_probe.py`) detects three
  external binaries — ffmpeg, fpcalc, slskd (yt-dlp and essentia are plain Python
  dependencies pip already installs, not registry entries). `services/binary_manifest.py`
  pins a version/URL/SHA256 per component per platform, and `services/binary_installer.py`
  downloads, verifies, extracts and installs each one — valid only once the binary
  has actually run, since a verified download can still fail to execute. macOS has
  no pinned `ffmpeg` build on purpose (no upstream ships a checksummed native arm64
  static binary): there the installer falls back to running the registry's recipe
  itself (`brew install ffmpeg`, same streamed log, same run-it-to-verify discipline)
  whenever `brew` is present, and only the manual command otherwise — the probe
  payload's `install_method` tells the two routes apart. `services/slskd_daemon.py`
  additionally writes `slskd.yml` (only the four keys it needs, the rest of the
  user's file untouched) and starts/stops the daemon as a detached process, never
  touching one it didn't start itself. Each provider credential (Spotify, Anthropic,
  Discogs, AcoustID) can be tested for real before moving on. Credentials became
  runtime-writable the same way paths/URLs already were (`core/runtime_settings.py`'s
  `SECRET_KEYS`): a key saved from the wizard or from `/settings` (same shared field
  components, so a key can be changed without re-running the wizard) takes effect
  immediately, no restart, and its value never appears in an API response.

## Where to look next

- Full chronological development diary: `docs/archive/PROGRESS-diario-completo.md`.
- Current backlog, open decisions and next steps: `docs/ROADMAP.md`.
