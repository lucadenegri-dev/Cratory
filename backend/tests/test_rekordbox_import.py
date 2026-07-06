from app.models import Track
from app.services.rekordbox_import import apply_collection

_XML = b"""<DJ_PLAYLISTS><COLLECTION>
<TRACK Name="Dreamscapes" Artist="SLV" AverageBpm="128.00" Tonality="8A"
       Location="file://localhost/music/a.mp3"/>
</COLLECTION></DJ_PLAYLISTS>"""


def _owned(db, **kw):
    t = Track(source_type="spotify", has_local_file=True, **kw)
    db.add(t); db.commit(); db.refresh(t)
    return t


def test_apply_fills_bpm_key_and_energy_by_path(db):
    t = _owned(db, local_path="/music/a.mp3", genre="Techno")
    report = apply_collection(db, _XML)
    db.refresh(t)
    assert t.bpm == 128.0 and t.camelot_key == "8A"
    assert t.energy is not None            # ricalcolata da bpm+genere
    assert t.status == "ready_for_set"
    assert report["matched"] == 1 and report["bpm_set"] == 1


def test_apply_does_not_overwrite_existing_bpm(db):
    t = _owned(db, local_path="/music/a.mp3", bpm=120.0)
    apply_collection(db, _XML)
    db.refresh(t)
    assert t.bpm == 120.0                   # valore preesistente autorevole


def test_apply_matches_by_artist_title_fallback(db):
    t = _owned(db, local_path="/other/path.mp3", artist="SLV", title="Dreamscapes")
    report = apply_collection(db, _XML)
    db.refresh(t)
    assert t.bpm == 128.0 and report["matched"] == 1
