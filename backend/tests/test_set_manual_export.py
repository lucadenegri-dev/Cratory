"""Export del set manuale (tappa 5): i formati, e cio' che l'anteprima mostra."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Track


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


def _set_ricco(client, db):
    """Un set con tutto dentro: due tracce (una senza file), un varco, una
    riserva, una sequenza con nome, una alternativa e un appunto."""
    tracce = []
    for i in range(4):
        t = Track(source_type="spotify", title=f"T{i}", artist=f"A{i}", bpm=124.0,
                  camelot_key="8A", duration_seconds=300, has_local_file=(i != 1),
                  local_path=(f"/lib/t{i}.mp3" if i != 1 else None))
        db.add(t)
        tracce.append(t)
    db.commit()
    sid = client.post("/api/sets/manual", json={"name": "Sabato"}).json()["id"]
    doc = client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 0, "track_ids": [tracce[0].id, tracce[1].id]}).json()
    righe = [r for b in doc["blocks"] if b["placement"] == "main" for r in b["rows"]]
    client.patch(f"/api/sets/{sid}/rows/{righe[0]['id']}", json={
        "expected_revision": 1, "note": "apre piano"})
    # La sequenza si crea PRIMA del varco: un varco in mezzo rende le due righe
    # non contigue e il raggruppamento verrebbe (giustamente) rifiutato.
    r = client.post(f"/api/sets/{sid}/blocks", json={
        "expected_revision": 2, "row_ids": [righe[0]["id"], righe[1]["id"]],
        "name": "Apertura"})
    assert r.status_code == 200, r.text
    client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 3, "gap": True, "after_row_id": righe[0]["id"]})
    client.post(f"/api/sets/{sid}/rows", json={
        "expected_revision": 4, "track_ids": [tracce[2].id], "reserve": True})
    r = client.post(f"/api/sets/{sid}/rows/{righe[0]['id']}/alternatives", json={
        "expected_revision": 5, "track_ids": [tracce[3].id]})
    assert r.status_code == 200, r.text
    return sid, tracce


def test_il_testo_elenca_il_percorso_risolto(client_db):
    client, db = client_db
    sid, t = _set_ricco(client, db)
    r = client.post(f"/api/sets/{sid}/export?format=text")
    assert r.status_code == 200, r.text
    testo = r.text
    assert "T0" in testo and "T1" in testo
    assert "T2" not in testo          # la riserva non e' il set


def test_l_m3u8_esclude_i_file_mancanti_e_lo_dice(client_db):
    client, db = client_db
    sid, t = _set_ricco(client, db)
    r = client.post(f"/api/sets/{sid}/export?format=m3u8")
    corpo = r.text
    assert "/lib/t0.mp3" in corpo
    assert "/lib/t1.mp3" not in corpo   # quella traccia non ha file
    assert "1" in corpo                  # il conteggio dichiarato nel commento


def test_la_scheda_di_preparazione_porta_tutto_cio_che_serve_in_cabina(client_db):
    client, db = client_db
    sid, t = _set_ricco(client, db)
    r = client.post(f"/api/sets/{sid}/export?format=prep")
    md = r.text
    assert "Apertura" in md          # la sequenza col suo nome
    assert "apre piano" in md        # l'appunto di riga
    assert "T3" in md                # l'alternativa tenuta da parte
    assert "T1" in md                # la traccia senza file RESTA
    assert "non disponibile" in md   # ...e si dichiara, invece di sparire
    assert "varco" in md             # il varco aperto e' un fatto della serata


def test_l_export_delle_riserve_elenca_solo_quelle(client_db):
    client, db = client_db
    sid, t = _set_ricco(client, db)
    r = client.post(f"/api/sets/{sid}/export?format=reserve")
    corpo = r.text
    assert "T2" in corpo
    assert "T0" not in corpo


def test_un_formato_sconosciuto_si_rifiuta(client_db):
    client, db = client_db
    sid, _ = _set_ricco(client, db)
    assert client.post(f"/api/sets/{sid}/export?format=inventato").status_code == 422


def test_i_formati_del_generato_non_cambiano(client_db):
    """La regressione da evitare: l'export dei set generati passa dallo stesso
    endpoint e non deve accorgersi di niente."""
    client, db = client_db
    from app.models import Setlist, SetlistTrack
    t = Track(source_type="spotify", title="G", artist="A", bpm=124.0,
              camelot_key="8A", duration_seconds=300, has_local_file=True,
              local_path="/lib/g.mp3")
    db.add(t)
    s = Setlist(name="Generato", kind="generated")
    db.add(s)
    db.flush()
    db.add(SetlistTrack(setlist_id=s.id, position=1, track_id=t.id))
    db.commit()
    for fmt in ("text", "csv", "markdown", "m3u8"):
        r = client.post(f"/api/sets/{s.id}/export?format={fmt}")
        assert r.status_code == 200, (fmt, r.text)
        assert "G" in r.text
    # I formati nuovi sono del banco: su un generato non hanno senso.
    r = client.post(f"/api/sets/{s.id}/export?format=prep")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "set_format_not_available"
