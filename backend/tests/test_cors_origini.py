"""Le origini ammesse dal CORS. In un bundle la pagina non arriva piu' da
localhost:3000, e senza l'origin del webview non riesce una sola chiamata."""
from app.core.config import Settings
from app.main import WEBVIEW_ORIGIN, origini_ammesse


def _origini(s: Settings) -> list[str]:
    """Chiama la funzione vera di main.py invece di riscriverla: una copia
    della logica qui si disallinea al primo cambiamento, ed e' successo."""
    return origini_ammesse(s.frontend_origin)


def test_le_origini_di_sviluppo_restano():
    origini = _origini(Settings())
    assert "http://localhost:3000" in origini
    assert "http://localhost:3001" in origini


def test_c_e_l_origin_del_webview():
    """Il bundle desktop serve la pagina da uno schema suo, non da http."""
    assert "tauri://localhost" in _origini(Settings())


def test_l_utente_sovrascrive_le_sue_origini():
    """Chi mette il proprio elenco lo ottiene: le origini di sviluppo spariscono."""
    origini = _origini(Settings(frontend_origin="http://192.168.1.10:3000"))
    assert "http://192.168.1.10:3000" in origini
    assert "http://localhost:3000" not in origini


def test_il_webview_resta_ammesso_anche_con_una_lista_personale():
    """Non e' una preferenza: e' il modo in cui il bundle parla con se stesso.

    Un .env scritto prima che l'app desktop esistesse elenca solo le porte dei
    browser, e senza questa unione l'app si aprirebbe muta — ogni chiamata
    bloccata dal CORS e nessun messaggio che lo spieghi. E' successo davvero."""
    assert WEBVIEW_ORIGIN in _origini(Settings(frontend_origin="http://192.168.1.10:3000"))
    assert WEBVIEW_ORIGIN in _origini(Settings(frontend_origin=""))
