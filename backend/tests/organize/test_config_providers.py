from app.core.config import Settings


def test_provider_settings_default_and_env(monkeypatch):
    # Isola dal .env reale del developer e da eventuali variabili ambientali:
    # il test verifica i DEFAULT della classe, non la macchina su cui gira.
    monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
    monkeypatch.delenv("ACOUSTID_API_KEY", raising=False)
    monkeypatch.delenv("MUSICBRAINZ_USER_AGENT", raising=False)

    s = Settings(_env_file=None)
    assert s.discogs_token == ""
    assert s.acoustid_api_key == ""
    assert s.musicbrainz_user_agent.startswith("Cratory-Organize")

    monkeypatch.setenv("DISCOGS_TOKEN", "tok")
    monkeypatch.setenv("ACOUSTID_API_KEY", "key")
    s2 = Settings(_env_file=None)
    assert s2.discogs_token == "tok"
    assert s2.acoustid_api_key == "key"
