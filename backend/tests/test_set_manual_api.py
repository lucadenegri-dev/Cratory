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
    r = client.post("/api/sets/manual", json={"playlist_ids": [pl.id]})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["kind"] == "manual" and doc["name"] == "Deep"
    assert [x["name"] for x in doc["sources"]] == ["Deep"] and doc["revision"] == 0
    assert doc["blocks"] == [] and doc["track_count"] == 0
    assert client.get(f"/api/sets/{doc['id']}/manual").json() == doc
    assert client.get("/api/sets").json()[0]["kind"] == "manual"


def test_crea_con_playlist_inesistente(client_db):
    client, _ = client_db
    r = client.post("/api/sets/manual", json={"playlist_ids": [999]})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "playlist_not_found"


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
    # Costruito a mano: `generate_set` e' sparito il 2026-09-19. Cio' che il
    # test verifica — le rotte manuali rifiutano un set generato — vale finche'
    # un set `generated` puo' stare in archivio.
    from app.models import Setlist

    generated = Setlist(name="Vecchio", kind="generated", generated_by="algorithmic")
    db.add(generated)
    db.commit()
    r = client.get(f"/api/sets/{generated.id}/manual")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_not_manual"


def test_rinomina_e_cancellazione_restano_aperte_su_un_set_manuale(client_db):
    """Rename e delete del set intero non assumono la forma generata (non
    toccano posizioni/`st.track`): un set manuale deve poterle usare — la
    cancellazione in particolare e' l'unico modo che l'utente ha per buttare
    via un set manuale creato per errore (nessun editor classico da aprire)."""
    client, db = client_db
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    r = client.patch(f"/api/sets/{sid}", json={"name": "Rinominato"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Rinominato"
    r = client.delete(f"/api/sets/{sid}")
    assert r.status_code == 204, r.text
    assert client.get(f"/api/sets/{sid}/manual").json()["detail"]["code"] == "set_not_found"


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

    setlist = create_manual_set(db, name="M", playlist_ids=[])
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
    sid = client.post("/api/sets/manual", json={"playlist_ids": [pl.id]}).json()["id"]
    client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id, extra.id]})

    doc = client.get(f"/api/sets/{sid}/material").json()
    assert [x["name"] for x in doc["sources"]] == ["Deep"]
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
    assert doc["sources"] == [] and doc["items"] == []


# --- Tappa 2: alternative, riserva, materiale ---------------------------------


def test_alternative_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=4)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id]}).json()
    row = _rows(doc)[0]

    r = client.post(f"/api/sets/{sid}/rows/{row['id']}/alternatives",
                    json={"expected_revision": 1, "track_ids": [t[1].id, t[2].id]})
    assert r.status_code == 200, r.text
    doc = r.json()
    alts = _rows(doc)[0]["alternatives"]
    assert [a["track"]["id"] for a in alts] == [t[1].id, t[2].id]
    assert doc["revision"] == 2

    r = client.post(f"/api/sets/{sid}/rows/{row['id']}/alternatives/{alts[0]['id']}/choose",
                    json={"expected_revision": 2})
    riga = _rows(r.json())[0]
    assert riga["track"]["id"] == t[1].id
    assert t[0].id in [a["track"]["id"] for a in riga["alternatives"]]

    alt_id = riga["alternatives"][0]["id"]
    r = client.delete(f"/api/sets/{sid}/rows/{row['id']}/alternatives/{alt_id}",
                      params={"expected_revision": 3})
    assert r.status_code == 200
    assert alt_id not in [a["id"] for a in _rows(r.json())[0]["alternatives"]]

    r = client.delete(f"/api/sets/{sid}/rows/{row['id']}/alternatives/999999",
                      params={"expected_revision": 4})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "set_alternative_not_found"


def test_riserva_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=3)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    r = client.post(f"/api/sets/{sid}/rows",
                    json={"expected_revision": 0, "track_ids": [t[0].id], "reserve": True})
    doc = r.json()
    assert _rows(doc) == []
    assert [x["track"]["id"] for x in doc["reserve"]] == [t[0].id]
    assert doc["track_count"] == 0  # la riserva non e' il set

    riga = doc["reserve"][0]
    r = client.post(f"/api/sets/{sid}/rows/{riga['id']}/move",
                    json={"expected_revision": 1, "position": 1, "to_reserve": False})
    doc = r.json()
    assert [x["track"]["id"] for x in _rows(doc)] == [t[0].id]
    assert doc["reserve"] == [] and doc["track_count"] == 1


def test_materiale_distingue_percorso_e_riserva(client_db):
    client, db = client_db
    pl, t = _seed(db, n=3)
    sid = client.post("/api/sets/manual", json={"playlist_ids": [pl.id]}).json()["id"]
    client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id]})
    client.post(f"/api/sets/{sid}/rows",
                json={"expected_revision": 1, "track_ids": [t[1].id], "reserve": True})

    items = client.get(f"/api/sets/{sid}/material").json()["items"]
    by_id = {it["track"]["id"]: it for it in items}
    assert by_id[t[0].id]["in_set"] is True and by_id[t[0].id]["in_reserve"] is False
    assert by_id[t[1].id]["in_set"] is False and by_id[t[1].id]["in_reserve"] is True

    solo_riserva = client.get(f"/api/sets/{sid}/material",
                              params={"reserved": "true"}).json()["items"]
    assert [it["track"]["id"] for it in solo_riserva] == [t[1].id]


# --- Sequenze, banco, annulla e ripeti (tappa 3) -------------------------------


def test_sequenze_e_banco_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=4)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [x.id for x in t]}).json()
    righe = _rows(doc)

    r = client.post(f"/api/sets/{sid}/blocks", json={
        "expected_revision": 1, "row_ids": [righe[1]["id"], righe[2]["id"]], "name": "Salita"})
    assert r.status_code == 200, r.text
    doc = r.json()
    main = [b for b in doc["blocks"] if b["placement"] == "main"]
    assert [b["name"] for b in main] == [None, "Salita", None]

    blocco = main[1]["id"]
    r = client.post(f"/api/sets/{sid}/blocks/{blocco}/move",
                    json={"expected_revision": 2, "position": 1, "to_bench": True})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert [b["name"] for b in doc["blocks"] if b["placement"] == "bench"] == ["Salita"]
    assert [x["track"]["id"] for x in _rows(doc)] == [t[0].id, t[3].id]
    # Il banco non e' il percorso: non conta nel totale del set.
    assert doc["track_count"] == 2

    r = client.patch(f"/api/sets/{sid}/blocks/{blocco}", json={"expected_revision": 3, "name": "Idea"})
    assert [b["name"] for b in r.json()["blocks"] if b["placement"] == "bench"] == ["Idea"]

    r = client.patch(f"/api/sets/{sid}/blocks/999999", json={"expected_revision": 4, "name": "X"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "set_block_not_found"


def test_separare_una_sequenza_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=4)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [x.id for x in t]}).json()
    righe = _rows(doc)
    doc = client.post(f"/api/sets/{sid}/blocks", json={
        "expected_revision": 1, "row_ids": [righe[0]["id"], righe[1]["id"]], "name": "A"}).json()
    blocco = [b for b in doc["blocks"] if b["name"] == "A"][0]["id"]

    r = client.post(f"/api/sets/{sid}/blocks/{blocco}/split", json={"expected_revision": 2})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert [b["name"] for b in doc["blocks"]] == [None]
    assert [x["track"]["id"] for x in _rows(doc)] == [x.id for x in t]


def test_annulla_e_ripeti_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=3)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id]}).json()
    assert doc["can_undo"] is True and doc["can_redo"] is False

    r = client.post(f"/api/sets/{sid}/undo", json={"expected_revision": 1})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert _rows(doc) == []
    assert doc["can_undo"] is False and doc["can_redo"] is True
    assert doc["revision"] == 2  # cresce anche annullando

    r = client.post(f"/api/sets/{sid}/undo", json={"expected_revision": 2})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_nothing_to_undo"

    r = client.post(f"/api/sets/{sid}/redo", json={"expected_revision": 2})
    assert [x["track"]["id"] for x in _rows(r.json())] == [t[0].id]

    r = client.post(f"/api/sets/{sid}/redo", json={"expected_revision": 3})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "set_nothing_to_redo"


# --- Passaggi e tempo di cabina (tappa 4) --------------------------------------


def test_passaggi_e_appunti_di_coppia_via_http(client_db):
    client, db = client_db
    _, t = _seed(db, n=3)   # tutte a 124 BPM
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]}).json()
    assert len(doc["transitions"]) == 1
    passaggio = doc["transitions"][0]
    assert passaggio["from_track_id"] == t[0].id and passaggio["to_track_id"] == t[1].id
    assert passaggio["bpm_percent"] == 0.0        # stesso tempo: niente pitch
    assert passaggio["note"] is None

    r = client.put(f"/api/sets/{sid}/pair-notes", json={
        "expected_revision": 1, "from_track_id": t[0].id, "to_track_id": t[1].id,
        "note": "entra sul break"})
    assert r.status_code == 200, r.text
    assert r.json()["transitions"][0]["note"] == "entra sul break"

    r = client.put(f"/api/sets/{sid}/pair-notes", json={
        "expected_revision": 2, "from_track_id": 999999, "to_track_id": t[1].id, "note": "x"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "manual_set_error"


def test_un_varco_spezza_il_passaggio(client_db):
    """Regola della spec: finche' il varco e' aperto, le tracce ai suoi lati non
    sono vicine e nessuna compatibilita' si calcola fra loro."""
    client, db = client_db
    _, t = _seed(db, n=2)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]}).json()
    prima = _rows(doc)[0]
    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 1, "gap": True, "after_row_id": prima["id"]}).json()
    assert doc["transitions"] == []


def test_la_suono_a_via_http_e_la_patch_parziale(client_db):
    client, db = client_db
    _, t = _seed(db, n=2)
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]}).json()
    riga = _rows(doc)[0]["id"]

    r = client.patch(f"/api/sets/{sid}/rows/{riga}",
                     json={"expected_revision": 1, "play_bpm": 130})
    assert r.status_code == 200, r.text
    assert _rows(r.json())[0]["play_bpm"] == 130.0
    # 124 -> 130 sul primo, il secondo resta a 124: serve pitch all'indietro.
    assert r.json()["transitions"][0]["bpm_from"] == 130.0

    r = client.patch(f"/api/sets/{sid}/rows/{riga}",
                     json={"expected_revision": 2, "note": "solo la nota"})
    assert _rows(r.json())[0]["play_bpm"] == 130.0   # non azzerato dalla PATCH parziale
    assert _rows(r.json())[0]["note"] == "solo la nota"

    r = client.patch(f"/api/sets/{sid}/rows/{riga}",
                     json={"expected_revision": 3, "play_bpm": 999})
    assert r.status_code == 422


def test_la_durata_esce_nel_documento(client_db):
    client, db = client_db
    _, t = _seed(db, n=2)   # due tracce da 300 secondi
    sid = client.post("/api/sets/manual", json={"name": "M"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [x.id for x in t]}).json()
    assert doc["duration"]["seconds"] == 600
    assert doc["duration"]["incomplete"] is False

    riga = _rows(doc)[0]["id"]
    doc = client.patch(f"/api/sets/{sid}/rows/{riga}",
                       json={"expected_revision": 1, "planned_seconds": 120}).json()
    assert _rows(doc)[0]["planned_seconds"] == 120
    assert doc["duration"]["seconds"] == 420

    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 2, "gap": True, "after_row_id": riga}).json()
    assert doc["duration"]["incomplete"] is True and doc["duration"]["open_gaps"] == 1


def test_riempire_un_varco_via_http(client_db):
    client, db = client_db
    pl, t = _seed(db, n=5)
    sid = client.post("/api/sets/manual", json={"playlist_ids": [pl.id]}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows",
                      json={"expected_revision": 0, "track_ids": [t[0].id, t[1].id]}).json()
    prima = _rows(doc)[0]["id"]
    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 1, "gap": True, "after_row_id": prima}).json()
    varco = _rows(doc)[1]["id"]

    r = client.post(f"/api/sets/{sid}/rows/{varco}/fill-gap",
                    json={"expected_revision": 2, "count": 2})
    assert r.status_code == 200, r.text
    righe = _rows(r.json())
    assert len(righe) == 4 and all(x["track"] is not None for x in righe)

    # Annullare riapre il varco: il riempimento e' una revisione sola.
    r = client.post(f"/api/sets/{sid}/undo", json={"expected_revision": 3})
    righe = _rows(r.json())
    assert len(righe) == 3 and righe[1]["slot_kind"] == "gap"


# --- Origini multiple e materiale della bozza (2026-09-19) ---------------------


def test_origini_multiple_via_http(client_db):
    client, db = client_db
    pl_a, t = _seed(db, n=2)
    pl_b = Playlist(platform="spotify", name="Seconda")
    db.add(pl_b)
    db.flush()
    add_track_to_playlist(db, t[0], pl_b, added_by="test")
    db.commit()

    r = client.post("/api/sets/manual", json={"name": "M", "playlist_ids": [pl_a.id]})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert [s["playlist_id"] for s in doc["sources"]] == [pl_a.id]
    sid = doc["id"]

    r = client.post(f"/api/sets/{sid}/sources",
                    json={"expected_revision": 0, "playlist_id": pl_b.id})
    assert r.status_code == 200, r.text
    assert [s["name"] for s in r.json()["sources"]] == ["Deep", "Seconda"]

    r = client.delete(f"/api/sets/{sid}/sources/{pl_a.id}?expected_revision=1")
    assert r.status_code == 200, r.text
    assert [s["playlist_id"] for s in r.json()["sources"]] == [pl_b.id]

    r = client.delete(f"/api/sets/{sid}/sources/{pl_a.id}?expected_revision=2")
    assert r.status_code == 422


def test_il_materiale_di_una_bozza_via_http(client_db):
    client, db = client_db
    pl, t = _seed(db, n=3)
    r = client.get(f"/api/sets/material?playlist_ids={pl.id}")
    assert r.status_code == 200, r.text
    doc = r.json()
    assert len(doc["items"]) == 3
    assert all(item["in_set"] is False for item in doc["items"])
    assert [s["playlist_id"] for s in doc["sources"]] == [pl.id]


def test_rinomina_un_set_a_mano_che_ha_un_varco(client_db):
    """Regressione: la rinomina rispondeva col documento del set GENERATO, che
    su un varco (riga senza traccia) andava in 500 — e intanto il nome era gia'
    stato scritto, quindi il client vedeva un errore su un'operazione riuscita."""
    client, db = client_db
    _, t = _seed(db)
    sid = client.post("/api/sets/manual", json={"name": "Sabato"}).json()["id"]
    r = client.post(f"/api/sets/{sid}/rows", json={"expected_revision": 0, "track_ids": [t[0].id]})
    assert r.status_code == 200, r.text
    riga = _rows(r.json())[0]
    r = client.post(f"/api/sets/{sid}/rows",
                    json={"expected_revision": 1, "gap": True, "after_row_id": riga["id"]})
    assert r.status_code == 200, r.text
    assert [x["slot_kind"] for x in _rows(r.json())] == ["track", "gap"]

    r = client.patch(f"/api/sets/{sid}", json={"name": "  Domenica  "})
    assert r.status_code == 200, r.text
    # Il riepilogo, come GET /api/sets: il varco non conta fra le tracce.
    assert r.json()["name"] == "Domenica"
    assert r.json()["kind"] == "manual" and r.json()["track_count"] == 1
    assert client.get("/api/sets").json()[0]["name"] == "Domenica"


def test_rinomina_rifiuta_un_nome_di_soli_spazi(client_db):
    """Prima passava: `min_length` guardava la stringa grezza, poi il servizio
    la ripuliva, e in archivio restava un set senza nome."""
    client, _ = client_db
    sid = client.post("/api/sets/manual", json={"name": "Sabato"}).json()["id"]
    assert client.patch(f"/api/sets/{sid}", json={"name": ""}).status_code == 422
    assert client.patch(f"/api/sets/{sid}", json={"name": "   "}).status_code == 422
    assert client.get("/api/sets").json()[0]["name"] == "Sabato"
