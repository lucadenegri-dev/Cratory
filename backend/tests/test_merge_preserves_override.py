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
