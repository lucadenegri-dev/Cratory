from app.organize.core.config import Settings


def test_provider_settings_default_and_env(monkeypatch):
    # Isola dal .env reale del developer e da eventuali variabili ambientali:
    # il test verifica i DEFAULT della classe, non la macchina su cui gira.
    monkeypatch.delenv("DJORG_DISCOGS_TOKEN", raising=False)
    monkeypatch.delenv("DJORG_ACOUSTID_API_KEY", raising=False)
    monkeypatch.delenv("DJORG_MUSICBRAINZ_USER_AGENT", raising=False)

    s = Settings(_env_file=None)
    assert s.discogs_token is None
    assert s.acoustid_api_key is None
    assert s.musicbrainz_user_agent.startswith("Sortory")

    monkeypatch.setenv("DJORG_DISCOGS_TOKEN", "tok")
    monkeypatch.setenv("DJORG_ACOUSTID_API_KEY", "key")
    s2 = Settings(_env_file=None)
    assert s2.discogs_token == "tok"
    assert s2.acoustid_api_key == "key"
