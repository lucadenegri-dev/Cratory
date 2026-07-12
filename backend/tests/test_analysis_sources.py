"""Regole di provenienza: modifica manuale (repositories.update_track)."""
from app.models import Track
from app.repositories import update_track


def test_patch_bpm_imposta_source_manual(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="rekordbox")
    db.add(t); db.commit()
    update_track(db, t, {"bpm": 130.0})
    assert t.bpm == 130.0 and t.bpm_source == "manual"


def test_patch_key_imposta_source_manual(db):
    t = Track(source_type="spotify", camelot_key="8A", key_source="cratory")
    db.add(t); db.commit()
    update_track(db, t, {"camelot_key": "9A"})
    assert t.camelot_key == "9A" and t.key_source == "manual"


def test_azzeramento_azzera_anche_la_source(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="manual",
              camelot_key="8A", key_source="manual")
    db.add(t); db.commit()
    update_track(db, t, {"bpm": None, "camelot_key": None})
    assert t.bpm is None and t.bpm_source is None
    assert t.camelot_key is None and t.key_source is None


def test_patch_altri_campi_non_tocca_le_source(db):
    t = Track(source_type="spotify", bpm=128.0, bpm_source="rekordbox")
    db.add(t); db.commit()
    update_track(db, t, {"title": "Nuovo"})
    assert t.bpm_source == "rekordbox"
