# Roadmap

## Naming

Nome scelto: **Cratory** (`crate` + `-ory`, "repository/archivio di crate").

Perche':

- evoca il crate digging: l'archivio di tracce del DJ;
- coerente col brand editoriale (archivio, monospace, squadrato);
- coniato e brandabile, breve e facile nell'interfaccia;
- piu' specifico e distintivo di "DJ Assistant" (ed evita la collisione del vecchio
  nome provvisorio "SetArc", gia' esistente).

Disponibilita' `cratory.com` da confermare su un registrar. I path tecnici legacy
(`djassistant.db`, log file) restano invariati per compatibilita' locale, salvo futura
migrazione esplicita.

## Stato completato

- Core deterministico: scoring, set generator, transition finder.
- Spotify OAuth, import playlist, liked tracks, export playlist.
- Import manuale da tracklist incollata.
- Data model streaming-first.
- Rimozione Rekordbox (2026-06-14, storica): **poi reintrodotto nel 2026-07 come fonte
  di BPM/key via import XML** — vedi "Pivot disk-first + Rekordbox" qui sotto. Non e'
  tornato il vecchio scope (beatgrid/cue restano fuori), solo BPM/Camelot.
- Gap Analysis.
- Candidate Engine con cap 60.
- AI Set Agent con output strutturato.
- Validation Engine.
- Set Editor e alternative.
- Modalita' `technical` e `creative`.
- Transition classification.
- Discovery playlist-seed Last.fm-centric con resolver Spotify e write-back.
- PATCH manuale valori traccia.
- UI Dashboard e Set Builder ridisegnate.
- Shazam/mix identification integrata (fase 1: identificazione tracklist e corpus
  DjSet separato); fase 2 (co-occorrenza) in backlog.
- Test reale con chiavi completato.
- Confronto modelli AI completato e implementato.
- Rimossa la sezione Discovery che suggeriva tracce sulla base dei gap della playlist.
- Reset documentazione 2026-06-18.
- Rebranding UI "editorial archive" (monocromo, IBM Plex Mono, tema dark/paper).
- Dashboard command center (figure, istogramma BPM, attivita', copertura, azioni).
- Sezione Etichette: backfill da copyright Spotify + normalizzazione nomi.
- Discovery con etichette: Radar Etichette (`label:`) + segnale-etichetta su expand;
  rimossa la "compatibilita' tecnica" dal Discovery (resta del Set Builder).
- Import Spotify: solo playlist possedute; sync/aggiorna delle gia' importate.
- Discovery v2 "Scava generi": dig a volume via Discogs (genere/stile), lead non
  risolti, ranking profondita'+novita', salva-al-volo. Fix: cancellare una playlist
  non elimina piu' i brani condivisi (scollega invece di hard-delete).
- Rename prodotto a **Cratory** (UI, codice, docs, icona); legacy `djassistant.*` invariati.
- Discovery de-noise + unificazione: ranking per domanda (want/have), filtri formato/
  self-released, dedup varianti, cap per artista; UI da 3 a 2 modi con "Scava"
  (Genere|Etichetta) e preset Familiare/Bilanciato/Avventuroso. Etichette ora via Discogs.
- Audit leggero (quick win): SSRF guard sull'URL del mix Shazam, `library_stats` con
  query SQL aggregate, rimozione endpoint morto `/api/discovery/labels`, tetti di versione
  alle dipendenze critiche.
- Rifacimento documentazione: ridisegno architettura doc (fonte di verita' unica),
  README vetrina in inglese + diagramma nuovo, audit accuratezza API/ARCHITECTURE,
  AGENTS unificato in CLAUDE, PRODUCT/DESIGN spostati in `docs/`.
- Discovery dig — gusto + spiegazioni: segnali di gusto (etichetta posseduta, affinita'
  stile, familiarita' graduata) su riferimento selezionabile (libreria|playlist), dedup
  sempre library-wide, e spiegazioni a chip (reason code deterministici, testo in UI).
- Discovery solo DIG: l'espansione playlist e' stata spostata nel contesto Playlist
  (pagina dedicata `/playlists/[id]/expand`, autorun senza AI). "Aggiungi" attacca il
  brano a quella playlist e, dove possibile, lo propaga sulla playlist Spotify
  (write-back best-effort via `POST /api/playlists/{id}/discovered-tracks`).
- Playlist many-to-many: tabella associativa `playlist_tracks` (membership), import che
  aggiunge appartenenze invece di sovrascrivere, delete/prune per-playlist, libreria che
  mostra "in N playlist". Colonne legacy `Track.playlist_id`/`playlist_name` svuotate.
- Acquisizione file via Soulseek (slskd): selezione deterministica per qualita'/match
  nome/disponibilita', job async con polling, download per-playlist (blocco con
  auto-pick) e per-traccia (mini-selettore da Discovery), link al `Track` esistente
  (`has_local_file`/`local_path`/`local_format`/`local_bitrate`). Eccezione dichiarata
  al principio "non conserva file audio" (resta il "non riproduce audio").
- **Disk-first (2026-07), fette 1-4: la libreria e' il disco.** `Track.audio_hash`
  (SHA-256 dello stream decodificato via ffmpeg, stabile a rinomina/retag) calcolato
  sia dall'acquisizione Soulseek sia dall'indicizzazione di libreria. `LIBRARY_ROOT` +
  `POST /api/library/index` (async, `GET /status`): scan della cartella canonica,
  match `audio_hash -> digest legacy -> ISRC -> fuzzy artist+title`, riconciliazione
  dei possessi persi (file spostato/cancellato -> torna wishlist, `audio_hash`
  mantenuto per riaggancio immediato), guard anti-unmount, contatore `duplicates`.
  Possesso in superficie: filtro `has_local_file` + sorgente `local_files` su
  `GET /api/tracks`, stat `with_local_file`, filtro/badge FILE in libreria — chiude
  la "Vista tracce senza file" (fast-follow Soulseek, era in backlog tecnico) con un
  filtro "Wishlist (senza file)" — card Impostazioni per indicizzare, figura
  "Possedute" in dashboard. Set Builder: `SetGenerationRequest.owned_only=True` di
  default, persistito su `Setlist.owned_only`, rispettato da editor/alternative (422
  se la sostituta non e' posseduta), toggle+badge in UI. Bridge DjOrganizer:
  `GET /api/tracks/lookup` read-only (isrc/artist+title, confidence 100/70/0,
  `limit(1)`). Le playlist streaming sono "lead" in UI, non la libreria.
- **Rifiniture disk-first (2026-07-02, lotti A-D):** indicizzazione incrementale a due
  passate (skip file invariati via mtime/size, contatore `unchanged`) con avvio
  automatico all'apertura del backend; archivio scartate (`ARCHIVE_ROOT` + `Track.archived`:
  l'indice scarta le tracce archiviate, escono da liste/coda download/wishlist, filtro
  "Scartate" in Libreria e sezione Disco nel dettaglio traccia); catena del genere con
  `Track.genre_source` (manuale/provider/tag file) e AI come anello di riserva, con
  normalizzazione leggera dei generi; auto-enrichment delle tracce nuove (da download
  Soulseek e da indice).
- **Pipeline di orientamento:** `GET /api/pipeline` (snapshot conteggi DB+disco), striscia
  PipelineStrip in dashboard con "Prossimo passo" cross-app (link a DjOrganizer via
  `ORGANIZER_URL`), menu raggruppato per fasi Scopri → Colleziona → Suona; `start-dev`
  avvia anche DjOrganizer se presente.
- **Barra job unificata (GlobalProgress):** poller unico in JobsProvider su tutti i job
  lunghi (all'epoca: enrichment, Shazam, download, indice, fingerprint — i job
  enrichment/fingerprint sono stati ritirati col pivot 2026-07, restano Shazam,
  download e indice), righe impilate con dettaglio ed esito visibile 4s.
- **Archivio download da sistemare + link file locale:** esiti download persistiti sulla
  Track, pagina `/downloads/issues` con filtri/contatori e azioni per riga (Scegli file
  Soulseek, Collega file locale, Ignora, Riprova tutte); collegamento manuale via
  `POST /api/tracks/{id}/link-file` + ricerca su disco `GET /api/files/search`.
- ~~Fingerprinting AcoustID (audio → MusicBrainz Recording MBID via `Track.mbid`,
  endpoint `/api/library/fingerprint[/status]`)~~ — **rimosso nel pivot 2026-07**
  insieme al motore di enrichment: era parte della catena feature esterna, ora
  ritirata (vedi "Pivot disk-first + Rekordbox" sotto). Nota storica, non attivo.
- **Playlist dalla libreria:** `POST /api/playlists/create-from-tracks` + composizione da
  UI; "Scarica mancanti" direttamente dal dettaglio playlist. Rimosso l'import playlist
  da cartella locale (superato dal disk-first: la cartella canonica si indicizza, non si
  importa come playlist).
- **Pivot disk-first + Rekordbox (2026-07, slice 1A/1B/2/3):** ritirati il motore di
  enrichment interno, il fingerprinting AcoustID e il bridge `GET /api/tracks/lookup`
  per DjOrganizer (slice 1A/1B) — l'arricchimento testuale dei metadati e il tagging
  su disco sono ora esclusivamente di DjOrganizer; le colonne DB del vecchio motore
  sono state droppate con migrazione FK-safe. **BPM/key tornano in Cratory solo
  dall'import della collezione Rekordbox XML** (`POST /api/rekordbox/import`, slice 2):
  match path (NFC) → `audio_hash` (gated su basename) → artist+title, mai sovrascrive
  un dato gia' presente; `energy` e' ora un campo derivato deterministico (BPM+genere),
  ricalcolato all'import e sui PATCH di bpm/genere, non piu' editabile a mano (422).
  Stati traccia ridotti a `imported | ready_for_set`. Dashboard: striscia a sei fasi
  Scopri → Acquisisci → Organizza⤴ → Indicizza → Analizza⤴ → Suona (slice 3), con
  pannello di import Rekordbox inline nella fase Analizza. Provider esterni residui
  (Last.fm, Discogs, Spotify) servono solo la Discovery. `.env`: rimosse le chiavi dei
  provider-audio/fingerprint (`MUSICBRAINZ_USER_AGENT`, `GETSONGBPM_API_KEY`,
  `DEEZER_ENABLED`, `ACOUSTICBRAINZ_ENABLED`, `ACOUSTID_API_KEY`); restano
  `SPOTIFY_*`, `LASTFM_API_KEY`, `DISCOGS_TOKEN`, `AI_*`, `SLSKD_*`, `LIBRARY_ROOT`,
  `ARCHIVE_ROOT`, `ORGANIZER_URL`. Dettaglio completo in `PROGRESS.md`.

## Direzione prodotto

Cratory e' uno **strumento personale/self-hosted eccellente** per DJ, NON un SaaS
multi-tenant pubblico. Vincolo bloccante (verificato): Spotify Web API non consente un
SaaS pubblico Spotify-based (dev mode max 5 utenti / Premium / endpoint ridotti;
extended quota mode solo per organizzazioni con servizio lanciato e >= 250k utenti/mese).
Il valore e' la qualita' del prodotto, non la scala.

## Prossimi passi

In ordine concordato (dettaglio operativo in `PROGRESS.md`):

1. **Miglioramento Discovery.** Slice gusto + spiegazioni del dig **FATTO** (segnali di
   gusto su riferimento selezionabile + reason code a chip). Restano nel backlog tecnico
   le sorgenti extra del dig (Last.fm tag, tracklist per-release); l'unificazione
   expand/dig e' superata (Discovery solo DIG, expand nel contesto Playlist di proposito).
2. **Audit leggero + quick win** — quick win principali FATTI (SSRF, `library_stats`,
   endpoint morto, dipendenze); robustezza confermata solida. Threat model piccolo
   (nessun utente pubblico), niente authz da SaaS.

(Il rifacimento documentazione, terzo passo concordato, e' stato completato — vedi
"Stato completato".)

Sospesi / rivisti:

- **Testi + multi-lingua (inglese)** — sospeso (rimandato). Estrazione stringhe per
  l'i18n e revisione copy/microcopy pagina per pagina; il rollout nome Cratory e' gia' fatto.
- **Multi-account pubblico** — sospeso (muro Spotify + direzione personale). Eventuale
  reshape futuro = piccola crew self-hosted con credenziali Spotify proprie, solo se serve.
- **Pitch** — da riformulare attorno alla natura reale del prodotto (non "SaaS Spotify").
- **Cambio nome** — FATTO (Cratory). Resta solo `cratory.com` da confermare su registrar.

Backlog tecnico (non bloccante):

- **Discovery: arricchire il dig.** Tracklist per-release (espandere un release nelle
  sue tracce) e Last.fm tag come 2a sorgente. (Genere+Etichetta gia' unificati; Playlist
  resta Spotify-resolved di proposito, goal diverso.)
- **Shazam fase 2.** `DjSetTrack` come corpus per suggerimenti di co-occorrenza.
- **SoundCloud import.** API chiusa a nuove app: rivalutare solo se riapre.
- **PostgreSQL.** Bassa priorita': SQLite basta per uso personale (servirebbe solo con
  un eventuale multi-utente).

## Rischi

| Rischio | Mitigazione |
|---|---|
| Tracce senza BPM/key | stato traccia resta `imported` (non usabile dal Set Builder) finche' non arriva un import Rekordbox; nessuna stima automatica |
| Rate limit o errori rete (provider Discovery) | retry/backoff, job async |
| Output AI inventato | candidate cap, schema Pydantic, Validation Engine |
| Spotify recommendation non disponibile | Discovery basato su Last.fm e resolver Spotify `/search` |
| Spotify dev-mode limita la profondita' (5 utenti, search `label:` cap 10) | profondita' di genere/etichetta da Discogs (aperto); Spotify solo come resolver |
| Rename prodotto rompe path dati | path legacy mantenuti, migrazione solo se esplicita |
| Import Rekordbox disallineato (path/hash/nome non matchano) | tre livelli di match (path NFC → audio_hash gated su basename → artist+title), report con conteggio `unmatched` |

## Decisioni consolidate

- Cratory e' uno strumento personale/self-hosted, non un SaaS pubblico (muro policy Spotify).
- Rekordbox e' tornato nel progetto (pivot 2026-07) ma solo come fonte di import BPM/key
  via export XML — non torna il vecchio scope (beatgrid/cue restano fuori, nessuna
  integrazione live con l'app Rekordbox).
- Spotify e' fonte di identita'/metadata, non di feature musicali.
- Discovery: profondita' di genere/etichetta da Discogs (aperto); Spotify resta solo
  resolver di identita' (al salvataggio).
- Discovery non usa Spotify `/recommendations`.
- Discovery non suggerisce piu' tracce dai gap della playlist; quei gap restano analisi separata.
- Discovery lavora per gusto, non per compatibilita' tecnica: BPM/key/transizioni
  sono competenza del Set Builder.
- Il modulo Shazam non popola direttamente la libreria: produce un corpus separato
  (resta l'unico fingerprinting audio del progetto — identifica mix esterni, non
  la libreria).
- L'arricchimento testuale dei metadati (titolo/artista/album/label/genere) e il
  tagging su disco sono competenza di DjOrganizer, non di Cratory (pivot 2026-07).
- SQLite resta sufficiente per uso locale mono-utente.
- Disk-first: la libreria e' il disco (`LIBRARY_ROOT`), non le playlist streaming
  (che restano lead). Cratory legge i file per indicizzarli ma non li scrive mai:
  tag e organizzazione restano competenza di DjOrganizer.
