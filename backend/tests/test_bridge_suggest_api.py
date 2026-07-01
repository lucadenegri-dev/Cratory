from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AudioFile, Issue, Settings
from app.services import cratory_bridge

FOUND = {"found": True, "match": "isrc", "track_id": 7, "artist": "Rataxes",
         "title": "Acid Face", "genre": "Acid Techno", "genre_secondary": None,
         "label": "Bunker", "year": 2024, "confidence": 100}
NOT_FOUND = {"found": False, "match": None, "track_id": None, "artist": None,
             "title": None, "genre": None, "genre_secondary": None, "label": None,
             "year": None, "confidence": 0}
EMPTY = {"configured": False, "files": 0, "suggested": 0,
         "unresolved": 0, "mismatches": 0}


def _configure(db, url="http://localhost:8000"):
    db.add(Settings(id=1, naming_template="{artist} - {title}",
                    folder_template="{genre}/{artist}", cratory_base_url=url))
    db.commit()


def _file(db, file_id, **kw):
    defaults = dict(root_id=1, path=f"/m/{file_id}.mp3", ext="mp3", size_bytes=1,
                    hash_method="file", status="present", has_cover=False)
    defaults.update(kw)
    db.add(AudioFile(id=file_id, **defaults))


def test_bridge_not_configured(db):
    with TestClient(app) as client:
        assert client.post("/api/issues/bridge-suggest").json() == EMPTY


def test_bridge_fills_missing_metadata_via_isrc(db, monkeypatch):
    _configure(db)
    _file(db, 1, artist="Rataxes", title="Acid Face", genre=None, year=None,
          label=None, isrc="DEAB12300123")
    for field in ("genre", "year", "label"):
        db.add(Issue(file_id=1, type="missing_metadata", field=field,
                     severity="warning", detail=f"{field} mancante",
                     suggested_fix_json=None, status="open"))
    db.commit()
    calls = []

    def fake(base_url, isrc=None, artist=None, title=None):
        calls.append({"base_url": base_url, "isrc": isrc,
                      "artist": artist, "title": title})
        return dict(FOUND)

    monkeypatch.setattr(cratory_bridge, "lookup", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r == {"configured": True, "files": 1, "suggested": 3,
                     "unresolved": 0, "mismatches": 0}
        # una sola chiamata HTTP per file (cache), preferendo l'ISRC
        assert calls == [{"base_url": "http://localhost:8000",
                          "isrc": "DEAB12300123", "artist": None, "title": None}]
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        by_field = {i["field"]: i for i in rows}
        assert by_field["genre"]["suggested_fix_json"] == {
            "field": "genre", "action": "retag", "to": "Acid Techno"}
        assert by_field["year"]["suggested_fix_json"]["to"] == 2024
        assert by_field["label"]["suggested_fix_json"]["to"] == "Bunker"
        assert all(i["status"] == "open" for i in rows)  # mai auto-accettate


def test_bridge_fills_artist_title_via_isrc(db, monkeypatch):
    _configure(db)
    _file(db, 2, artist=None, title=None, isrc="DEAB12300123")
    for field in ("artist", "title"):
        db.add(Issue(file_id=2, type="missing_required_tag", field=field,
                     severity="error", detail=f"{field} mancante",
                     suggested_fix_json=None, status="open"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["files"] == 1 and r["suggested"] == 2 and r["mismatches"] == 0
        rows = client.get("/api/issues", params={"type": "missing_required_tag"}).json()
        by_field = {i["field"]: i for i in rows}
        assert by_field["artist"]["suggested_fix_json"]["to"] == "Rataxes"
        assert by_field["title"]["suggested_fix_json"]["to"] == "Acid Face"


def test_bridge_fuzzy_fills_dirty_genre(db, monkeypatch):
    _configure(db)
    _file(db, 3, artist="Rataxes", title="Acid Face",
          genre="Techno, House, Acid", isrc=None)
    db.add(Issue(file_id=3, type="dirty_genre", field="genre", severity="warning",
                 detail="genere da normalizzare", suggested_fix_json=None,
                 status="open"))
    db.commit()
    calls = []

    def fake(base_url, isrc=None, artist=None, title=None):
        calls.append({"isrc": isrc, "artist": artist, "title": title})
        return dict(FOUND, match="fuzzy", confidence=70)

    monkeypatch.setattr(cratory_bridge, "lookup", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["suggested"] == 1 and r["mismatches"] == 0  # fuzzy: mai mismatch
        assert calls == [{"isrc": None, "artist": "Rataxes", "title": "Acid Face"}]
        rows = client.get("/api/issues", params={"type": "dirty_genre"}).json()
        assert rows[0]["suggested_fix_json"]["to"] == "Acid Techno"


def test_bridge_overwrites_open_ai_suggestion(db, monkeypatch):
    # Precedenza: Cratory > AI. Un suggerimento AI non ancora accettato
    # (status open) viene sovrascritto dal bridge.
    _configure(db)
    _file(db, 4, artist="Rataxes", title="Acid Face", genre=None, isrc=None)
    db.add(Issue(file_id=4, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante",
                 suggested_fix_json={"field": "genre", "action": "retag", "to": "House"},
                 status="open"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup",
                        lambda base_url, **kw: dict(FOUND, match="fuzzy", confidence=70))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["suggested"] == 1
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        assert rows[0]["suggested_fix_json"]["to"] == "Acid Techno"


def test_bridge_never_touches_accepted(db, monkeypatch):
    # Precedenza: fix manuale/accettato > Cratory. Status != open: intoccabile.
    _configure(db)
    _file(db, 5, artist="Rataxes", title="Acid Face", genre=None, isrc=None)
    db.add(Issue(file_id=5, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Scelto A Mano"},
                 status="accepted"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["files"] == 0 and r["suggested"] == 0
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        assert rows[0]["suggested_fix_json"]["to"] == "Scelto A Mano"
        assert rows[0]["status"] == "accepted"


def test_bridge_unresolved_without_key_or_match(db, monkeypatch):
    _configure(db)
    # File 6: niente ISRC, artist mancante -> nessuna chiave -> nessuna chiamata.
    _file(db, 6, artist=None, title="Solo Titolo", isrc=None)
    db.add(Issue(file_id=6, type="missing_required_tag", field="artist",
                 severity="error", detail="artist mancante",
                 suggested_fix_json=None, status="open"))
    # File 7: chiave fuzzy ma Cratory non trova nulla.
    _file(db, 7, artist="Ignoto", title="Mai Sentito", genre=None, isrc=None)
    db.add(Issue(file_id=7, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante",
                 suggested_fix_json=None, status="open"))
    db.commit()
    calls = []

    def fake(base_url, isrc=None, artist=None, title=None):
        calls.append(artist)
        return dict(NOT_FOUND)

    monkeypatch.setattr(cratory_bridge, "lookup", fake)
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r == {"configured": True, "files": 2, "suggested": 0,
                     "unresolved": 2, "mismatches": 0}
        assert calls == ["Ignoto"]  # per il file 6 nessuna chiamata (niente chiave)


def test_bridge_mismatch_on_isrc_conflict(db, monkeypatch):
    _configure(db)
    _file(db, 8, artist="Sconosciuto", title="Acid Face", genre="Acid Techno",
          year=2024, label="Bunker", isrc="DEAB12300123")
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mismatches"] == 1
        rows = client.get("/api/issues", params={"type": "bridge_mismatch"}).json()
        assert len(rows) == 1
        assert rows[0]["field"] == "artist"
        assert rows[0]["severity"] == "warning"
        assert rows[0]["status"] == "open"  # mai auto-applicata
        assert rows[0]["suggested_fix_json"] == {"field": "artist", "action": "retag",
                                                 "to": "Rataxes"}
        # idempotente: un secondo run non duplica la issue
        client.post("/api/issues/bridge-suggest")
        rows2 = client.get("/api/issues", params={"type": "bridge_mismatch"}).json()
        assert len(rows2) == 1


def test_bridge_mismatch_skipped_without_isrc(db, monkeypatch):
    _configure(db)
    _file(db, 9, artist="Altro Artista", title="Altro Titolo", genre=None, isrc=None)
    db.add(Issue(file_id=9, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante", suggested_fix_json=None, status="open"))
    db.commit()
    # Cratory risponde fuzzy con artist/title DIVERSI: senza ISRC niente mismatch.
    monkeypatch.setattr(cratory_bridge, "lookup",
                        lambda base_url, **kw: dict(FOUND, match="fuzzy", confidence=70))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mismatches"] == 0
        assert client.get("/api/issues", params={"type": "bridge_mismatch"}).json() == []


def test_bridge_mismatch_resolved_is_removed(db, monkeypatch):
    _configure(db)
    # Il tag ora coincide con Cratory: la vecchia discrepanza va rimossa.
    _file(db, 10, artist="Rataxes", title="Acid Face", isrc="DEAB12300123")
    db.add(Issue(file_id=10, type="bridge_mismatch", field="artist",
                 severity="warning", detail="vecchia discrepanza",
                 suggested_fix_json={"field": "artist", "action": "retag",
                                     "to": "Rataxes"},
                 status="open"))
    db.commit()
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        r = client.post("/api/issues/bridge-suggest").json()
        assert r["mismatches"] == 0
        assert client.get("/api/issues", params={"type": "bridge_mismatch"}).json() == []


def test_bridge_mismatch_orphan_removed_when_isrc_lost(db, monkeypatch):
    # File con bridge_mismatch esistente che perde l'ISRC: la riga orfana
    # (step 2) va ripulita anche se il conflitto non e' piu' verificabile.
    _file(db, 12, artist="Sconosciuto", title="Acid Face", isrc=None)
    db.add(Issue(file_id=12, type="bridge_mismatch", field="artist",
                 severity="warning", detail="vecchia discrepanza",
                 suggested_fix_json={"field": "artist", "action": "retag",
                                     "to": "Rataxes"},
                 status="open"))
    db.commit()
    _configure(db)
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        client.post("/api/issues/bridge-suggest")
        rows = db.execute(
            select(Issue).where(Issue.file_id == 12, Issue.type == "bridge_mismatch")
        ).scalars().all()
        assert rows == []


def test_bridge_mismatch_dismissed_untouched_when_conflict_persists(db, monkeypatch):
    # Riga bridge_mismatch dismissed: le decisioni utente sono intoccabili.
    # Anche se il conflitto persiste (stesso file/ISRC/risposta), detail,
    # updated_at, status e suggested_fix_json NON devono cambiare.
    _configure(db)
    _file(db, 13, artist="Sconosciuto", title="Acid Face", genre="Acid Techno",
          year=2024, label="Bunker", isrc="DEAB12300123")
    original_detail = "vecchia discrepanza (dismissed dall'utente)"
    original_fix = {"field": "artist", "action": "retag", "to": "Valore Manuale"}
    issue = Issue(file_id=13, type="bridge_mismatch", field="artist",
                  severity="warning", detail=original_detail,
                  suggested_fix_json=original_fix, status="dismissed")
    db.add(issue)
    db.commit()
    db.refresh(issue)
    original_updated_at = issue.updated_at
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        client.post("/api/issues/bridge-suggest")
    db.expire_all()
    refreshed = db.get(Issue, issue.id)
    assert refreshed is not None
    assert refreshed.detail == original_detail
    assert refreshed.updated_at == original_updated_at
    assert refreshed.status == "dismissed"
    assert refreshed.suggested_fix_json == original_fix


def test_bridge_mismatch_open_row_updated_when_conflict_changes(db, monkeypatch):
    # Contro-prova: una riga OPEN esistente deve continuare ad aggiornare
    # detail/updated_at/suggested_fix_json quando il conflitto persiste
    # (dimostra che il fix del guard non rompe il percorso open).
    _configure(db)
    _file(db, 14, artist="Sconosciuto", title="Acid Face", genre="Acid Techno",
          year=2024, label="Bunker", isrc="DEAB12300123")
    issue = Issue(file_id=14, type="bridge_mismatch", field="artist",
                  severity="warning", detail="vecchia discrepanza",
                  suggested_fix_json={"field": "artist", "action": "retag",
                                      "to": "Valore Vecchio"},
                  status="open")
    db.add(issue)
    db.commit()
    db.refresh(issue)
    original_updated_at = issue.updated_at
    monkeypatch.setattr(cratory_bridge, "lookup", lambda base_url, **kw: dict(FOUND))
    with TestClient(app) as client:
        client.post("/api/issues/bridge-suggest")
    db.expire_all()
    refreshed = db.get(Issue, issue.id)
    assert refreshed is not None
    assert refreshed.status == "open"
    assert refreshed.suggested_fix_json == {"field": "artist", "action": "retag",
                                             "to": "Rataxes"}
    assert "Rataxes" in refreshed.detail
    assert refreshed.updated_at != original_updated_at


def test_bridge_unreachable_degrades_cleanly(db, monkeypatch):
    _configure(db)
    _file(db, 11, artist="Rataxes", title="Acid Face", genre=None, isrc="DEAB12300123")
    db.add(Issue(file_id=11, type="missing_metadata", field="genre", severity="warning",
                 detail="genre mancante", suggested_fix_json=None, status="open"))
    db.commit()

    def boom(base_url, **kw):
        raise cratory_bridge.CratoryUnreachable("timeout")

    monkeypatch.setattr(cratory_bridge, "lookup", boom)
    with TestClient(app) as client:
        assert client.post("/api/issues/bridge-suggest").json() == EMPTY
        # nessuna modifica parziale: il suggerimento resta vuoto
        rows = client.get("/api/issues", params={"type": "missing_metadata"}).json()
        assert rows[0]["suggested_fix_json"] is None
