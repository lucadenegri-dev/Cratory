"""Motore Scanner deterministico: walk del FS, lettura, upsert in DB."""

import logging
import os
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import runtime_settings
from app.core.config import settings
from app.models import Track
from app.organize.integrations import content_hash, tagio
from app.organize.models import AudioFile, ScanRoot, utcnow
from app.organize.schemas import LinkingReport, ScanSummary
from app.organize.services.file_link import deriva_location, stacca_file
from app.organize.services.roots import radici
from app.services.genre_align import align_track_genre

logger = logging.getLogger(__name__)

_TAG_FIELDS = (
    "bitrate", "sample_rate", "channels", "duration_s", "artist", "title", "album",
    "album_artist", "genre", "year", "label", "track_no", "comment", "isrc", "has_cover",
)


def _iter_audio_files(root_path: str) -> Iterator[tuple[str, str]]:
    for dirpath, dirs, names in os.walk(root_path):
        # Pota le directory nascoste (es. .quarantine dell'Apply): modificare
        # `dirs` in-place impedisce a os.walk di scenderci.
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext in settings.audio_exts:
                yield os.path.join(dirpath, name), ext


def _scan_file_fields(path: str, ext: str, mtime: float | None) -> dict:
    """Campi aggiornabili di AudioFile per un file, con errori isolati per-file.

    `mtime` è il tempo di modifica già letto dallo `stat()` del chiamante (fatto
    per decidere se saltare questa stessa lettura): si passa qui per scriverlo
    insieme agli altri campi della lettura completa, senza un secondo `stat()`.
    Se lo `stat()` del chiamante è fallito (file sparito fra `os.walk` e qui),
    arriva `None`: la riga risultante ha `mtime` NULL e verrà ritentata alla
    prossima corsa (non combacia mai con nessuno stat valido).
    """
    h, method = content_hash.compute(path, ext)
    fields = {
        "ext": ext.lstrip("."),
        "size_bytes": 0,
        "mtime": mtime,
        "content_hash": h,
        "hash_method": method,
        "scan_error": None,
        "has_cover": False,
    }
    for key in _TAG_FIELDS:
        fields.setdefault(key, None)
    try:
        fields["size_bytes"] = os.path.getsize(path)
    except OSError as exc:
        fields["scan_error"] = f"errore lettura file: {exc}"
        return fields
    try:
        info = tagio.read_info(path)
        tags = tagio.read_tags(path)
    except tagio.TagReadError as exc:
        fields["scan_error"] = str(exc)
        return fields
    fields.update(
        bitrate=info.bitrate, sample_rate=info.sample_rate,
        channels=info.channels, duration_s=info.duration_s,
        artist=tags.artist, title=tags.title, album=tags.album,
        album_artist=tags.album_artist, genre=tags.genre, year=tags.year,
        label=tags.label, track_no=tags.track_no, comment=tags.comment,
        isrc=tags.isrc, has_cover=tags.has_cover,
    )
    return fields


def _location_per(path: str) -> str:
    """Collocazione del file rispetto alle due cartelle di Settings.

    Un path fuori da entrambe non è libreria canonica per definizione, quindi
    "inbox" è la risposta conservativa; il warning serve a far emergere la
    configurazione incoerente (una ScanRoot che non sta né in LIBRARY_ROOT né in
    SLSKD_DOWNLOAD_DIR) invece di lasciarla passare muta. Con F3b, tolte le
    ScanRoot, il caso sparisce.
    """
    try:
        return deriva_location(path, library_root=runtime_settings.library_root(),
                               inbox_root=runtime_settings.slskd_download_dir())
    except ValueError:
        logger.warning("Path fuori dalle radici configurate, location=inbox: %s", path)
        return "inbox"


def scan(db: Session, roots: list[ScanRoot], on_progress=None) -> ScanSummary:
    """Scansiona le root date e aggiorna il DB.

    Semantica di idempotenza:
    - Nessuna riga duplicata: ogni file sul disco corrisponde a esattamente una riga.
    - Nessun falso missing/moved: i file invariati restano "present".
    - ``summary.updated`` conta le righe *rilette per intero* (mtime/size cambiati,
      riga nuova con scan_error, o riga senza mtime perché mai passata da questo
      meccanismo). Da F4 Task 3b una re-scansione su disco immutato NON produce
      più ``updated == N``: i file invariati (stesso path/size_bytes/mtime,
      nessuno scan_error) prendono il fast-path e finiscono in
      ``summary.unchanged``, senza rileggere né rihashare il file.

    Root percorsa e root scritta sono due nozioni distinte: la prima è la
    cartella che si sta camminando, la seconda si deriva dalla collocazione del
    file (`_location_per`).  Coincidevano per costruzione finché le ScanRoot le
    creava l'utente; da F3b no: con SLSKD_DOWNLOAD_DIR annidata dentro
    LIBRARY_ROOT lo stesso file viene percorso due volte e deriva "library"
    entrambe le volte.  Tutto ciò che è indicizzazione (lookup del già-noto,
    `seen`, riconciliazione) va quindi agganciato all'id DERIVATO.
    """
    summary = ScanSummary(roots=[r.id for r in roots], started_at=utcnow())
    # Un path percorso da due root (inbox annidata nella libreria) è lo stesso
    # file: da quando l'indicizzazione si aggancia alla collocazione derivata —
    # che dipende solo dal path — la seconda passata sarebbe pura duplicazione.
    work: list[tuple[str, str, str]] = []
    visti: set[str] = set()
    for root in roots:
        for path, ext in _iter_audio_files(root.path):
            # Chiave sul path REALE (symlink risolti) e normalizzato nelle
            # maiuscole, non sulla stringa grezza: due cartelle configurate che
            # raggiungono lo stesso albero per strade diverse — una
            # SLSKD_DOWNLOAD_DIR symlinkata dentro la libreria, o una differenza
            # di maiuscole su un filesystem case-insensitive — passerebbero
            # indenni il confronto fra stringhe e indicizzerebbero lo stesso
            # file due volte. In `work` resta il path originale: è quello che
            # va scritto in DB.
            chiave = os.path.normcase(os.path.realpath(path))
            if chiave in visti:
                continue
            visti.add(chiave)
            work.append((path, ext, _location_per(path)))
    summary.found = len(work)
    # Denominatore UNICO per le due fasi. Finche' ognuna riportava il proprio,
    # la percentuale scendeva al passaggio (100% di scanning -> 0% di linking).
    # La fase 2 itera le righe di libreria: `work` le conosce gia'.
    n_libreria = sum(1 for _, _, loc in work if loc == "library")
    totale_fasi = len(work) + n_libreria
    # Una sola risoluzione delle radici per l'intero scan: `radici()` costa due
    # query più un flush, e chiamarla per file (via `root_id_per`) cambierebbe
    # anche il MOMENTO del flush — gli insert pendenti finirebbero a disco a
    # metà loop invece che al flush unico di fine ciclo.
    id_per_location = {loc: r.id for loc, r in radici(db).items()}
    # Fail-fast PRIMA del primo insert: una collocazione senza cartella
    # configurata è un errore di configurazione, non del singolo file.
    # Scoprirlo a metà loop lascerebbe al chiamante una Session con dentro gli
    # AudioFile dei file già visitati (nessun commit li salva, ma restano
    # pendenti).
    mancanti = sorted({loc for _, _, loc in work if loc not in id_per_location})
    if mancanti:
        raise ValueError(f"cartella non configurata per location={mancanti[0]!r}")
    # Pre-semina le collocazioni delle root percorse: senza, una root il cui
    # walk non trova più nessun file non verrebbe riconciliata e i suoi file
    # spariti non diventerebbero mai "missing".
    seen_by_root: dict[int, set[str]] = {}
    for root in roots:
        root_id = id_per_location.get(_location_per(root.path))
        if root_id is not None:
            seen_by_root.setdefault(root_id, set())
    new_inserts: list[AudioFile] = []
    for index, (path, ext, location) in enumerate(work):
        root_id = id_per_location[location]
        # Registrazione PRIMA di ogni decisione di skip: `seen_by_root` alimenta
        # `_reconcile`, che marca "missing" ciò che non ha visto. Un file che
        # prende il fast-path sotto deve comunque risultare visto, altrimenti
        # ogni file invariato verrebbe dichiarato sparito.
        seen_by_root.setdefault(root_id, set()).add(path)
        existing = db.scalar(
            select(AudioFile).where(AudioFile.root_id == root_id, AudioFile.path == path)
        )
        # stat() costa niente (a differenza della lettura completa più sotto):
        # è il segnale incrementale. Se fallisce (file sparito fra os.walk e
        # qui) si ricade sulla lettura completa, che isola lo stesso errore.
        try:
            st = os.stat(path)
            stat_mtime, stat_size = st.st_mtime, st.st_size
        except OSError:
            stat_mtime, stat_size = None, None
        unchanged = (
            existing is not None
            and existing.scan_error is None
            and stat_mtime is not None
            and existing.mtime == stat_mtime
            and existing.size_bytes == stat_size
        )
        if unchanged:
            # Path, size_bytes e mtime combaciano con l'ultima lettura completa:
            # il contenuto non è cambiato, si salta content_hash.compute e la
            # rilettura dei tag. content_hash resta quello già in riga (serve a
            # _abbina_spostamenti anche per i file mai ri-hashati in questa corsa).
            existing.status = "present"
            existing.last_scanned_at = utcnow()
            summary.unchanged += 1
            if on_progress is not None:
                on_progress(index + 1, totale_fasi, "scanning")
            continue
        fields = _scan_file_fields(path, ext, stat_mtime)
        if existing is None:
            # Stesso timestamp per entrambi: un file "nuovo" ha
            # first_seen_at == last_scanned_at finché non lo si ri-scansiona
            # (base del filtro "solo file nuovi").
            now = utcnow()
            row = AudioFile(
                root_id=root_id, path=path, status="present", location=location,
                first_seen_at=now, last_scanned_at=now, **fields,
            )
            db.add(row)
            new_inserts.append(row)
            summary.inserted += 1
        else:
            old_genre = existing.genre
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.status = "present"
            existing.last_scanned_at = utcnow()
            summary.updated += 1
            # Sincronizzazione Parte 2 (stessa regola condivisa del backfill e
            # della modifica manuale, app.services.genre_align): un file gia'
            # agganciato il cui tag genere e' cambiato FUORI dall'app (rilevato
            # solo qui, dove il file e' stato davvero riletto — i file
            # invariati prendono il fast-path sopra e non passano di qui, quindi
            # questo non aggiunge costo proporzionale all'intera libreria, solo
            # ai file di cui il tag genere e' effettivamente cambiato) tiene
            # Track.genre allineato. Confronto sul valore grezzo prima
            # dell'eventuale query: evita un SELECT per ogni file riletto la cui
            # unica variazione era, es., bitrate o mtime.
            if existing.track_id is not None and fields["genre"] != old_genre:
                linked = db.get(Track, existing.track_id)
                if linked is not None:
                    align_track_genre(linked, fields["genre"], apply=True)
        if fields["scan_error"]:
            summary.errors += 1
        if on_progress is not None:
            on_progress(index + 1, totale_fasi, "scanning")
    db.flush()  # assegna gli id ai nuovi insert
    _reconcile(db, seen_by_root, id_per_location, new_inserts, summary)
    # `_reconcile` scrive status/path/location/root_id SOLO in memoria e
    # `SessionLocal` è `autoflush=False` (app/db.py): la SELECT della fase 2
    # (`collega_tracce`, WHERE location='library' AND status='present') valuta
    # la clausola contro il DATABASE, quindi senza questo flush leggerebbe lo
    # stato PRECEDENTE alla riconciliazione. Due conseguenze, entrambe con
    # perdita di dati: le righe di una radice smontata risulterebbero ancora
    # `present` (l'anti-unmount di `riconcilia_possessi` non scatta e le tracce
    # non referenziate vengono cancellate), e la riga fusa da un Apply
    # risulterebbe ancora in `location='inbox'` (il file organizzato resta
    # senza Track fino alla scansione successiva). Prima di F4 il problema non
    # poteva esistere: la fase 2 girava in un job separato, con la propria
    # sessione, su dati già committati.
    db.flush()

    # Fase 2: le tracce si agganciano ai file appena indicizzati. Una camminata
    # sola sul disco (D5 della spec): prima era library_index a ripercorrerlo.
    #
    # Gira SOLO se questo scan ha camminato la radice della libreria: le sue
    # parti ragionano sull'INTERA libreria (riconciliano i possessi e cancellano
    # le tracce orfane), e uno scan ristretto all'inbox
    # (`POST /api/organize/scan {"locations":["inbox"]}`, un clic dal filtro
    # Inbox in app/organize/files) non ha riconciliato nessuna riga di
    # libreria: le lascerebbe `present`, `scanned` non sarebbe zero e
    # l'anti-unmount di `riconcilia_possessi` non scatterebbe nemmeno con il
    # flush qui sopra. `summary.linking` resta None: è il segnale, per il
    # chiamante, che la libreria NON è stata indicizzata (scan_job ci gate la
    # scrittura di `last_index_at`).
    if _ha_camminato_la_libreria(roots):
        summary.linking = LinkingReport(
            **_aggancia_le_tracce(db, on_progress, offset=len(work), totale=totale_fasi)
        )

    # NOTA (F4): da qui in poi `scan()` non è più atomico. Prima aveva un solo
    # commit in coda, e un crash annullava l'intera scansione; ora le funzioni
    # della fase di aggancio committano al loro interno, quindi un errore in
    # `indicizza_archivio` o in `analysis.recompute` lascia indice e aggancio
    # parziali su disco. È benigno perché l'intera pipeline è idempotente e
    # converge alla corsa successiva — è la milestone dichiarata della fase — ma
    # è una proprietà persa, non una scelta: non contarci sopra.
    db.commit()
    summary.finished_at = utcnow()
    return summary


def _ha_camminato_la_libreria(roots: list[ScanRoot]) -> bool:
    """True se fra le radici percorse c'è LIBRARY_ROOT in persona.

    Confronto sul path reale (symlink risolti, maiuscole normalizzate) come la
    dedup dei file, e NON su `_location_per(root.path)`: con
    SLSKD_DOWNLOAD_DIR annidata dentro LIBRARY_ROOT anche la radice inbox
    deriva "library", ma camminare l'inbox non è camminare la libreria."""
    libreria = runtime_settings.library_root()
    if not libreria:
        return False

    def chiave(path: str) -> str:
        return os.path.normcase(os.path.realpath(path))

    return chiave(libreria) in {chiave(r.path) for r in roots}


def _aggancia_le_tracce(db: Session, on_progress, *, offset: int = 0,
                        totale: int | None = None) -> dict:
    """Fase 2: le tracce si agganciano ai file che la fase 1 ha appena scritto.

    Import differito: app/services/library_index.py importa già da
    app/organize/ (per aggiorna_primary), e un import a livello di modulo
    chiuderebbe il ciclo."""
    from app.services.library_index import (
        collega_tracce,
        indicizza_archivio,
        recompute_energy,
        riconcilia_possessi,
    )

    def _progress_linking(processed: int, total: int) -> None:
        """Traduce il conteggio locale della fase 2 nel denominatore comune:
        le funzioni interne continuano a contare per conto proprio, e' qui che
        si somma l'offset della fase 1. Il min() protegge dalla stima: se le
        righe da agganciare fossero piu' dei file camminati, la frazione non
        supera 1."""
        if on_progress is None:
            return
        if totale is None:
            on_progress(processed, total, "linking")
            return
        on_progress(min(offset + processed, totale), totale, "linking")

    # Le quattro parti del giro d'indicizzazione, nell'ordine obbligatorio
    # (vedi i docstring in library_index.py): la libreria prima dell'archivio
    # (a parità di audio il possesso vince), la riconciliazione per ultima
    # (altrimenti una traccia il cui file è passato in ARCHIVE_ROOT viene
    # cancellata invece che marcata scartata), e infine il ricalcolo
    # dell'energia — `index_library` non è tre chiamate ma quattro
    # (library_index.py `index_library`): `_own` scrive solo `energy_raw`,
    # ed è `recompute_energy` a calibrarlo in `energy` (0-100). Senza questa
    # chiusura le Track appena agganciate restano con `energy` NULL e fuori
    # dall'arco energetico del Set Builder finché non gira, separatamente, il
    # job di Cratory. `seen_paths`/`seen_digests` sono lo stato condiviso fra
    # le prime tre e vanno passati identici a tutte.
    seen_paths: set[str] = set()
    seen_digests: set[str] = set()
    link_report = collega_tracce(db, seen_paths=seen_paths, seen_digests=seen_digests,
                                 on_progress=_progress_linking)

    archive_root = runtime_settings.archive_root()
    if archive_root:
        arc_report = indicizza_archivio(db, archive_root=archive_root,
                                        seen_paths=seen_paths, seen_digests=seen_digests,
                                        on_progress=_progress_linking)
        # I contatori dell'archivio NON si sommano a quelli di libreria: un
        # `unchanged` di libreria (riga già agganciata e invariata) e uno
        # d'archivio (file scartato già visto) sono due cose diverse, e la
        # somma dava un numero che non significava nulla. `archived` è l'unico
        # senza gemello — lo produce solo questo giro — e resta com'è.
        link_report["archived"] += arc_report["archived"]
        for key in ("failed", "unchanged", "duplicates"):
            link_report[f"archive_{key}"] = arc_report[key]
        link_report["errors"] += arc_report["errors"]

    rec = riconcilia_possessi(db, seen_paths=seen_paths, scanned=link_report["scanned"])
    link_report["lost"] += rec["lost"]
    link_report["orphans_removed"] += rec["orphans_removed"]

    # Anti-unmount, versione energia (stesso guard di `index_library`): uno
    # scan che non ha visto righe di libreria (radice smontata o vuota) non
    # deve nemmeno ricalcolare l'energia.
    if link_report["scanned"]:
        link_report["energy_computed"] = recompute_energy(db)

    return link_report


def _abbina_spostamenti(gone_by_hash, inserts_by_hash) -> dict[int, AudioFile]:
    """Abbinamenti riga-sparita → nuovo-insert, per content_hash.

    Due passate. La prima accoppia dentro la stessa radice: un rename in
    libreria deve fondersi col file rinominato, non con una copia identica
    appena arrivata in inbox (quale delle due vinca, altrimenti, lo decide
    l'ordine di walk). La seconda accoppia ciò che avanza attraversando il
    confine — è il caso dell'Apply (inbox→library) e del suo undo, dove per
    costruzione un candidato nella stessa radice non esiste.

    In entrambe le passate si fonde solo un abbinamento 1:1. Se più righe
    sparite o più insert si contendono lo stesso hash, nessun accoppiamento è
    più informato degli altri: si rinuncia, le righe restano missing e gli
    insert restano insert."""
    coppie: dict[int, AudioFile] = {}
    for h, gone in gone_by_hash.items():
        liberi = list(inserts_by_hash.get(h, ()))
        restanti = list(gone)
        for root_id in sorted({r.root_id for r in restanti}):
            g = [r for r in restanti if r.root_id == root_id]
            i = [c for c in liberi if c.root_id == root_id]
            if len(g) == 1 and len(i) == 1:
                coppie[g[0].id] = i[0]
                restanti.remove(g[0])
                liberi.remove(i[0])
        if len(restanti) == 1 and len(liberi) == 1:
            coppie[restanti[0].id] = liberi[0]
    return coppie


def _reconcile(db, seen_by_root, id_per_location, new_inserts, summary) -> None:
    """Marca i file spariti come missing; se l'hash combacia con un nuovo insert,
    li tratta come spostamento (aggiorna il path della riga esistente).

    L'abbinamento è per solo content_hash, non per (root, hash): uno
    spostamento può attraversare il confine inbox↔library (è esattamente ciò che
    fa un Apply), e la riga da riusare sta nell'altra radice.

    Quella chiave larga però ha un prezzo. `content_hash` è l'hash dello stream
    audio, stabile per costruzione a retag e rename, e trovare copie
    byte-identiche fra inbox e libreria è uno degli scopi dell'applicazione:
    due file con lo stesso hash sono la norma, non l'eccezione. Una fusione
    sbagliata non perde righe e non orfana FK, ma fa sopravvivere la riga —
    con id, first_seen_at, track_id e i figli Issue/DupMember/PlanOp/
    UndoJournal — puntata su un ALTRO file fisico, mentre il file davvero
    sparito non viene mai segnalato missing: un Issue già "accepted" o un
    DupMember "remove" si risolverebbero poi sulla copia sbagliata.

    Le guardie di `_abbina_spostamenti` stringono la maglia: preferenza per la
    stessa radice, e fusione solo sugli abbinamenti 1:1. Resta accettato il
    caso 1:1 che attraversa il confine, indistinguibile da un Apply o dal suo
    undo."""
    inserts_by_hash: dict[str, list[AudioFile]] = {}
    for row in new_inserts:
        if row.content_hash:
            inserts_by_hash.setdefault(row.content_hash, []).append(row)
    # Le righe sparite si raccolgono TUTTE prima di fondere: la guardia
    # sull'ambiguità deve contare anche le righe delle altre radici.
    gone_by_root: list[list[AudioFile]] = []
    gone_by_hash: dict[str, list[AudioFile]] = {}
    for root_id, seen in seen_by_root.items():
        all_rows = db.scalars(select(AudioFile).where(AudioFile.root_id == root_id)).all()
        gone = [r for r in all_rows if r.path not in seen and r.status != "missing"]
        gone_by_root.append(gone)
        for row in gone:
            if row.content_hash:
                gone_by_hash.setdefault(row.content_hash, []).append(row)
    coppie = _abbina_spostamenti(gone_by_hash, inserts_by_hash)
    for gone in gone_by_root:
        for row in gone:
            cand = coppie.get(row.id)
            if cand is not None and cand.id != row.id:
                moved_path = cand.path
                # Il file esce dall'indice: nessuna Track deve restare a
                # puntarlo. `cand` nasce in questo stesso scan, quindi di norma
                # non è ancora agganciato — ma se è già stato flushato può
                # esserlo, e la FK non ha chi la ordini. Costa una UPDATE.
                if cand.id is not None:
                    stacca_file(db, cand.id)
                db.delete(cand)
                db.flush()
                row.path = moved_path
                # Il file si è spostato: può aver attraversato il confine
                # inbox↔library (è esattamente ciò che fa un Apply).
                row.location = _location_per(moved_path)
                row.root_id = id_per_location.get(row.location, row.root_id)
                row.status = "present"
                row.last_scanned_at = utcnow()
                summary.moved += 1
                summary.inserted -= 1
            else:
                row.status = "missing"
                summary.missing += 1
