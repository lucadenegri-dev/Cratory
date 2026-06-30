from app.integrations.slskd import SlskdFile
from app.services.soulseek_select import (
    QualityPreference, best_for_auto, rank_candidates,
)


def _f(filename, *, bitrate=None, slot=True):
    return SlskdFile(username="u", filename=filename, size=1, bitrate=bitrate,
                     length=None, has_free_slot=slot, queue_length=0)


def test_lossless_outranks_mp3_for_same_name():
    files = [
        _f("Daft Punk - Da Funk.mp3", bitrate=320),
        _f("Daft Punk - Da Funk.flac"),
    ]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked[0].file.extension == "flac"


def test_below_min_bitrate_excluded():
    files = [_f("Daft Punk - Da Funk.mp3", bitrate=128)]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked == []


def test_weak_name_match_excluded():
    files = [_f("Completely Unrelated Song.flac")]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert ranked == []


def test_best_for_auto_returns_none_below_threshold():
    # match parziale: nome plausibile ma non perfetto, solo mp3 a 256
    files = [_f("daft - da funk (live bootleg rip).mp3", bitrate=256)]
    best = best_for_auto(files, artist="Daft Punk", title="Da Funk")
    # confidence sotto 0.7 -> niente auto-pick
    assert best is None


def test_best_for_auto_picks_strong_lossless():
    files = [_f("Daft Punk - Da Funk.flac")]
    best = best_for_auto(files, artist="Daft Punk", title="Da Funk")
    assert best is not None
    assert best.confidence >= 0.7


def test_unknown_bitrate_lossy_not_excluded():
    # Soulseek spesso non riporta il bitrate in ricerca: un mp3 con bitrate ignoto
    # e nome coerente NON deve essere scartato (prima finiva tier 0 -> escluso).
    files = [_f("Daft Punk - Da Funk.mp3", bitrate=None)]
    ranked = rank_candidates(files, artist="Daft Punk", title="Da Funk")
    assert len(ranked) == 1
    assert ranked[0].quality_tier == 1


def test_name_match_uses_basename_not_full_path():
    # Path Soulseek reale e rumoroso: il titolo combacia col nome file anche se il
    # path e' lungo (cartelle/anno/formato). Prima veniva escluso (name_score basso).
    files = [_f("Music\\Arca\\Arca - KiCk i (2020) [FLAC]\\02  Time.flac")]
    ranked = rank_candidates(files, artist="Arca", title="Time")
    assert len(ranked) == 1
    best = best_for_auto(files, artist="Arca", title="Time")
    assert best is not None
    assert best.confidence >= 0.7
