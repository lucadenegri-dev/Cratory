"""Comandi massivi di ISSUES per id espliciti: il frontend manda ciò che la
lista mostra (filtri correnti inclusi), non un tipo/gravità globale.

- ``/bulk`` con ``ids`` tocca solo quelle issue; il riparo su
  provider_override/genre_review vale solo per il bulk "per sola gravità":
  chi manda gli id le ha davanti agli occhi.
- ``/bulk-fix`` accetta in blocco i valori digitati a mano (una ``fix`` per
  riga), saltando e contando ciò che non si può accettare invece di fallire
  l'intera richiesta.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, Issue

client = TestClient(app)


def _seed(db):
    f = AudioFile(id=1, root_id=1, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="A", title="T",
                  genre="x")
    db.add(f)
    db.add(Issue(id=10, file_id=1, type="missing_metadata", field="genre",
                 severity="warning", detail="genre mancante", status="open"))
    db.add(Issue(id=11, file_id=1, type="missing_metadata", field="year",
                 severity="warning", detail="year mancante", status="open"))
    db.add(Issue(id=12, file_id=1, type="inconsistent_casing", field="artist",
                 severity="warning", detail="casing",
                 suggested_fix_json={"field": "artist", "action": "retag",
                                     "from": "a", "to": "A"}, status="open"))
    db.add(Issue(id=13, file_id=1, type="provider_override", field="genre",
                 severity="info", detail="override",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.add(Issue(id=14, file_id=1, type="missing_metadata", field="bpm",
                 severity="info", detail="non editabile", status="open"))
    db.commit()


def _status(db, issue_id):
    db.expire_all()
    return db.get(Issue, issue_id).status


def test_bulk_ids_touches_only_those(db):
    _seed(db)
    r = client.post("/api/organize/issues/bulk",
                    json={"ids": [10, 11], "status": "dismissed"})
    assert r.status_code == 200 and r.json() == {"updated": 2}
    assert _status(db, 10) == "dismissed"
    assert _status(db, 11) == "dismissed"
    assert _status(db, 12) == "open"
    assert _status(db, 13) == "open"


def test_bulk_ids_includes_override_when_explicit(db):
    """Per id il riparo non scatta: l'utente vede la riga e la sta ignorando
    apposta (a differenza del bulk per sola gravità 'info')."""
    _seed(db)
    r = client.post("/api/organize/issues/bulk",
                    json={"ids": [13], "status": "dismissed"})
    assert r.json() == {"updated": 1}
    assert _status(db, 13) == "dismissed"


def test_bulk_ids_accept_still_skips_without_suggestion(db):
    _seed(db)
    r = client.post("/api/organize/issues/bulk",
                    json={"ids": [10, 12], "status": "accepted"})
    assert r.json() == {"updated": 1}
    assert _status(db, 10) == "open"  # niente da applicare
    assert _status(db, 12) == "accepted"


def test_bulk_ids_ignores_unknown_ids(db):
    _seed(db)
    r = client.post("/api/organize/issues/bulk",
                    json={"ids": [999], "status": "dismissed"})
    assert r.status_code == 200 and r.json() == {"updated": 0}


def test_bulk_empty_ids_touches_nothing(db):
    """Lista vuota esplicita ≠ assente: non deve degradare a 'tutte'."""
    _seed(db)
    r = client.post("/api/organize/issues/bulk",
                    json={"ids": [], "status": "dismissed"})
    assert r.status_code == 200 and r.json() == {"updated": 0}
    assert _status(db, 10) == "open"


def test_bulk_fix_accepts_typed_values(db):
    _seed(db)
    r = client.post("/api/organize/issues/bulk-fix", json={"items": [
        {"id": 10, "value": " Techno "},
        {"id": 11, "value": "1999"},
    ]})
    assert r.status_code == 200
    assert r.json() == {"updated": 2, "skipped": 0}
    db.expire_all()
    i10 = db.get(Issue, 10)
    assert i10.status == "accepted"
    assert i10.suggested_fix_json == {"field": "genre", "action": "retag", "to": "Techno"}
    assert db.get(Issue, 11).status == "accepted"


def test_bulk_fix_preserves_markers(db):
    _seed(db)
    r = client.post("/api/organize/issues/bulk-fix",
                    json={"items": [{"id": 13, "value": "Deep House"}]})
    assert r.json() == {"updated": 1, "skipped": 0}
    db.expire_all()
    fix = db.get(Issue, 13).suggested_fix_json
    assert fix["to"] == "Deep House"
    assert fix["source"] == "provider" and fix["confidence"] == "high"


def test_bulk_fix_skips_and_counts_bad_items(db):
    """Campo non editabile, valore vuoto e id sconosciuto: saltati, non 400.
    Gli altri passano comunque."""
    _seed(db)
    r = client.post("/api/organize/issues/bulk-fix", json={"items": [
        {"id": 14, "value": "128"},
        {"id": 10, "value": "   "},
        {"id": 999, "value": "x"},
        {"id": 11, "value": "2001"},
    ]})
    assert r.status_code == 200
    assert r.json() == {"updated": 1, "skipped": 3}
    assert _status(db, 14) == "open"
    assert _status(db, 10) == "open"
    assert _status(db, 11) == "accepted"


def test_bulk_fix_empty_is_noop(db):
    _seed(db)
    r = client.post("/api/organize/issues/bulk-fix", json={"items": []})
    assert r.status_code == 200 and r.json() == {"updated": 0, "skipped": 0}
