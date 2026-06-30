from app.core.config import Settings


def test_slskd_defaults_empty():
    s = Settings(_env_file=None)
    assert s.slskd_url == ""
    assert s.slskd_api_key == ""
    assert s.slskd_download_dir == ""
