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
