from app.models import AudioFile, Issue, ScanRoot
from app.services import analysis


def test_recompute_keeps_provider_override(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="X", title="A",
                  genre="House")
    db.add(f); db.flush()
    db.add(Issue(file_id=f.id, type="provider_override", field="genre",
                 severity="info", detail="override",
                 suggested_fix_json={"field": "genre", "action": "retag",
                                     "to": "Tech House", "source": "provider",
                                     "confidence": "high"}, status="open"))
    db.commit()

    analysis.recompute(db)  # l'Inspector NON produce provider_override

    assert db.query(Issue).filter_by(type="provider_override").count() == 1


def _file_with_lower_album(db):
    root = ScanRoot(path="/m"); db.add(root); db.flush()
    f = AudioFile(root_id=root.id, path="/m/a.mp3", ext="mp3", size_bytes=1,
                  hash_method="file", status="present", artist="Some Artist",
                  title="Some Title", album="ivanovo night luxe")  # all-lower
    db.add(f); db.flush()
    return f


def _album_override(file_id):
    # il provider ha autorità sul case dell'album (vince sul case)
    return Issue(file_id=file_id, type="provider_override", field="album",
                 severity="info", detail="override",
                 suggested_fix_json={"field": "album", "action": "retag",
                                     "to": "ivanovo night luxe", "source": "provider",
                                     "confidence": "high"}, status="accepted")


def test_inspector_casing_fires_without_provider_override(db):
    # Controllo: senza override, l'Inspector propone il Title Case sull'album lower.
    f = _file_with_lower_album(db)
    db.commit()
    analysis.recompute(db)
    casing = db.query(Issue).filter_by(type="inconsistent_casing", field="album").all()
    assert len(casing) == 1
    assert casing[0].suggested_fix_json["to"] == "Ivanovo Night Luxe"


def test_provider_override_suppresses_inspector_casing(db):
    # Con un provider_override sull'album, l'Inspector NON deve ri-proporre il
    # casing: provider ('ivanovo night luxe') e Inspector ('Ivanovo Night Luxe')
    # oscillerebbero all'infinito. Il provider vince sul case.
    f = _file_with_lower_album(db)
    db.add(_album_override(f.id))
    db.commit()
    analysis.recompute(db)
    assert db.query(Issue).filter_by(type="inconsistent_casing", field="album").count() == 0
    assert db.query(Issue).filter_by(type="provider_override", field="album").count() == 1


def test_provider_override_removes_stale_accepted_casing(db):
    # Una vecchia inconsistent_casing già accettata (Title Case) deve sparire
    # quando arriva l'autorità del provider, o il planner rigenererebbe un RETAG
    # in senso opposto al provider.
    f = _file_with_lower_album(db)
    db.add(Issue(file_id=f.id, type="inconsistent_casing", field="album",
                 severity="warning", detail="casing", status="accepted",
                 suggested_fix_json={"field": "album", "action": "retag",
                                     "from": "ivanovo night luxe", "to": "Ivanovo Night Luxe"}))
    db.add(_album_override(f.id))
    db.commit()
    analysis.recompute(db)
    assert db.query(Issue).filter_by(type="inconsistent_casing", field="album").count() == 0
