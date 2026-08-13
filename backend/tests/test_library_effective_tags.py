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
    """F6: fixture in cui l'ordine sulla colonna streaming CONTRADDICE quello
    sul valore effettivo, così il test è vacuo solo se legge davvero
    _EFFECTIVE_TAGS['genre'], non Track.genre. Gli attesi sono scritti a mano,
    non derivati dalle righe restituite (a differenza della versione precedente
    di questo test, dimostrata vacua: fixture che si ordinavano ugualmente con
    entrambe le colonne — vedi verifica di non-vacuità nel report).

    A: Track.genre="Mango", senza file (effettivo = "Mango").
    B: Track.genre="Zebra" (mascherato), tag file genre="Apple" (effettivo = "Apple").
    Streaming grezzo (Track.genre per entrambe): "Mango"(A) < "Zebra"(B) -> asc A, B.
    Effettivo: "Apple"(B) < "Mango"(A) -> asc B, A. Le due colonne discordano davvero.
    """
    a = Track(source_type="spotify", title="TA", artist="A", genre="Mango")  # senza file
    db.add(a)
    db.commit()
    b = make_owned(track_kw={"title": "TB", "artist": "A", "genre": "Zebra"},
                   file_kw={"genre": "Apple"})
    _, rows = list_tracks(db, sort="genre", order="asc")
    assert [t.id for t, _ in rows] == [b.id, a.id]
    _, rows = list_tracks(db, sort="genre", order="desc")
    assert [t.id for t, _ in rows] == [a.id, b.id]


def test_sort_year_usa_il_valore_effettivo(db, make_owned):
    """F6: copertura mancante per sort=year, stessa forma del test del genere
    sopra (streaming e effettivo in disaccordo, attesi scritti a mano)."""
    a = Track(source_type="spotify", title="TA", artist="A", year=1990)  # senza file
    db.add(a)
    db.commit()
    b = make_owned(track_kw={"title": "TB", "artist": "A", "year": 2000},
                   file_kw={"year": 1980})
    # effettivo: A=1990, B=1980 -> asc B, A
    # streaming darebbe invece asc A, B (1990 < 2000): le due colonne discordano.
    _, rows = list_tracks(db, sort="year", order="asc")
    assert [t.id for t, _ in rows] == [b.id, a.id]
    _, rows = list_tracks(db, sort="year", order="desc")
    assert [t.id for t, _ in rows] == [a.id, b.id]


def test_filtro_album_matcha_il_tag_del_file(db, make_owned):
    """Copertura mancante (F6): il filtro album, come genre/label, deve leggere
    il valore effettivo."""
    make_owned(track_kw={"title": "T", "artist": "A", "album": "Streaming Album"},
               file_kw={"album": "File Album"})
    total, rows = list_tracks(db, album="file album")
    assert total == 1 and len(rows) == 1
    total, _ = list_tracks(db, album="streaming album")
    assert total == 0  # mascherato dal file: non matcha più


def test_filtro_label_matcha_il_tag_del_file(db, make_owned):
    """Copertura mancante (F6): il filtro label, come genre, deve leggere il
    valore effettivo (match esatto, non substring)."""
    make_owned(track_kw={"title": "T", "artist": "A", "label": "Streaming Label"},
               file_kw={"label": "File Label"})
    total, rows = list_tracks(db, label="File Label")
    assert total == 1 and len(rows) == 1
    total, _ = list_tracks(db, label="Streaming Label")
    assert total == 0  # mascherato dal file: non matcha più


def test_tag_vuoto_non_null_sul_file_non_sconfigge_il_fallback(db, make_owned):
    """F3: un frame ID3 presente ma vuoto (es. TCON="") viene salvato così
    com'è dallo scanner (AudioFile.genre=""). Senza NULLIF, COALESCE("", x)
    ritorna "" (una stringa vuota, non NULL) e il fallback streaming sparisce
    dietro un valore vuoto che si porta comunque dietro il badge "dal file"."""
    make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop"},
               file_kw={"genre": ""})
    _, rows = list_tracks(db)
    (track, tags) = rows[0]
    assert tags.genre is None  # non "": il valore streaming resta visibile

    out = track_out(track, tags)
    assert out.genre == "Pop" and out.genre_from_file is False  # niente badge "dal file"

    total, _ = list_tracks(db, genre="pop")
    assert total == 1  # il filtro effettivo continua a matchare lo streaming


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
    assert effective_genre(db, t_loaded) == "Techno"
    lead = Track(source_type="spotify", title="L", artist="A", genre="House", bpm=124.0)
    db.add(lead)
    db.commit()
    assert effective_genre(db, lead) == "House"


def test_effective_genre_risolve_per_id_anche_se_track_files_non_lo_contiene(db, make_owned):
    """F4: due tracce condividono un file fisico; `aggiorna_primary` imposta
    `primary_file_id` su entrambe senza azzerare la perdente, quindi il
    `primary_file_id` di `loser` punta a un file il cui `track_id` (il
    backref `track.files`) ormai appartiene a `winner`. `effective_genre`
    deve comunque risolvere il file per id (come fa la query SQL via
    `_EFFECTIVE_TAGS`/`_join_primary_file`), non filtrando `track.files`."""
    loser = make_owned(track_kw={"title": "L", "artist": "A", "genre": "Pop"},
                       file_kw={"genre": "Techno"})
    shared_file_id = loser.primary_file_id
    winner = make_owned(track_kw={"title": "W", "artist": "A", "genre": "House"},
                        file_kw={"genre": "Ambient"})
    # Simula l'ultimo aggiorna_primary: il file condiviso passa a `winner` (sia
    # come track_id del file sia come primary_file_id), ma `loser` non viene
    # azzerato e resta puntato allo stesso file id.
    from app.organize.models import AudioFile
    shared_file = db.get(AudioFile, shared_file_id)
    shared_file.track_id = winner.id
    winner.primary_file_id = shared_file_id
    db.commit()
    db.refresh(loser)

    assert effective_genre(db, loser) == "Techno"  # non "Pop": il file esiste ancora, solo per id


def test_candidate_engine_filtra_sul_genere_effettivo(db, make_owned):
    """DEVE fallire se candidate_engine confronta t.genre invece del genere
    effettivo: la traccia è taggata Techno solo sul file (Track.genre="Pop")."""
    from app.schemas import SetGenerationRequest
    from app.services.candidate_engine import select_candidates

    t = make_owned(track_kw={"title": "T", "artist": "A", "genre": "Pop",
                             "bpm": 128.0, "camelot_key": "8A",
                             "duration_seconds": 300},
                   file_kw={"genre": "Techno"})
    pool, _ = select_candidates(db, SetGenerationRequest(genres=["Techno"]))
    assert [x.id for x in pool] == [t.id]
    # ...e il genere streaming, ora mascherato dal tag file, non matcha più:
    pool, _ = select_candidates(db, SetGenerationRequest(genres=["Pop"]))
    assert pool == []
