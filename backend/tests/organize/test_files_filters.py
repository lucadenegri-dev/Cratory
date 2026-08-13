from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, ScanRoot

client = TestClient(app)


def _seed(db):
    root = ScanRoot(path="/m")
    db.add(root)
    db.flush()
    db.add_all([
        AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="ANNA", title="A",
                  album="Alpha", genre="House", year=2023, label="Diynamic"),
        AudioFile(root_id=root.id, path="/m/b.wav", ext="wav", size_bytes=1,
                  hash_method="file", status="present", artist="Kai Tracid", title="B",
                  album="Beta", genre="Trance", year=2002, label="Tracid Traxxx"),
        AudioFile(root_id=root.id, path="/m/c.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="ANNA", title="C",
                  album="Gamma", genre="House", year=2021, label="Diynamic"),
    ])
    db.commit()


def test_files_filter_by_genre(db):
    _seed(db)
    rows = client.get("/api/organize/files", params={"genre": "House"}).json()
    assert {r["title"] for r in rows} == {"A", "C"}
    assert all(r["genre"] == "House" for r in rows)


def test_files_filter_by_ext_and_year(db):
    _seed(db)
    rows = client.get("/api/organize/files", params={"ext": "mp3", "year": 2021}).json()
    assert {r["title"] for r in rows} == {"C"}


def test_files_filter_by_label(db):
    _seed(db)
    rows = client.get("/api/organize/files", params={"label": "Tracid Traxxx"}).json()
    assert {r["title"] for r in rows} == {"B"}


def test_filerow_exposes_tag_fields(db):
    _seed(db)
    row = next(r for r in client.get("/api/organize/files").json() if r["title"] == "A")
    assert row["album"] == "Alpha" and row["genre"] == "House"
    assert row["year"] == 2023 and row["label"] == "Diynamic"


def test_files_sort_by_title_asc_and_desc(db):
    _seed(db)
    asc = [r["title"] for r in client.get("/api/organize/files", params={"sort": "title", "dir": "asc"}).json()]
    desc = [r["title"] for r in client.get("/api/organize/files", params={"sort": "title", "dir": "desc"}).json()]
    assert asc == ["A", "B", "C"]
    assert desc == ["C", "B", "A"]


def test_files_sort_by_ext(db):
    _seed(db)
    exts = [r["ext"] for r in client.get("/api/organize/files", params={"sort": "ext", "dir": "asc"}).json()]
    assert exts == ["mp3", "mp3", "wav"]


def test_library_facets_distinct_sorted(db):
    _seed(db)
    f = client.get("/api/organize/library/facets").json()
    assert f["genre"] == ["House", "Trance"]
    assert f["ext"] == ["mp3", "wav"]
    assert f["year"] == [2002, 2021, 2023]
    assert f["label"] == ["Diynamic", "Tracid Traxxx"]
    assert "ANNA" in f["artist"] and "Kai Tracid" in f["artist"]


def test_files_search_q_escapes_underscore(db):
    """C3: `_` in `q` e' un carattere LIKE wildcard (un carattere qualsiasi) se
    non escapato. DEVE fallire se `q` finisce in un ILIKE grezzo: "trackA01"
    verrebbe pescato per errore insieme al vero match "track_01"."""
    root = ScanRoot(path="/m")
    db.add(root)
    db.flush()
    db.add_all([
        AudioFile(root_id=root.id, path="/m/track_01.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Target"),
        AudioFile(root_id=root.id, path="/m/trackA01.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Decoy"),
    ])
    db.commit()
    rows = client.get("/api/organize/files", params={"q": "track_01"}).json()
    assert {r["title"] for r in rows} == {"Target"}


def test_files_search_q_escapes_percent(db):
    """C3, stesso difetto con `%` (wildcard "zero o piu' caratteri" in LIKE):
    DEVE fallire se `q` finisce in un ILIKE grezzo, che pescherebbe anche
    "50xxxxoff" cercando "50%off"."""
    root = ScanRoot(path="/m")
    db.add(root)
    db.flush()
    db.add_all([
        AudioFile(root_id=root.id, path="/m/50%off.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Target"),
        AudioFile(root_id=root.id, path="/m/50xxxxoff.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Decoy"),
    ])
    db.commit()
    rows = client.get("/api/organize/files", params={"q": "50%off"}).json()
    assert {r["title"] for r in rows} == {"Target"}


def test_files_status_csv_include_missing(db):
    """C2: il cross-link dal dettaglio traccia deve trovare il file anche
    quando non e' piu' "present" (sparito dal disco) — l'unico caso in cui il
    link serve davvero. `status` accetta anche una CSV di piu' valori."""
    root = ScanRoot(path="/m")
    db.add(root)
    db.flush()
    db.add_all([
        AudioFile(root_id=root.id, path="/m/gone.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="missing", title="Gone"),
        AudioFile(root_id=root.id, path="/m/here.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Here"),
    ])
    db.commit()

    # Default: solo "present", come prima del fix.
    default_rows = client.get("/api/organize/files").json()
    assert {r["title"] for r in default_rows} == {"Here"}

    both = client.get("/api/organize/files", params={"status": "present,missing"}).json()
    assert {r["title"] for r in both} == {"Gone", "Here"}


def test_filerow_espone_track_id(db):
    from app.models import Track

    root = ScanRoot(path="/m2")
    db.add(root)
    db.flush()
    t = Track(source_type="spotify", title="T", artist="A")
    db.add(t)
    db.flush()
    db.add_all([
        AudioFile(root_id=root.id, path="/m2/linked.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Linked", track_id=t.id),
        AudioFile(root_id=root.id, path="/m2/loose.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", title="Loose"),
    ])
    db.commit()
    rows = client.get("/api/organize/files").json()
    linked = next(r for r in rows if r["title"] == "Linked")
    loose = next(r for r in rows if r["title"] == "Loose")
    assert linked["track_id"] == t.id
    assert loose["track_id"] is None
