"""Fix I3/M6: i tag effettivi (COALESCE file->streaming) valgono anche fuori
da GET /api/tracks e GET /api/tracks/{id}.

I3 (Important): la pagina playlist mostra i tag effettivi in GET
/api/playlists/{id}/tracks - il frontend precompila TrackEditModal da questo
payload ma salva sul file (single writer Organize): senza questo fix un
utente che "correggeva" il genere streaming che vedeva li' sovrascriveva
silenziosamente un tag del file mai mostrato.

M6 (Minor, stessa famiglia): altri percorsi di sola lettura - qui coperto da
Discovery add (import_single_track puo' ripiegare su una traccia gia'
posseduta via match artista+titolo).

Un test di guardia verifica anche che il numero di query SQL per
/api/playlists/{id}/tracks non cresca con il numero di tracce (niente N+1).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Setlist, SetlistTrack, Track
from app.organize.models import AudioFile, ScanRoot
from app.repositories import add_track_to_playlist


@pytest.fixture()
def client_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session, engine
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()


def _root(db) -> ScanRoot:
    root = ScanRoot(path="/tmp/lib")
    db.add(root)
    db.flush()
    return root


def _make_owned(db, root, *, track_kw, file_kw) -> Track:
    """Stessa factory di test_library_effective_tags.py: Track + AudioFile
    primario collegati (traccia posseduta con tag file propri)."""
    t = Track(source_type="local_files", **track_kw)
    db.add(t)
    db.flush()
    f = AudioFile(
        root_id=root.id, track_id=t.id, path=f"/tmp/lib/{t.id}.mp3",
        ext=".mp3", size_bytes=1, hash_method="stream",
        status="present", location="library", **file_kw,
    )
    db.add(f)
    db.flush()
    t.primary_file_id = f.id
    t.has_local_file = True
    db.commit()
    return t


# --- I3: la pagina playlist deve mostrare (e quindi precompilare il modal) --
# --- con lo STESSO valore che mostra la Library, non quello streaming ------


def test_playlist_tracks_usa_il_genere_del_file(client_db):
    """DEVE fallire se /api/playlists/{id}/tracks torna a serializzare con
    track_out(t) senza FileTags (bug I3): il genere mostrato sarebbe "Pop"
    invece di "Techno", e genre_from_file resterebbe False."""
    client, db, _engine = client_db
    root = _root(db)
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl)
    db.flush()
    t = _make_owned(
        db, root,
        track_kw={"title": "T", "artist": "A", "genre": "Pop"},
        file_kw={"genre": "Techno"},
    )
    add_track_to_playlist(db, t, pl)
    db.commit()

    r = client.get(f"/api/playlists/{pl.id}/tracks")
    assert r.status_code == 200
    (item,) = r.json()
    assert item["genre"] == "Techno"
    assert item["genre_from_file"] is True


def test_playlist_tracks_e_library_concordano_sulla_stessa_traccia(client_db):
    """La premessa della feature: quello che l'utente vede in Library e in
    Playlist per la STESSA traccia deve coincidere. Prima del fix i due
    endpoint divergevano (uno filtrava/serializzava sul file, l'altro no)."""
    client, db, _engine = client_db
    root = _root(db)
    pl = Playlist(platform="manual", name="P", kind="manual")
    db.add(pl)
    db.flush()
    t = _make_owned(
        db, root,
        track_kw={"title": "T", "artist": "A", "genre": "Electronic"},
        file_kw={"genre": "Progressive House"},
    )
    add_track_to_playlist(db, t, pl)
    db.commit()

    library_item = client.get("/api/tracks").json()["items"][0]
    playlist_item = client.get(f"/api/playlists/{pl.id}/tracks").json()[0]
    assert library_item["genre"] == playlist_item["genre"] == "Progressive House"


# --- M6: Discovery add puo' ripiegare su una traccia gia' posseduta --------


def test_discovery_add_su_traccia_esistente_usa_il_genere_del_file(client_db):
    """import_single_track fa match per artista+titolo su un lead senza
    identita' forte (niente platform_track_id/isrc): se la traccia trovata
    e' gia' posseduta, la risposta deve mostrare il genere del file, non
    quello streaming rimasto sulla Track."""
    client, db, _engine = client_db
    root = _root(db)
    _make_owned(
        db, root,
        track_kw={"title": "Same Name", "artist": "Same Artist", "genre": "Pop"},
        file_kw={"genre": "Witch House"},
    )

    r = client.post("/api/discovery/add", json={"artist": "Same Artist", "title": "Same Name"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is False  # ha trovato la traccia posseduta esistente
    assert body["track"]["genre"] == "Witch House"
    assert body["track"]["genre_from_file"] is True


# --- C1: le Alternative di un set devono mostrare il genere effettivo, non --
# --- quello streaming (ultimo payload rimasto indietro dopo 3eef90f) -------


def test_alternatives_usa_il_genere_del_file(client_db):
    """DEVE fallire se alternative_out(alt) torna a chiamare track_out(alt.track)
    senza FileTags (bug C1): il genere della candidata mostrata sarebbe "Pop"
    invece di "Techno", e genre_from_file resterebbe False."""
    client, db, _engine = client_db
    root = _root(db)
    setlist = Setlist(name="S")
    db.add(setlist)
    db.flush()
    current = Track(source_type="manual", title="Current", artist="A", bpm=128)
    db.add(current)
    db.flush()
    db.add(SetlistTrack(setlist_id=setlist.id, track_id=current.id, position=1))
    candidate = _make_owned(
        db, root,
        track_kw={"title": "Candidate", "artist": "B", "genre": "Pop", "bpm": 128},
        file_kw={"genre": "Techno"},
    )
    db.commit()

    r = client.post(f"/api/sets/{setlist.id}/alternatives",
                    json={"position": 1, "mode": "safer", "limit": 5})
    assert r.status_code == 200
    alts = r.json()["alternatives"]
    (alt,) = [a for a in alts if a["track"]["id"] == candidate.id]
    assert alt["track"]["genre"] == "Techno"
    assert alt["track"]["genre_from_file"] is True


# --- Guardia N+1: una playlist con piu' tracce non deve costare piu' query -


def _count_queries(engine, fn):
    count = 0

    def _listener(*_args, **_kwargs):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _listener)
    return count


# --- D5: setlist_out ed export CSV devono passare il genere effettivo -----
# --- a classify_transition (innesti di I4 rimasti scoperti da test) --------


def _set_con_reset_solo_via_tag_file(db, root):
    """Setlist di due tracce: BPM/key deboli (niente technically_safe) e
    genere STREAMING identico ("Techno") su entrambe, cosi' senza genre_map
    la transizione e' `creative_risk`. La seconda traccia e' posseduta con un
    tag file "Ambient": SOLO passando il genere effettivo la classificazione
    diventa `good_reset` (stesso schema di
    test_classify_transition_without_genre_map_keeps_streaming_behavior in
    test_i4_effective_genre_set_chain.py, qui end-to-end via l'API)."""
    setlist = Setlist(name="S")
    db.add(setlist)
    db.flush()
    prev = Track(source_type="manual", title="Prev", artist="A", bpm=128,
                 camelot_key="8A", energy=70, genre="Techno")
    db.add(prev)
    db.flush()
    cand = _make_owned(
        db, root,
        track_kw={"title": "Cand", "artist": "B", "bpm": 150, "camelot_key": "2B",
                 "energy": 68, "genre": "Techno"},
        file_kw={"genre": "Ambient"},
    )
    db.add(SetlistTrack(setlist_id=setlist.id, track_id=prev.id, position=1))
    db.add(SetlistTrack(setlist_id=setlist.id, track_id=cand.id, position=2))
    db.commit()
    return setlist


def test_setlist_out_passa_il_genere_effettivo_a_classify_transition(client_db):
    """DEVE fallire se setlist_out tornasse a costruire `genre_map` solo se
    `db` produce risultati (o smettesse di passarla): la classificazione
    resterebbe `creative_risk` (lo streaming e' identico su entrambe le
    tracce) invece di `good_reset` (il tag file della seconda e' "Ambient")."""
    client, db, _engine = client_db
    root = _root(db)
    setlist = _set_con_reset_solo_via_tag_file(db, root)

    r = client.get(f"/api/sets/{setlist.id}")
    assert r.status_code == 200
    items = r.json()["tracks"]
    assert items[1]["transition_class"] == "good_reset"


def test_export_csv_passa_il_genere_effettivo_a_classify_transition(client_db):
    """Stesso innesto (D5) ma per l'export CSV (`routers/sets.py`), che non ha
    `ft_map` e ricalcola `genre_map` con una query propria (legittima, D4)."""
    import csv
    import io

    client, db, _engine = client_db
    root = _root(db)
    setlist = _set_con_reset_solo_via_tag_file(db, root)

    r = client.post(f"/api/sets/{setlist.id}/export", params={"format": "csv"})
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text)))
    header, data_rows = rows[0], rows[1:]
    idx = header.index("transition_class")
    second_row = [row for row in data_rows if row[header.index("title")] == "Cand"][0]
    assert second_row[idx] == "good_reset"


def test_playlist_tracks_non_ha_n_piu_1_query(client_db):
    """DEVE fallire se il fix per I3 risolve i tag file traccia-per-traccia
    (es. `get_primary_file` dentro un ciclo) invece che con una query batch:
    in quel caso una playlist con piu' tracce costerebbe piu' query SQL di
    una con una sola traccia. Confrontiamo il conteggio invece di fissarne
    uno assoluto, cosi' il test non e' fragile a query accessorie invariate
    fra le due chiamate (es. il SELECT sulla playlist stessa)."""
    client, db, engine = client_db
    root = _root(db)

    pl_small = Playlist(platform="manual", name="Small", kind="manual")
    pl_big = Playlist(platform="manual", name="Big", kind="manual")
    db.add_all([pl_small, pl_big])
    db.flush()

    small = _make_owned(db, root, track_kw={"title": "S", "artist": "A", "genre": "Pop"},
                        file_kw={"genre": "Techno"})
    add_track_to_playlist(db, small, pl_small)

    for i in range(8):
        big_t = _make_owned(db, root, track_kw={"title": f"B{i}", "artist": "A", "genre": "Pop"},
                            file_kw={"genre": "Techno"})
        add_track_to_playlist(db, big_t, pl_big)
    db.commit()

    n_small = _count_queries(engine, lambda: client.get(f"/api/playlists/{pl_small.id}/tracks"))
    n_big = _count_queries(engine, lambda: client.get(f"/api/playlists/{pl_big.id}/tracks"))

    assert n_small == n_big, (
        f"il numero di query cresce con le tracce ({n_small} -> {n_big}): "
        "sospetto N+1 sui tag file"
    )
