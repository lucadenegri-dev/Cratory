"""La chiave AI e' una sola: ANTHROPIC_API_KEY, con fallback su AI_API_KEY
(retrocompatibilita' degli .env esistenti). Precedenza a ANTHROPIC_API_KEY."""

from app.core.config import Settings
from app.organize.services import ai_tags


def _fresh_settings(monkeypatch, **env):
    for k in ("ANTHROPIC_API_KEY", "AI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # _env_file=None: il test non deve leggere il backend/.env reale dello sviluppatore
    return Settings(_env_file=None)


def test_anthropic_api_key_letta(monkeypatch):
    assert _fresh_settings(monkeypatch, ANTHROPIC_API_KEY="nuova").ai_api_key == "nuova"


def test_fallback_su_ai_api_key(monkeypatch):
    assert _fresh_settings(monkeypatch, AI_API_KEY="vecchia").ai_api_key == "vecchia"


def test_precedenza_ad_anthropic(monkeypatch):
    s = _fresh_settings(monkeypatch, ANTHROPIC_API_KEY="nuova", AI_API_KEY="vecchia")
    assert s.ai_api_key == "nuova"


def test_senza_chiavi_vuota(monkeypatch):
    assert _fresh_settings(monkeypatch).ai_api_key == ""


def test_ai_tags_usa_il_setting_condiviso(monkeypatch):
    """is_configured() deve leggere settings.ai_api_key, non os.environ:
    altrimenti un .env con solo AI_API_KEY lascerebbe i tag AI spenti."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ai_api_key", "test")
    assert ai_tags.is_configured() is True
    monkeypatch.setattr(settings, "ai_api_key", "")
    assert ai_tags.is_configured() is False
