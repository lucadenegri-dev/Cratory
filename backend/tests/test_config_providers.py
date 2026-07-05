from app.core.config import Settings


def test_provider_settings_default_and_env(monkeypatch):
    s = Settings()
    assert s.discogs_token is None
    assert s.acoustid_api_key is None
    assert s.musicbrainz_user_agent.startswith("DjOrganizer")

    monkeypatch.setenv("DJORG_DISCOGS_TOKEN", "tok")
    monkeypatch.setenv("DJORG_ACOUSTID_API_KEY", "key")
    s2 = Settings()
    assert s2.discogs_token == "tok"
    assert s2.acoustid_api_key == "key"
