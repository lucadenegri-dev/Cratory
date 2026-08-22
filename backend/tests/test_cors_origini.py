"""Le origini ammesse dal CORS. In un bundle la pagina non arriva piu' da
localhost:3000, e senza l'origin del webview non riesce una sola chiamata."""
from app.core.config import Settings


def _origini(s: Settings) -> list[str]:
    """Stessa scomposizione che fa main.py per costruire allow_origins."""
    return [o.strip() for o in s.frontend_origin.split(",") if o.strip()]


def test_le_origini_di_sviluppo_restano():
    origini = _origini(Settings())
    assert "http://localhost:3000" in origini
    assert "http://localhost:3001" in origini


def test_c_e_l_origin_del_webview():
    """Il bundle desktop serve la pagina da uno schema suo, non da http."""
    assert "tauri://localhost" in _origini(Settings())


def test_l_utente_puo_ancora_sovrascrivere_tutto():
    """Chi mette il proprio elenco non se lo vede allungare d'ufficio."""
    s = Settings(frontend_origin="http://192.168.1.10:3000")
    assert _origini(s) == ["http://192.168.1.10:3000"]
