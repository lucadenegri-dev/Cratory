"""I tag descrittivi (genre/album/label/year) in Library sono quelli del file
fisico quando la traccia ha un primary file: COALESCE(file, track) a query-time.

Il file vince quando ha un valore; un tag NULL sul file lascia visibile il
valore streaming. Artist/title NON seguono il file (identità Cratory).
"""

import pytest

from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.repositories import FileTags, get_primary_file, list_tracks


@pytest.fixture()
def make_owned(db):
    """Factory: crea una Track con un AudioFile primario dai tag dati."""
    root = ScanRoot(path="/tmp/lib")
    db.add(root)
    db.flush()

    def make(*, track_kw=None, file_kw=None) -> Track:
        t = Track(source_type="spotify", **(track_kw or {}))
        db.add(t)
        db.flush()
        f = AudioFile(
            root_id=root.id, track_id=t.id, path=f"/tmp/lib/{t.id}.mp3",
            ext=".mp3", size_bytes=1, hash_method="stream",
            status="present", location="library", **(file_kw or {}),
        )
        db.add(f)
        db.flush()
        t.primary_file_id = f.id
        t.has_local_file = True
        db.commit()
        return t

    return make


def test_file_tags_vincono_su_quelli_streaming(db, make_owned):
    make_owned(
        track_kw={"title": "T", "artist": "A", "genre": "Pop", "album": "SA",
                  "label": "SL", "year": 2001},
        file_kw={"genre": "Techno", "album": "FA", "label": "FL", "year": 2020},
    )
    _, rows = list_tracks(db)
    (_track, tags) = rows[0]
    assert tags == FileTags(genre="Techno", album="FA", label="FL", year=2020)


def test_tag_null_sul_file_lascia_il_valore_track(db, make_owned):
    make_owned(
        track_kw={"title": "T", "artist": "A", "genre": "Pop"},
        file_kw={"genre": None, "album": "FA"},
    )
    _, rows = list_tracks(db)
    (_track, tags) = rows[0]
    # genre resta None nei FileTags: il fallback su Track.genre avviene nel
    # serializer, così il flag di provenienza è derivabile (None = non dal file).
    assert tags.genre is None
    assert tags.album == "FA"


def test_traccia_senza_file_ha_filetags_vuoti(db):
    db.add(Track(source_type="spotify", title="T", artist="A", genre="Pop"))
    db.commit()
    _, rows = list_tracks(db)
    (_track, tags) = rows[0]
    assert tags == FileTags()


def test_filtro_genre_matcha_il_tag_del_file(db, make_owned):
    """DEVE fallire se il filtro usa la sola colonna tracks.genre."""
    make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop"},
               file_kw={"genre": "Techno"})
    total, rows = list_tracks(db, genre="techno")
    assert total == 1 and len(rows) == 1
    # ...e il valore streaming ora mascherato dal file NON matcha più:
    total, _ = list_tracks(db, genre="pop")
    assert total == 0


def test_filtro_genre_matcha_ancora_il_valore_track_senza_file(db):
    db.add(Track(source_type="spotify", title="T", artist="A", genre="Pop"))
    db.commit()
    total, _ = list_tracks(db, genre="pop")
    assert total == 1


def test_sort_genre_usa_il_valore_effettivo(db, make_owned):
    # senza file, genre "A"; con file, tag "Z" che maschera genre "B"
    db.add(Track(source_type="spotify", title="T1", artist="A", genre="Alpha"))
    db.commit()
    make_owned(track_kw={"title": "T2", "artist": "A", "genre": "Beta"},
               file_kw={"genre": "Zulu"})
    _, rows = list_tracks(db, sort="genre", order="asc")
    generi_effettivi = [tags.genre or t.genre for t, tags in rows]
    assert generi_effettivi == ["Alpha", "Zulu"]
    _, rows = list_tracks(db, sort="genre", order="desc")
    generi_effettivi = [tags.genre or t.genre for t, tags in rows]
    assert generi_effettivi == ["Zulu", "Alpha"]


def test_get_primary_file(db, make_owned):
    t = make_owned(track_kw={"title": "T", "artist": "A"},
                   file_kw={"genre": "Techno", "artist": "FA", "title": "FT"})
    pf = get_primary_file(db, t)
    assert pf is not None and pf.genre == "Techno"
    lead = Track(source_type="spotify", title="L", artist="A")
    db.add(lead)
    db.commit()
    assert get_primary_file(db, lead) is None


from app.repositories import get_track
from app.routers import tracks as tracks_router
from app.serializers import track_detail_out, track_out


def test_track_out_espone_effettivi_e_provenienza(db, make_owned):
    t = make_owned(
        track_kw={"title": "T", "artist": "A", "genre": "Pop", "year": 2001},
        file_kw={"genre": "Techno", "album": "FA"},  # label/year NULL sul file
    )
    _, rows = list_tracks(db)
    out = track_out(rows[0][0], rows[0][1])
    assert out.genre == "Techno" and out.genre_from_file is True
    assert out.album == "FA" and out.album_from_file is True
    assert out.year == 2001 and out.year_from_file is False   # fallback su Track
    assert out.label is None and out.label_from_file is False
    assert out.primary_file_id == t.primary_file_id
    # identità NON seguono il file:
    assert out.title == "T" and out.artist == "A"


def test_track_out_senza_filetags_invariato(db):
    t = Track(source_type="spotify", title="T", artist="A", genre="Pop")
    db.add(t)
    db.commit()
    out = track_out(t)
    assert out.genre == "Pop" and out.genre_from_file is False
    assert out.primary_file_id is None


def test_detail_espone_artist_title_del_file(db, make_owned):
    t = make_owned(track_kw={"title": "T", "artist": "A"},
                   file_kw={"artist": "File Artist", "title": "File Title",
                            "genre": "Techno"})
    detail = tracks_router.get_track_detail(t.id, db=db)
    assert detail.file_artist == "File Artist"
    assert detail.file_title == "File Title"
    assert detail.genre == "Techno" and detail.genre_from_file is True


def test_detail_lead_senza_file(db):
    t = Track(source_type="spotify", title="T", artist="A")
    db.add(t)
    db.commit()
    detail = tracks_router.get_track_detail(t.id, db=db)
    assert detail.file_artist is None and detail.file_title is None


from app.repositories import all_playable_tracks, effective_genre, genres_overview


def test_genres_overview_conta_il_genere_effettivo(db, make_owned):
    # candidabile = con BPM (come da docstring di genres_overview)
    make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop", "bpm": 128.0},
               file_kw={"genre": "Techno"})
    db.add(Track(source_type="spotify", title="L", artist="A",
                 genre="House", bpm=124.0))
    db.commit()
    rows = genres_overview(db)
    assert {r["genre"] for r in rows} == {"Techno", "House"}  # niente "Pop"


def test_effective_genre_helper(db, make_owned):
    t = make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop", "bpm": 128.0},
                   file_kw={"genre": "Techno"})
    (t_loaded,) = [x for x in all_playable_tracks(db) if x.id == t.id]
    assert effective_genre(t_loaded) == "Techno"
    lead = Track(source_type="spotify", title="L", artist="A", genre="House", bpm=124.0)
    db.add(lead)
    db.commit()
    assert effective_genre(lead) == "House"


def test_candidate_engine_filtra_sul_genere_effettivo(db, make_owned):
    """DEVE fallire se candidate_engine confronta t.genre invece del genere
    effettivo: la traccia è taggata Techno solo sul file (Track.genre="Pop")."""
    from app.schemas import SetGenerationRequest
    from app.services.candidate_engine import select_candidates

    t = make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop",
                             "bpm": 128.0, "camelot_key": "8A",
                             "duration_seconds": 300},
                   file_kw={"genre": "Techno"})
    pool = select_candidates(db, SetGenerationRequest(genres=["Techno"]))
    assert [x.id for x in pool] == [t.id]
    # ...e il genere streaming, ora mascherato dal tag file, non matcha più:
    pool = select_candidates(db, SetGenerationRequest(genres=["Pop"]))
    assert pool == []
