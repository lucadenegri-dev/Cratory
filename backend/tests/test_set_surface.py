"""La superficie HTTP dei set dopo la rimozione del generatore (2026-09-19).

Non un test di regressione qualunque: e' l'elenco di cio' che esiste e di cio'
che NON deve tornare a esistere. Un endpoint di generazione che riappare qui si
vede subito.
"""
from app.main import app

ATTESI = {
    ("POST", "/api/sets/manual"),
    ("GET", "/api/sets"),
    ("GET", "/api/sets/{setlist_id}/manual"),
    ("GET", "/api/sets/{setlist_id}/material"),
    ("PATCH", "/api/sets/{setlist_id}"),
    ("DELETE", "/api/sets/{setlist_id}"),
    ("POST", "/api/sets/{setlist_id}/export"),
}

SPARITI = {
    ("POST", "/api/sets/generate-async"),
    ("GET", "/api/sets/generate-status"),
    ("GET", "/api/sets/{setlist_id}"),
    ("POST", "/api/sets/{setlist_id}/tracks"),
    ("DELETE", "/api/sets/{setlist_id}/tracks/{position}"),
    ("POST", "/api/sets/{setlist_id}/tracks/{position}/move"),
    ("POST", "/api/sets/{setlist_id}/tracks/{position}/replace"),
    ("POST", "/api/sets/{setlist_id}/alternatives"),
}


def _rotte(routes=None) -> set[tuple[str, str]]:
    """Le rotte (metodo, path) dell'app.

    Ricorsiva perche' questa versione di FastAPI NON appiattisce i router inclusi
    dentro `app.routes`: li avvolge in oggetti con `original_router`. Leggere solo
    il primo livello darebbe un insieme quasi vuoto, e i due test qui sotto
    passerebbero senza guardare niente.
    """
    out: set[tuple[str, str]] = set()
    for r in app.routes if routes is None else routes:
        interno = getattr(r, "original_router", None)
        if interno is not None:
            out |= _rotte(interno.routes)
            continue
        for metodo in (getattr(r, "methods", None) or set()) - {"HEAD", "OPTIONS"}:
            out.add((metodo, r.path))
    return out


def test_il_lettore_di_rotte_vede_davvero_l_app():
    """Se la ricorsione si rompesse, gli altri due test diventerebbero vacui:
    un insieme vuoto soddisfa «nessuno di questi endpoint esiste»."""
    rotte = _rotte()
    assert len(rotte) > 100, len(rotte)
    assert ("GET", "/api/sets") in rotte


def test_la_superficie_dei_set_e_quella_del_banco():
    rotte = _rotte()
    assert ATTESI <= rotte, ATTESI - rotte


def test_il_vecchio_generatore_non_ha_piu_endpoint():
    rotte = _rotte()
    assert not (SPARITI & rotte), SPARITI & rotte


def test_le_colonne_della_curatela_non_esistono_piu(db):
    from app.models import Setlist, SetlistTrack
    assert not hasattr(Setlist, "curation")
    assert not hasattr(SetlistTrack, "mood_tags")
    assert not hasattr(SetlistTrack, "ai_reason")


def test_un_database_vecchio_perde_le_colonne_all_avvio(tmp_path):
    """Il DB di chi aggiorna deve ritrovarsi senza quelle colonne. Si parte
    dallo schema CORRENTE e si ri-aggiungono a mano le tre colonne morte: e'
    esattamente la forma che ha il database di chi installa l'aggiornamento."""
    from sqlalchemy import create_engine, inspect, text

    from app.db import Base, ensure_schema
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    from sqlalchemy.orm import sessionmaker

    from app.models import Setlist

    eng = create_engine(f"sqlite:///{tmp_path / 'vecchio.db'}")
    Base.metadata.create_all(eng)
    # Il set si inserisce con l'ORM: elencare a mano le colonne NOT NULL
    # renderebbe questo test fragile a ogni colonna nuova su `setlists`.
    with sessionmaker(bind=eng)() as sess:
        sess.add(Setlist(name="vecchio", kind="generated"))
        sess.commit()
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE setlists ADD COLUMN curation JSON"))
        conn.execute(text("ALTER TABLE setlist_tracks ADD COLUMN mood_tags JSON"))
        conn.execute(text("ALTER TABLE setlist_tracks ADD COLUMN ai_reason TEXT"))

    ensure_schema(eng)

    assert "curation" not in {c["name"] for c in inspect(eng).get_columns("setlists")}
    righe = {c["name"] for c in inspect(eng).get_columns("setlist_tracks")}
    assert "mood_tags" not in righe and "ai_reason" not in righe
    # Il set c'e' ancora: si tolgono colonne, non i dati dell'utente.
    with eng.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM setlists")).scalar_one() == 1


def test_la_migrazione_delle_colonne_si_puo_rieseguire(tmp_path):
    """Idempotenza: `ensure_schema` gira a ogni avvio."""
    from sqlalchemy import create_engine

    from app.db import Base, ensure_schema
    import app.models  # noqa: F401
    import app.organize.models  # noqa: F401

    eng = create_engine(f"sqlite:///{tmp_path / 'due-volte.db'}")
    Base.metadata.create_all(eng)
    ensure_schema(eng)
    ensure_schema(eng)
