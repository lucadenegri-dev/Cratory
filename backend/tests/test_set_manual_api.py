# backend/tests/test_set_manual_api.py
"""Endpoint del set manuale (tappa 1). TestClient con DB in memoria."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Playlist, Track
from app.repositories import add_track_to_playlist


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


def _seed(db, n=3):
    pl = Playlist(platform="spotify", name="Deep")
    db.add(pl)
    db.flush()
    tracks = []
    for i in range(n):
        t = Track(source_type="spotify", title=f"T{i}", artist="A", duration_seconds=300,
                  bpm=124.0, has_local_file=(i != 2))
        db.add(t)
        db.flush()
        add_track_to_playlist(db, t, pl, added_by="test")
        tracks.append(t)
    db.commit()
    return pl, tracks


def _rows(doc):
    return [r for b in doc["blocks"] if b["placement"] == "main" for r in b["rows"]]


def test_crea_da_playlist_e_rileggi(client_db):
    client, db = client_db
    pl, _ = _seed(db)
    r = client.post("/api/sets/manual", json={"playlist_id": pl.id})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["kind"] == "manual" and doc["name"] == "Deep"
    assert doc["source_playlist_name"] == "Deep" and doc["revision"] == 0
    assert doc["blocks"] == [] and doc["track_count"] == 0
    assert client.get(f"/api/sets/{doc['id']}/manual").json() == doc
    assert client.get("/api/sets").json()[0]["kind"] == "manual"


def test_crea_con_playlist_inesistente(client_db):
    client, _ = client_db
    r = client.post("/api/sets/manual", json={"playlist_id": 999})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "playlist_not_found"


def test_dettaglio_classico_rifiuta_il_set_manuale(client_db):
    client, db = client_db
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    r = client.get(f"/api/sets/{sid}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_is_manual"


def test_righe_inserisci_varco_sposta_appunto_togli(client_db):
    client, db = client_db
    _, t = _seed(db)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]

    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["revision"] == 1 and doc["track_count"] == 2 and doc["total_file_seconds"] == 600
    rows = _rows(doc)
    assert [x["track"]["id"] for x in rows] == [t[0].id, t[1].id]

    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 1, "gap": True, "after_row_id": rows[0]["id"]})
    rows = _rows(r.json())
    assert [x["slot_kind"] for x in rows] == ["track", "gap", "track"]
    assert rows[1]["track"] is None

    r = client.post(f"/api/sets/{sid}/rows/{rows[2]['id']}/move", json={"expected_revision": 2, "position": 1})
    rows = _rows(r.json())
    assert [x["slot_kind"] for x in rows] == ["track", "track", "gap"]
    assert [x["position"] for x in rows] == [1, 2, 3]

    r = client.patch(f"/api/sets/{sid}/rows/{rows[0]['id']}", json={"expected_revision": 3, "note": "apre bene"})
    assert _rows(r.json())[0]["note"] == "apre bene"

    r = client.delete(f"/api/sets/{sid}/rows/{rows[2]['id']}", params={"expected_revision": 4})
    doc = r.json()
    assert [x["slot_kind"] for x in _rows(doc)] == ["track", "track"] and doc["revision"] == 5


def test_conflitto_di_revisione(client_db):
    client, db = client_db
    _, t = _seed(db)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id]})
    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[1].id]})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["code"] == "set_revision_conflict" and d["params"]["current"] == 1


def test_errori_di_dominio(client_db):
    client, db = client_db
    _, t = _seed(db)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0})
    assert r.status_code == 422  # ne' track_ids ne' gap: validazione Pydantic
    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [999]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "manual_set_error"
    r = client.delete(f"/api/sets/{sid}/rows/999", params={"expected_revision": 0})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "set_row_not_found"
    r = client.get("/api/sets/999/manual")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "set_not_found"


def test_endpoint_manuali_rifiutano_un_set_generato(client_db):
    client, db = client_db
    from app.schemas import SetGenerationRequest
    from app.services.set_generator import generate_set
    for i in range(40):
        db.add(Track(source_type="spotify", title=f"G{i}", artist=f"A{i % 5}", duration_seconds=300,
                     bpm=128.0 + (i % 6), camelot_key="8A", has_local_file=True))
    db.commit()
    generated = generate_set(db, SetGenerationRequest(target_duration_minutes=30, start_bpm=128))
    r = client.get(f"/api/sets/{generated.id}/manual")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_not_manual"


def test_created_at_concorde_tra_lista_e_dettaglio(client_db):
    """La stessa riga manual deve avere lo stesso `created_at` (stessa stringa,
    stesso formato) sia nella lista (`setlist_summary_out`) sia nel dettaglio
    manuale (`manual_set_out`): altrimenti un client JS che fa `new Date(...)`
    interpreta le due risposte come due istanti diversi (offset assente =
    locale, offset presente = UTC).

    Il round-trip via HTTP qui sotto non basta da solo a incastrare una
    regressione: appena la richiesta che crea la riga ritorna, l'oggetto ORM
    smette di avere riferimenti forti e sparisce dalla identity map (nessuna
    `expire_on_commit`, ma nessuno lo tiene in vita); qualunque lettura
    successiva - lista o dettaglio, con o senza normalizzazione nel
    serializer - rilegge percio' un valore gia' naive da SQLite, e i due
    riletti combaciano comunque per accidente. Per pizzicare davvero un
    serializer che ha smesso di normalizzare, bisogna interrogare entrambi
    mentre l'oggetto e' ancora caldo (aware) in memoria: lo si ottiene solo
    creandolo qui nel test (riferimento tenuto in vita dalla variabile locale)
    invece che tramite l'endpoint, il cui frame torna e libera l'oggetto prima
    che il test possa ispezionarlo."""
    client, db = client_db

    from app.services.manual_set import create_manual_set
    from app.serializers import manual_set_out, setlist_summary_out

    setlist = create_manual_set(db, name="M", playlist_id=None)
    assert setlist.created_at.tzinfo is not None  # ancora caldo: sanity check del setup

    summary_created_at = setlist_summary_out(setlist).created_at.isoformat()
    detail_created_at = manual_set_out(setlist, db).created_at.isoformat()
    assert summary_created_at == detail_created_at

    # E anche il round-trip end-to-end reale (dopo che l'oggetto e' stato
    # rigenerato/riletto, entrambi gli endpoint devono restare d'accordo).
    from_list = next(s for s in client.get("/api/sets").json() if s["id"] == setlist.id)
    from_detail = client.get(f"/api/sets/{setlist.id}/manual").json()
    assert from_list["created_at"] == from_detail["created_at"]


def test_materiale_playlist_aggiornata_piu_set_piu_ricerca(client_db):
    client, db = client_db
    pl, t = _seed(db)  # t[2] senza file
    extra = Track(source_type="spotify", title="Fuori playlist", artist="Z", has_local_file=True)
    db.add(extra)
    db.commit()
    sid = client.post("/api/sets/manual", json={"playlist_id": pl.id}).json()["id"]
    client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id, extra.id]})

    doc = client.get(f"/api/sets/{sid}/material").json()
    assert doc["playlist_name"] == "Deep"
    by_id = {it["track"]["id"]: it for it in doc["items"]}
    assert [it["track"]["id"] for it in doc["items"]][:3] == [t[0].id, t[1].id, t[2].id]
    assert by_id[t[0].id]["in_set"] is True and by_id[t[0].id]["from_playlist"] is True
    assert by_id[extra.id]["in_set"] is True and by_id[extra.id]["from_playlist"] is False

    # la playlist cambia: il materiale la segue, il set no
    from app.repositories import remove_track_from_playlist
    remove_track_from_playlist(db, pl.id, t[0].id)
    db.commit()
    doc = client.get(f"/api/sets/{sid}/material").json()
    assert {it["track"]["id"] for it in doc["items"]} == {t[1].id, t[2].id, t[0].id, extra.id}
    assert {it["track"]["id"] for it in doc["items"] if it["from_playlist"]} == {t[1].id, t[2].id}
    assert client.get(f"/api/sets/{sid}/manual").json()["track_count"] == 2

    only_owned = client.get(f"/api/sets/{sid}/material", params={"owned": "true"}).json()["items"]
    assert t[2].id not in {it["track"]["id"] for it in only_owned}
    unused = client.get(f"/api/sets/{sid}/material", params={"unused": "true"}).json()["items"]
    assert {it["track"]["id"] for it in unused} == {t[1].id, t[2].id}

    lib = Track(source_type="spotify", title="Rain", artist="Kerri Chandler", has_local_file=True)
    db.add(lib)
    db.commit()
    found = client.get(f"/api/sets/{sid}/material", params={"q": "kerri"}).json()["items"]
    assert [it["track"]["id"] for it in found] == [lib.id]
    assert found[0]["from_playlist"] is False and found[0]["in_set"] is False


def test_materiale_senza_playlist(client_db):
    client, db = client_db
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.get(f"/api/sets/{sid}/material").json()
    assert doc["playlist_id"] is None and doc["items"] == []
