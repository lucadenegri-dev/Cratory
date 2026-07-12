"""Test per l'aggiunta di una traccia al set (A14): append in coda, inserimento a
posizione con renumber+ruoli, duplicati, garanzia owned_only, 404 su set/traccia
inesistenti. Mirror di test_set_editing.py e test_set_editing_owned.py.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track
from app.repositories import all_playable_tracks, get_setlist
from app.schemas import SetGenerationRequest
from app.services.set_editor import SetEditError, add_track
from app.services.set_generator import generate_set


def _make_set(db, seed_fn, **kw):
    seed_fn(n=40)
    req = SetGenerationRequest(target_duration_minutes=45, start_bpm=128, end_bpm=134, **kw)
    return generate_set(db, req)


def _positions(setlist):
    return [st.position for st in sorted(setlist.tracks, key=lambda s: s.position)]


# --- Service: append/insert ----------------------------------------------------


def test_add_track_appends_at_end_by_default(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    before = len(s.tracks)
    present = {st.track_id for st in s.tracks}
    spare = next(t for t in all_playable_tracks(db) if t.id not in present)

    out = add_track(db, s.id, spare.id)
    assert len(out.tracks) == before + 1
    assert _positions(out) == list(range(1, before + 2))
    last = sorted(out.tracks, key=lambda st: st.position)[-1]
    assert last.track_id == spare.id
    assert last.transition_score is not None  # non e' l'apertura: ricomputato


def test_add_track_insert_at_position_renumbers_and_recomputes(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    before_ordered = sorted(s.tracks, key=lambda st: st.position)
    before = len(before_ordered)
    old_second = before_ordered[1].track_id
    present = {st.track_id for st in s.tracks}
    spare = next(t for t in all_playable_tracks(db) if t.id not in present)

    out = add_track(db, s.id, spare.id, position=2)
    ordered = sorted(out.tracks, key=lambda st: st.position)
    assert len(ordered) == before + 1
    assert _positions(out) == list(range(1, before + 2))
    assert ordered[1].track_id == spare.id  # posizione 2 (1-based)
    assert ordered[2].track_id == old_second  # spostata avanti di uno
    # apertura invariata e ricomputata come tale
    assert ordered[0].transition_score is None
    assert ordered[0].risk_level == "low"
    # il resto ha score ricomputato
    assert all(st.transition_score is not None for st in ordered[1:])


def test_add_track_reassigns_roles(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    present = {st.track_id for st in s.tracks}
    spare = next(t for t in all_playable_tracks(db) if t.id not in present)

    out = add_track(db, s.id, spare.id)
    ordered = sorted(out.tracks, key=lambda st: st.position)
    assert all(st.role for st in ordered)


# --- Service: errori -----------------------------------------------------------


def test_add_track_rejects_duplicate(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    existing = sorted(s.tracks, key=lambda st: st.position)[0].track_id
    with pytest.raises(SetEditError, match="gia'"):
        add_track(db, s.id, existing)


def test_add_track_invalid_position_too_low(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    present = {st.track_id for st in s.tracks}
    spare = next(t for t in all_playable_tracks(db) if t.id not in present)
    with pytest.raises(SetEditError):
        add_track(db, s.id, spare.id, position=0)


def test_add_track_invalid_position_too_high(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    present = {st.track_id for st in s.tracks}
    spare = next(t for t in all_playable_tracks(db) if t.id not in present)
    with pytest.raises(SetEditError):
        add_track(db, s.id, spare.id, position=len(s.tracks) + 2)


def test_add_track_nonexistent_track(db, seed_tracks):
    s = _make_set(db, seed_tracks)
    with pytest.raises(SetEditError, match="non trovata"):
        add_track(db, s.id, 999999)


def test_add_track_nonexistent_setlist(db, seed_tracks):
    seed_tracks(n=5)
    with pytest.raises(SetEditError, match="non trovato"):
        add_track(db, 999999, 1)


# --- Service: garanzia owned_only -----------------------------------------------


def _track(i: int, *, owned: bool | None, bpm: float | None = 128.0) -> Track:
    return Track(
        source_type="spotify", title=f"T{i}", artist=f"A{i}",
        bpm=bpm, camelot_key="8A", duration_seconds=300,
        has_local_file=owned,
    )


def _seed_owned(db, n: int = 6) -> None:
    for i in range(1, n + 1):
        db.add(_track(i, owned=True, bpm=125.0 + i))
    db.commit()


def _gen(db, **kw):
    return generate_set(db, SetGenerationRequest(target_duration_minutes=20, **kw))


def test_add_track_rejects_lead_on_owned_only_set(db):
    _seed_owned(db)
    s = _gen(db)  # default disk-first: owned_only=True
    lead = _track(99, owned=False)
    db.add(lead)
    db.commit()

    with pytest.raises(SetEditError, match="possedut"):
        add_track(db, s.id, lead.id)


def test_add_track_accepts_owned_on_owned_only_set(db):
    _seed_owned(db)
    s = _gen(db)
    present = {st.track_id for st in s.tracks}
    spare = next(t for t in all_playable_tracks(db, owned_only=True) if t.id not in present)

    out = add_track(db, s.id, spare.id)
    assert any(st.track_id == spare.id for st in out.tracks)


def test_add_track_accepts_lead_on_free_set(db):
    _seed_owned(db)
    s = _gen(db, owned_only=False)
    lead = _track(99, owned=False)
    db.add(lead)
    db.commit()

    out = add_track(db, s.id, lead.id)
    assert any(st.track_id == lead.id for st in out.tracks)


# --- Router: contratto HTTP ------------------------------------------------------


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _seed_and_generate(db):
    for i in range(40):
        db.add(Track(
            platform="spotify", spotify_id=f"spot{i:06d}", platform_track_id=f"spot{i:06d}",
            source_type="spotify", isrc=f"USABC{i:07d}", title=f"Track {i}", artist=f"Artist {i % 5}",
            duration_seconds=300, bpm=128.0 + (i % 8), camelot_key="8A",
            status="ready_for_set", has_local_file=True,
        ))
    db.commit()
    from app.services.set_generator import generate_set as _gen_set
    return _gen_set(db, SetGenerationRequest(target_duration_minutes=45, start_bpm=128, end_bpm=134))


def test_endpoint_add_track_returns_200_and_updated_setlist(client_db):
    client, db = client_db
    s = _seed_and_generate(db)
    before = len(s.tracks)
    present = {st.track_id for st in s.tracks}
    spare = next(t for t in all_playable_tracks(db) if t.id not in present)

    resp = client.post(f"/api/sets/{s.id}/tracks", json={"track_id": spare.id})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tracks"]) == before + 1
    assert any(item["track"]["id"] == spare.id for item in body["tracks"])


def test_endpoint_add_track_404_setlist_not_found(client_db):
    client, _db = client_db
    resp = client.post("/api/sets/999999/tracks", json={"track_id": 1})
    assert resp.status_code == 404


def test_endpoint_add_track_404_track_not_found(client_db):
    client, db = client_db
    s = _seed_and_generate(db)
    resp = client.post(f"/api/sets/{s.id}/tracks", json={"track_id": 999999})
    assert resp.status_code == 404


def test_endpoint_add_track_409_duplicate(client_db):
    client, db = client_db
    s = _seed_and_generate(db)
    existing = sorted(s.tracks, key=lambda st: st.position)[0].track_id
    resp = client.post(f"/api/sets/{s.id}/tracks", json={"track_id": existing})
    assert resp.status_code == 409


def test_endpoint_add_track_422_owned_only(client_db):
    client, db = client_db
    for i in range(1, 7):
        db.add(_track(i, owned=True, bpm=125.0 + i))
    db.commit()
    s = generate_set(db, SetGenerationRequest(target_duration_minutes=20))
    lead = _track(99, owned=False)
    db.add(lead)
    db.commit()

    resp = client.post(f"/api/sets/{s.id}/tracks", json={"track_id": lead.id})
    assert resp.status_code == 422


# --- Router: move endpoint, contratto "direction" vs "to" (B12) ----------------


def test_endpoint_move_with_to_moves_to_arbitrary_position(client_db):
    client, db = client_db
    s = _seed_and_generate(db)
    ordered_ids = [st.track_id for st in sorted(s.tracks, key=lambda st: st.position)]
    moved_id = ordered_ids[2]  # posizione 3

    resp = client.post(f"/api/sets/{s.id}/tracks/3/move", json={"to": 6})
    assert resp.status_code == 200
    body = resp.json()
    ordered = sorted(body["tracks"], key=lambda st: st["position"])
    assert ordered[5]["track"]["id"] == moved_id


def test_endpoint_move_with_direction_still_works(client_db):
    client, db = client_db
    s = _seed_and_generate(db)
    ordered_ids = [st.track_id for st in sorted(s.tracks, key=lambda st: st.position)]

    resp = client.post(f"/api/sets/{s.id}/tracks/2/move", json={"direction": "up"})
    assert resp.status_code == 200
    body = resp.json()
    ordered = sorted(body["tracks"], key=lambda st: st["position"])
    assert ordered[0]["track"]["id"] == ordered_ids[1]
    assert ordered[1]["track"]["id"] == ordered_ids[0]


def test_endpoint_move_rejects_both_direction_and_to(client_db):
    client, db = client_db
    s = _seed_and_generate(db)
    resp = client.post(f"/api/sets/{s.id}/tracks/1/move", json={"direction": "up", "to": 3})
    assert resp.status_code == 422


def test_endpoint_move_rejects_neither_direction_nor_to(client_db):
    client, db = client_db
    s = _seed_and_generate(db)
    resp = client.post(f"/api/sets/{s.id}/tracks/1/move", json={})
    assert resp.status_code == 422


def test_endpoint_move_with_to_invalid_target_422(client_db):
    client, db = client_db
    s = _seed_and_generate(db)
    resp = client.post(f"/api/sets/{s.id}/tracks/1/move", json={"to": 999})
    assert resp.status_code == 422
