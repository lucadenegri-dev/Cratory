from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return eng


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_schema(eng=None) -> None:
    """create_all + ALTER TABLE per colonne aggiunte dopo MVP 1 (niente Alembic: app locale)."""
    eng = eng or engine
    with eng.begin() as conn:
        _recover_legacy_tracks_leftover(conn)
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        _migrate_add_model_columns(conn, eng.dialect)
        for table in Base.metadata.tables.values():
            existing_cols = {c["name"] for c in inspect(conn).get_columns(table.name)}
            for idx in table.indexes:
                if not set(idx.columns.keys()).issubset(existing_cols):
                    continue  # colonna non ancora presente (tabella pre-migrazione minima)
                idx.create(bind=conn, checkfirst=True)
        _migrate_drop_lead_cols(conn)
        _migrate_drop_legacy(conn)
        _migrate_drop_enrichment_cols(conn)
        _migrate_playlist_memberships(conn)
        _migrate_backfill_playlist_positions(conn)
        _migrate_rename_liked_spotify(conn)
        _migrate_rename_discovery_playlist(conn)
        _migrate_backfill_bpm_key_sources(conn)
        _migrate_null_soundcloud_stream_urls(conn)
        _migrate_recount_playlist_counts(conn)


def _migrate_add_model_columns(conn, dialect) -> None:
    """Additions derivate dal modello: ogni colonna presente in `Base.metadata`
    ma assente dal DB live (PRAGMA table_info) viene aggiunta con
    `ALTER TABLE ... ADD COLUMN`. E' il duale di `_migrate_drop_legacy`
    (drop model-derived): niente dict manuale da tenere allineato quando un
    modello guadagna una colonna. Tipo e default arrivano dalla Column stessa
    (vedi `_column_add_ddl`).

    Limiti SQLite rispettati:
    - NOT NULL e' legale in ADD COLUMN solo insieme a un DEFAULT non-NULL: i
      NOT NULL con default Python callable (utcnow, dict) si aggiungono
      nullable — il default ORM continua a valorizzare le righe nuove, quelle
      pre-esistenti restano NULL come col vecchio dict;
    - niente clausola REFERENCES: le colonne legacy con FK (Track.playlist_id,
      non droppabile, vedi `_DEAD_LEAD_COLS`) si ri-aggiungono come colonne
      semplici, esattamente come faceva il vecchio dict ("playlist_id": "INTEGER");
    - le colonne PK non sono aggiungibili con ADD COLUMN: si saltano (in
      pratica non capita mai, ogni tabella live ha la sua PK).

    Idempotente: aggiunge solo cio' che manca; su un DB fresco e' un no-op.
    """
    for table in Base.metadata.sorted_tables:
        live = {r[1] for r in conn.execute(
            text(f'PRAGMA table_info("{table.name}")')
        ).fetchall()}
        if not live:
            continue  # difensivo: create_all ha appena creato le tabelle mancanti
        for col in table.columns:
            if col.name in live or col.primary_key:
                continue
            conn.execute(text(
                f'ALTER TABLE "{table.name}" ADD COLUMN {_column_add_ddl(col, dialect)}'
            ))


def _column_add_ddl(col, dialect) -> str:
    """Frammento DDL `"nome" TIPO [DEFAULT x] [NOT NULL]` per l'ADD COLUMN,
    derivato dalla Column del modello: l'equivalente di cio' che il vecchio
    dict `additions` codificava a mano (es. "VARCHAR DEFAULT 'imported'")."""
    parts = [f'"{col.name}"', col.type.compile(dialect)]
    # server_default del modello (es. has_local_file="0"), reso come in create_all.
    default_sql = dialect.ddl_compiler(dialect, None).get_column_default_string(col)
    if default_sql is None and col.default is not None and col.default.is_scalar:
        # Default scalare solo lato Python (es. status='imported'): promosso a
        # DDL cosi' le righe pre-esistenti ricevono il valore atteso invece di NULL.
        processor = col.type.literal_processor(dialect)
        if processor is not None:
            default_sql = processor(col.default.arg)
    if default_sql is not None:
        parts.append(f"DEFAULT {default_sql}")
        if not col.nullable:
            parts.append("NOT NULL")  # SQLite lo accetta in ADD COLUMN solo col DEFAULT
    return " ".join(parts)


# Tabelle dell'era Rekordbox/MVP1 rimosse dopo il pivot a playlist->set.
_LEGACY_TABLES = ("beatgrid_points", "cue_points", "artists", "import_reports")
# source_type delle righe Rekordbox/locali, non piu' previste dal nuovo flusso.
_LEGACY_SOURCES = ("local", "rekordbox")


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}
    ).first())


def _recover_legacy_tracks_leftover(conn) -> None:
    """Recovery di un rebuild vecchio-stile (RENAME-based) interrotto a meta'.

    Se `_tracks_legacy` esiste ancora, il RENAME di `tracks` era gia' avvenuto (le
    REFERENCES dei figli puntano gia' a `_tracks_legacy`) ma il copy/drop successivo
    no. Va eseguita PRIMA di `Base.metadata.create_all`: altrimenti create_all prova
    a ricreare `tracks` (mancante) e gli indici `ix_tracks_*`, ancora attaccati a
    `_tracks_legacy` con il vecchio nome, causano "index ... already exists".

    Il RENAME back riscrive di nuovo le REFERENCES dei figli, stavolta a favore
    (self-healing, stesso meccanismo verificato del RENAME che le rompe).
    """
    if not _table_exists(conn, "_tracks_legacy"):
        return
    conn.execute(text("DROP TABLE IF EXISTS tracks"))  # eventuale tracks vuota del run interrotto
    conn.execute(text("ALTER TABLE _tracks_legacy RENAME TO tracks"))


def _migrate_drop_legacy(conn) -> None:
    """Ripulisce i DB pre-pivot: rimuove colonne/tabelle Rekordbox e le righe legacy.

    Usa `ALTER TABLE ... DROP COLUMN` nativo (SQLite >= 3.35), come
    `_migrate_drop_enrichment_cols`, invece del vecchio rebuild RENAME->copy->DROP:
    con le foreign key attive il RENAME di `tracks` riscrive le clausole REFERENCES
    di `playlist_tracks`/`setlist_tracks` verso il nome temporaneo, e il DROP della
    tabella rinominata fallisce con "FOREIGN KEY constraint failed" se le membership
    hanno righe (verificato su SQLite 3.53). Il DROP COLUMN non rinomina ne' ricrea
    nulla: le FK dei figli restano intatte per costruzione.

    La colonna `camelot_key` va preservata via `UPDATE ... COALESCE` (da `tonality`)
    PRIMA del drop, perche' il drop e' distruttivo. Le colonne del modello corrente
    (incl. `camelot_key`) esistono gia' a questo punto: `_migrate_add_model_columns`
    (ALTER ADD model-derived) gira prima di questa funzione in `ensure_schema`.

    Robusta agli interrupt: ogni DROP COLUMN e' atomico, quindi una run successiva
    droppa solo cio' che resta (idempotente). Il caso di un rebuild vecchio-stile
    lasciato a meta' (tabella `_tracks_legacy` presente) e' gestito da
    `_recover_legacy_tracks_leftover`, chiamata da `ensure_schema` PRIMA di
    `create_all` (altrimenti create_all stesso fallisce sugli indici orfani) e di
    nuovo qui in modo difensivo.
    """
    from app.models import Track  # import differito: models importa db.Base

    # Difensivo: se qualcuno chiama questa funzione senza passare per ensure_schema
    # (che fa gia' la recovery prima di create_all), il leftover va comunque sanato.
    _recover_legacy_tracks_leftover(conn)

    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tracks)")).fetchall()]
    if not cols:
        return
    current_cols = set(Track.__table__.columns.keys())
    dead = [c for c in cols if c not in current_cols]
    tracks_is_legacy = "rekordbox_track_id" in cols or "play_count" in cols
    if not dead and not tracks_is_legacy:
        return

    # Coalesce PRIMA del drop: la colonna morta `tonality` va persa solo dopo
    # aver salvato il suo valore in `camelot_key` per le righe che non lo hanno.
    if "tonality" in cols:
        conn.execute(text("UPDATE tracks SET camelot_key = COALESCE(camelot_key, tonality)"))

    if dead:
        # SQLite rifiuta il DROP COLUMN su colonne indicizzate: droppa prima gli
        # indici che le coprono (stesso pattern di _migrate_drop_enrichment_cols).
        for (idx,) in conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tracks' AND sql IS NOT NULL"
        )).fetchall():
            covered = {r[2] for r in conn.execute(text(f'PRAGMA index_info("{idx}")')).fetchall()}
            if covered & set(dead):
                conn.execute(text(f'DROP INDEX IF EXISTS "{idx}"'))
        for col in dead:
            conn.execute(text(f'ALTER TABLE tracks DROP COLUMN "{col}"'))

    for tbl in _LEGACY_TABLES:
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))

    # Righe e set dell'era Rekordbox: con le FK attive le righe figlie (membership
    # playlist/set) vanno eliminate prima delle tracce che referenziano, altrimenti
    # il DELETE su `tracks` fallisce con "FOREIGN KEY constraint failed" (nessuna
    # delle due relazioni ha ON DELETE CASCADE nei modelli). Poi si potano le voci
    # di set orfane e i set rimasti senza tracce (i set "veri" su tracce streaming
    # restano).
    legacy_src = ", ".join(f"'{s}'" for s in _LEGACY_SOURCES)
    conn.execute(text(
        f"DELETE FROM playlist_tracks WHERE track_id IN "
        f"(SELECT id FROM tracks WHERE source_type IN ({legacy_src}))"
    ))
    conn.execute(text(
        f"DELETE FROM setlist_tracks WHERE track_id IN "
        f"(SELECT id FROM tracks WHERE source_type IN ({legacy_src}))"
    ))
    conn.execute(text(f"DELETE FROM tracks WHERE source_type IN ({legacy_src})"))
    conn.execute(text("DELETE FROM setlist_tracks WHERE track_id NOT IN (SELECT id FROM tracks)"))
    conn.execute(text("DELETE FROM setlists WHERE id NOT IN (SELECT setlist_id FROM setlist_tracks)"))


# Colonne enrichment/fingerprint rimosse con lo slim-down (slice 1B). `energy` resta.
_DEAD_TRACK_COLS = ("mood", "danceability", "vocalness", "genre_secondary",
                    "genre_source", "album_id", "enrichment_source",
                    "enrichment_confidence", "enriched_at", "mbid")


def _migrate_drop_enrichment_cols(conn) -> None:
    """Rimuove da `tracks` le colonne enrichment morte e la tabella `enrichment_cache`.

    Usa `ALTER TABLE ... DROP COLUMN` (SQLite >= 3.35) invece del rebuild con RENAME
    (pattern `_migrate_drop_legacy`): con le foreign key attive il RENAME di `tracks`
    riscrive le clausole REFERENCES di `playlist_tracks`/`setlist_tracks` verso il nome
    temporaneo e il DROP della tabella rinominata fallisce se le membership hanno righe
    (verificato su SQLite 3.53). Il DROP COLUMN non rinomina ne' ricrea nulla: le FK dei
    figli e gli indici delle colonne sopravvissute restano intatti.

    Idempotente e robusta agli interrupt: niente tabella temporanea, ogni statement e'
    atomico e una run successiva droppa solo cio' che e' ancora presente. Gli indici che
    coprono una colonna morta vanno eliminati prima (SQLite rifiuta il DROP COLUMN su
    colonne indicizzate, es. ix_tracks_mbid/ix_tracks_album_id dei DB storici).
    `enrichment_cache` si droppa comunque, anche quando `tracks` e' gia' pulita.
    """
    conn.execute(text("DROP TABLE IF EXISTS enrichment_cache"))
    cols = {r[1] for r in conn.execute(text("PRAGMA table_info(tracks)")).fetchall()}
    dead = [c for c in _DEAD_TRACK_COLS if c in cols]
    if not dead:
        return
    for (idx,) in conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tracks' AND sql IS NOT NULL"
    )).fetchall():
        covered = {r[2] for r in conn.execute(text(f'PRAGMA index_info("{idx}")')).fetchall()}
        if covered & set(dead):
            conn.execute(text(f'DROP INDEX IF EXISTS "{idx}"'))
    for col in dead:
        conn.execute(text(f'ALTER TABLE tracks DROP COLUMN "{col}"'))


def _migrate_playlist_memberships(conn) -> None:
    """Backfill M2M: copia Track.playlist_id nelle membership, poi svuota le colonne legacy.

    Idempotente: INSERT OR IGNORE non duplica; dopo lo svuotamento non ci sono piu'
    righe con playlist_id valorizzato, quindi le esecuzioni successive sono no-op.
    """
    if not _table_exists(conn, "playlist_tracks"):
        return
    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tracks)")).fetchall()]
    if "playlist_id" not in cols:
        return
    conn.execute(text(
        "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id, added_at) "
        "SELECT playlist_id, id, added_at FROM tracks WHERE playlist_id IS NOT NULL"
    ))
    conn.execute(text(
        "UPDATE tracks SET playlist_id = NULL, playlist_name = NULL WHERE playlist_id IS NOT NULL"
    ))


def _migrate_backfill_playlist_positions(conn) -> None:
    """Backfill di playlist_tracks.position: per ogni playlist assegna 1..N nell'ordine
    corrente (added_at NULLs-last, poi track_id) alle sole righe con position NULL.

    Idempotente: dopo il backfill le position sono valorizzate, quindi le ri-esecuzioni
    (WHERE position IS NULL) sono no-op.
    """
    if not _table_exists(conn, "playlist_tracks"):
        return
    cols = {r[1] for r in conn.execute(text('PRAGMA table_info("playlist_tracks")')).fetchall()}
    if "position" not in cols:
        return
    conn.execute(text(
        "WITH ordered AS ("
        "  SELECT playlist_id, track_id, ROW_NUMBER() OVER ("
        "    PARTITION BY playlist_id ORDER BY (added_at IS NULL), added_at, track_id"
        "  ) AS rn FROM playlist_tracks"
        ") "
        "UPDATE playlist_tracks SET position = ("
        "  SELECT rn FROM ordered o WHERE o.playlist_id = playlist_tracks.playlist_id "
        "    AND o.track_id = playlist_tracks.track_id"
        ") WHERE position IS NULL"
    ))


def _migrate_rename_liked_spotify(conn) -> None:
    """Rinomina la playlist dei liked Spotify da 'Liked Spotify' a 'Spotify Likes'.

    Idempotente: la WHERE sul vecchio nome rende no-op le esecuzioni successive.
    """
    if not _table_exists(conn, "playlists"):
        return
    conn.execute(text(
        "UPDATE playlists SET name = 'Spotify Likes' "
        "WHERE kind = 'liked' AND platform = 'spotify' AND name = 'Liked Spotify'"
    ))


def _migrate_rename_discovery_playlist(conn) -> None:
    """Rinomina la playlist di sistema Discovery da 'Scoperte' a 'Discovery'.

    Idempotente: la WHERE sul vecchio nome rende no-op le esecuzioni successive.
    """
    if not _table_exists(conn, "playlists"):
        return
    conn.execute(text(
        "UPDATE playlists SET name = 'Discovery' "
        "WHERE kind = 'discovery' AND platform = 'manual' AND name = 'Scoperte'"
    ))


def _migrate_null_soundcloud_stream_urls(conn) -> None:
    """NULLa gli `url` salvati per errore come stream CDN temporaneo
    (`media-streaming.soundcloud.cloud`) invece della pagina pubblica
    soundcloud.com: bug storico di `normalize_soundcloud_item` (priorita'
    url/webpage_url invertita, fix in services/playlist_import.py). Lo stream
    non e' reversibile in una pagina: nessun link e' meglio di uno rotto/scaduto;
    un ri-sync successivo lo ripara via `_apply_fields`.

    Idempotente: la WHERE su LIKE colpisce solo le righe ancora sporche.
    """
    if not _table_exists(conn, "tracks"):
        return
    conn.execute(text(
        "UPDATE tracks SET url = NULL WHERE url LIKE '%media-streaming.soundcloud.cloud%'"
    ))


def _migrate_recount_playlist_counts(conn) -> None:
    """Riallinea il `track_count` denormalizzato al numero reale di membership.

    Ripara i conteggi gonfiati dal bug storico di `merge_tracks` (dedup che
    eliminava membership senza ricontare, fix in repositories.py). Naturalmente
    idempotente e auto-riparante: ricalcola sempre il valore corretto.
    """
    if not _table_exists(conn, "playlists") or not _table_exists(conn, "playlist_tracks"):
        return
    conn.execute(text(
        "UPDATE playlists SET track_count = ("
        "    SELECT COUNT(*) FROM playlist_tracks"
        "    WHERE playlist_tracks.playlist_id = playlists.id"
        ")"
    ))


def _migrate_backfill_bpm_key_sources(conn) -> None:
    """Backfill provenienza bpm/key: i valori esistenti arrivavano dall'import
    Rekordbox (unica fonte storica di scrittura); un valore in realta' corretto a
    mano si ri-etichetta 'manual' alla prossima modifica. Idempotente: la WHERE
    su source NULL rende no-op le esecuzioni successive.

    Difensivo su `bpm`/`camelot_key`: con le additions model-derived
    (`_migrate_add_model_columns`, che gira prima in `ensure_schema`) entrambe le
    colonne esistono sempre a questo punto; il check resta come guardia se la
    funzione viene chiamata fuori da quel flusso, dove l'UPDATE fallirebbe con
    "no such column" invece di essere un no-op sicuro.
    """
    cols = {r[1] for r in conn.execute(text("PRAGMA table_info(tracks)")).fetchall()}
    if "bpm" in cols:
        conn.execute(text(
            "UPDATE tracks SET bpm_source = 'rekordbox' "
            "WHERE bpm IS NOT NULL AND bpm_source IS NULL"))
    if "camelot_key" in cols:
        conn.execute(text(
            "UPDATE tracks SET key_source = 'rekordbox' "
            "WHERE camelot_key IS NOT NULL AND camelot_key != '' AND key_source IS NULL"))


# `release_date`: colonna lead senza writer nel flusso attuale (metadati editoriali
# spostati su Sortory). Droppabile con DROP COLUMN: nessuna FK ne' indice.
# NB: playlist_id/playlist_name NON sono qui: playlist_id ha una FK baked-in nel CREATE
# TABLE e SQLite rifiuta il DROP COLUMN su una colonna referenziata in una foreign key;
# rimuoverle richiederebbe un rebuild di `tracks`, che il progetto evita (vedi
# _migrate_drop_legacy). Restano in schema, svuotate dal backfill M2M.
_DEAD_LEAD_COLS = ("release_date",)


def _migrate_drop_lead_cols(conn) -> None:
    """Rimuove da `tracks` `release_date` (lead residue senza writer attuale).

    Idempotente: droppa solo le colonne ancora presenti; su un DB fresco (create_all
    dal modello corrente) non ne trova nessuna ed e' no-op.

    Come `_migrate_drop_enrichment_cols` usa ALTER TABLE DROP COLUMN (niente rebuild
    RENAME: le FK dei figli restano intatte) e droppa prima gli indici che coprono una
    colonna morta (SQLite rifiuta il DROP COLUMN su colonne indicizzate).
    """
    cols = {r[1] for r in conn.execute(text("PRAGMA table_info(tracks)")).fetchall()}
    dead = [c for c in _DEAD_LEAD_COLS if c in cols]
    if not dead:
        return
    for (idx,) in conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tracks' AND sql IS NOT NULL"
    )).fetchall():
        covered = {r[2] for r in conn.execute(text(f'PRAGMA index_info("{idx}")')).fetchall()}
        if covered & set(dead):
            conn.execute(text(f'DROP INDEX IF EXISTS "{idx}"'))
    for col in dead:
        conn.execute(text(f'ALTER TABLE tracks DROP COLUMN "{col}"'))


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
