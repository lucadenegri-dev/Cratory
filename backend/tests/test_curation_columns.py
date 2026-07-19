"""Colonne di curatela AI: Setlist.curation e SetlistTrack.mood_tags."""

from sqlalchemy import inspect

from app.models import Setlist, SetlistTrack, Track
from app.serializers import setlist_out


def test_new_columns_exist_after_ensure_schema(db):
    cols_setlists = {c["name"] for c in inspect(db.get_bind()).get_columns("setlists")}
    cols_tracks = {c["name"] for c in inspect(db.get_bind()).get_columns("setlist_tracks")}
    assert "curation" in cols_setlists
    assert "mood_tags" in cols_tracks


def test_serializer_exposes_curation_and_mood_tags(db):
    t = Track(source_type="spotify", title="T", artist="A", duration_seconds=200,
              bpm=126.0, camelot_key="8A")
    db.add(t)
    db.flush()
    sl = Setlist(name="S", curation={"intent_summary": "warm-up malinconico"})
    sl.tracks.append(SetlistTrack(track_id=t.id, position=1, mood_tags=["malinconico", "deep"]))
    db.add(sl)
    db.commit()
    db.refresh(sl)
    out = setlist_out(sl)
    assert out.curation == {"intent_summary": "warm-up malinconico"}
    assert out.tracks[0].mood_tags == ["malinconico", "deep"]


def test_serializer_defaults_for_legacy_sets(db):
    sl = Setlist(name="Vecchio")
    db.add(sl)
    db.commit()
    db.refresh(sl)
    out = setlist_out(sl)
    assert out.curation == {}
    assert out.tracks == []
