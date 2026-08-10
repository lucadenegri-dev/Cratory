# backend/tests/test_provider_suggest_api.py
from fastapi.testclient import TestClient

from app.main import app
from app.organize.models import AudioFile, Issue, ScanRoot

client = TestClient(app)


def _seed(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", artist="SLV", title="Dreamscapes", status="present")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="missing_metadata", field="label",
                 severity="info", detail="manca label", status="open"))
    db.commit()
    return f


def _no_fingerprint(monkeypatch):
    """AcoustID off → nessun ac_client, nessun fingerprint: test hermetico."""
    monkeypatch.setattr("app.organize.integrations.acoustid.acoustid_configured", lambda: False)


def _conf(monkeypatch, mapping):
    from app.organize.services.text_providers import ResolvedText
    monkeypatch.setattr(
        "app.organize.routers.issues.text_providers.resolve",
        lambda file, **kw: ResolvedText(fields=mapping, release_mbids=[], confidence=None))


def test_provider_suggest_fills_label(db, monkeypatch):
    _seed(db)
    _no_fingerprint(monkeypatch)
    _conf(monkeypatch, {"label": ("Drumcode", "text")})
    body = client.post("/api/issues/provider-suggest", json={"covers": False}).json()
    assert body["configured"] is True and body["suggested"] == 1
    assert body["acoustid_available"] is False and body["fingerprinted"] == 0
    iss = db.query(Issue).filter_by(field="label").one()
    assert iss.suggested_fix_json == {"field": "label", "action": "retag",
                                      "to": "Drumcode", "source": "provider",
                                      "confidence": "text"}
    assert iss.status == "open"


def test_provider_suggest_marks_high_confidence(db, monkeypatch):
    _seed(db)
    _no_fingerprint(monkeypatch)
    _conf(monkeypatch, {"label": ("Drumcode", "high")})
    client.post("/api/issues/provider-suggest", json={"covers": False})
    iss = db.query(Issue).filter_by(field="label").one()
    assert iss.suggested_fix_json["confidence"] == "high"


def test_provider_suggest_overwrites_ai_suggestion(db, monkeypatch):
    """Provider sovrascrive un suggerimento AI marcato source:ai."""
    _seed(db)
    iss = db.query(Issue).filter_by(field="label").one()
    iss.suggested_fix_json = {"field": "genre", "action": "retag", "to": "X", "source": "ai"}
    iss.field = "genre"
    db.commit()
    _no_fingerprint(monkeypatch)
    _conf(monkeypatch, {"genre": ("Y", "text")})
    body = client.post("/api/issues/provider-suggest", json={"covers": False}).json()
    assert body["suggested"] == 1
    db.refresh(iss)
    assert iss.suggested_fix_json == {"field": "genre", "action": "retag", "to": "Y",
                                      "source": "provider", "confidence": "text"}


def test_provider_suggest_overwrites_legacy_without_marker(db, monkeypatch):
    """Issue open con suggerimento legacy SENZA marker -> provider sovrascrive."""
    _seed(db)
    iss = db.query(Issue).filter_by(field="label").one()
    iss.suggested_fix_json = {"field": "label", "action": "retag", "to": "Legacy"}
    db.commit()
    _no_fingerprint(monkeypatch)
    _conf(monkeypatch, {"label": ("Drumcode", "text")})
    body = client.post("/api/issues/provider-suggest", json={"covers": False}).json()
    assert body["suggested"] == 1
    db.refresh(iss)
    assert iss.suggested_fix_json["to"] == "Drumcode"
    assert iss.suggested_fix_json["source"] == "provider"


def test_provider_suggest_idempotent_on_own_suggestions(db, monkeypatch):
    """Issue già source:provider -> nessuna nuova lookup, dict intoccato."""
    _seed(db)
    iss = db.query(Issue).filter_by(field="label").one()
    iss.suggested_fix_json = {"field": "label", "action": "retag", "to": "Drumcode",
                              "source": "provider", "confidence": "text"}
    db.commit()
    _no_fingerprint(monkeypatch)
    called = {"n": 0}

    def _fake(file, **kw):
        called["n"] += 1
        from app.organize.services.text_providers import ResolvedText
        return ResolvedText(fields={"label": ("ShouldNotBeUsed", "text")})

    monkeypatch.setattr("app.organize.routers.issues.text_providers.resolve", _fake)
    body = client.post("/api/issues/provider-suggest", json={"covers": False}).json()
    assert body["configured"] is True and body["suggested"] == 0 and body["files"] == 0
    assert called["n"] == 0


def test_provider_suggest_fingerprints_files_without_mbid(db, monkeypatch):
    """Fingerprint-first: file senza mbid + AcoustID on -> fingerprint prima della lookup,
    e l'mbid ottenuto viene persistito."""
    _seed(db)
    monkeypatch.setattr("app.organize.integrations.acoustid.acoustid_configured", lambda: True)
    monkeypatch.setattr("app.organize.integrations.acoustid.fpcalc_available", lambda: True)
    monkeypatch.setattr("app.organize.integrations.acoustid.get_acoustid_client", lambda: object())
    seen = {"fp": 0}

    def _fake_fp(file, client, **kw):
        seen["fp"] += 1
        file.mbid = "mb-xyz"
        return "mb-xyz"

    monkeypatch.setattr("app.organize.services.fingerprint.fingerprint_one", _fake_fp)
    _conf(monkeypatch, {"label": ("Drumcode", "high")})
    body = client.post("/api/issues/provider-suggest", json={"covers": False}).json()
    assert body["acoustid_available"] is True
    assert body["fingerprinted"] == 1 and seen["fp"] == 1
    assert db.query(AudioFile).one().mbid == "mb-xyz"
