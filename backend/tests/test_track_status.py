from app.models import Track
from app.services.track_status import compute_status


def test_ready_for_set_needs_bpm_and_key():
    t = Track(source_type="spotify", bpm=124.0, camelot_key="8A")
    assert compute_status(t) == "ready_for_set"


def test_imported_without_core():
    assert compute_status(Track(source_type="spotify")) == "imported"
    assert compute_status(Track(source_type="spotify", bpm=124.0)) == "imported"
