from app.core.config import Settings


def test_slskd_defaults_empty(monkeypatch):
    # Isola dal vero .env dello sviluppatore: app/main.py ora fa
    # load_dotenv(backend/.env) (serve ad ANTHROPIC_API_KEY per l'SDK
    # Anthropic), quindi da quando il modulo e' stato importato queste
    # variabili sono anche nel process env — _env_file=None da solo non basta più.
    for var in ("SLSKD_URL", "SLSKD_API_KEY", "SLSKD_DOWNLOAD_DIR"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.slskd_url == ""
    assert s.slskd_api_key == ""
    assert s.slskd_download_dir == ""
