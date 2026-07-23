import pytest

from app.integrations.soundcloud import SoundCloudInvalidUrl, validate_soundcloud_url


def test_validate_accepts_soundcloud_url():
    url = "https://soundcloud.com/artist/track"
    assert validate_soundcloud_url(url) == url


def test_validate_rejects_file_scheme():
    with pytest.raises(SoundCloudInvalidUrl):
        validate_soundcloud_url("file:///etc/passwd")


def test_validate_rejects_foreign_host():
    with pytest.raises(SoundCloudInvalidUrl):
        validate_soundcloud_url("https://evil.example.com/track")
