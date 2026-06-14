"""Test Fase C: generazione set da playlist, scoring feature, ruoli, export Markdown."""

from app.models import Playlist, Track
from app.routers.sets import export
from app.schemas import SetGenerationRequest
from app.services.set_generator import _desired_energy, _feature_fit, generate_set


def _playlist(db, name: str) -> Playlist:
    pl = Playlist(platform="spotify", name=name)
    db.add(pl)
    db.flush()
    return pl


def _add_track(db, pl_id: int, i: int, **kw) -> Track:
    t = Track(source_type="spotify", playlist_id=pl_id, title=f"T{i}", artist=f"Art{i}",
              duration_seconds=200, **kw)
    db.add(t)
    return t


def test_generate_set_scoped_to_playlist(db):
    pl = _playlist(db, "PL")
    other = _playlist(db, "Other")
    for i in range(8):
        _add_track(db, pl.id, i, bpm=124 + i * 0.5, camelot_key="8A")
    for i in range(8):
        _add_track(db, other.id, 100 + i, bpm=125 + i * 0.5, camelot_key="8A")
    db.commit()

    setlist = generate_set(db, SetGenerationRequest(playlist_id=pl.id, target_duration_minutes=20))
    in_pl = {t.id for t in db.query(Track).filter(Track.playlist_id == pl.id).all()}
    assert setlist.tracks
    assert all(st.track_id in in_pl for st in setlist.tracks)  # nessuna traccia di altre playlist


def test_generated_set_has_roles(db):
    pl = _playlist(db, "PL")
    for i in range(8):
        _add_track(db, pl.id, i, bpm=124 + i * 0.4, camelot_key="8A")
    db.commit()

    setlist = generate_set(db, SetGenerationRequest(playlist_id=pl.id, target_duration_minutes=20))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    assert ordered[0].role == "intro"
    assert ordered[-1].role == "closing"
    assert any(st.role == "peak" for st in ordered)


def test_desired_energy_interpolation():
    req = SetGenerationRequest(start_energy=40, end_energy=80)
    assert _desired_energy(req, 0.0) == 40
    assert _desired_energy(req, 0.5) == 60
    assert _desired_energy(req, 1.0) == 80
    assert _desired_energy(SetGenerationRequest(), 0.5) is None  # nessuna energia richiesta


def test_feature_fit_uses_only_available_signals():
    prev = Track(source_type="spotify", energy=50, mood="dark", genre="techno")
    cand = Track(source_type="spotify", energy=55, mood="dark", genre="techno")
    fit = _feature_fit(prev, cand, SetGenerationRequest(), None)
    assert fit is not None and fit >= 80  # energia dolce + mood uguale + genere coerente

    # nessuna feature presente -> None (il termine non incide sul ranking)
    bare = Track(source_type="spotify")
    assert _feature_fit(bare, Track(source_type="spotify"), SetGenerationRequest(), None) is None


def test_feature_scoring_prefers_coherent_energy(db):
    # due candidate identiche per BPM/key, ma una ha energia coerente con la precedente
    pl = _playlist(db, "PL")
    opener = _add_track(db, pl.id, 0, bpm=124.0, camelot_key="8A", energy=50)
    _add_track(db, pl.id, 1, bpm=124.0, camelot_key="8A", energy=92)   # salto di energia
    good = _add_track(db, pl.id, 2, bpm=124.0, camelot_key="8A", energy=55)  # progressione dolce
    db.commit()

    setlist = generate_set(db, SetGenerationRequest(
        playlist_id=pl.id, target_duration_minutes=10, start_bpm=124, end_bpm=124,
        max_tracks_per_artist=1,
    ))
    ordered = sorted(setlist.tracks, key=lambda st: st.position)
    assert ordered[0].track_id == opener.id
    # la seconda scelta deve essere quella con progressione di energia dolce
    assert ordered[1].track_id == good.id


def test_export_markdown(db):
    pl = _playlist(db, "PL")
    for i in range(6):
        _add_track(db, pl.id, i, bpm=124 + i * 0.5, camelot_key="8A")
    db.commit()
    setlist = generate_set(db, SetGenerationRequest(playlist_id=pl.id, target_duration_minutes=15))

    res = export(setlist.id, format="markdown", db=db)
    body = res.body.decode()
    assert body.startswith("# ")
    assert "| # | Ruolo | Traccia |" in body
    assert "intro" in body
