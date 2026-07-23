import pytest

from app.integrations.soundcloud import SoundCloudInvalidUrl
from app.integrations.soundcloud_audio import (
    SoundCloudAudioError, download_track_audio,
)


class _FakeYDL:
    """YoutubeDL finto: registra le opzioni e simula un download riuscito."""
    last_opts = None

    def __init__(self, opts):
        _FakeYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download):
        assert download is True
        return {"title": "Song", "requested_downloads": [{"filepath": "/dl/Song.mp3"}]}

    def prepare_filename(self, info):
        return "/dl/Song.webm"


def test_download_returns_mp3_path(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", _FakeYDL)
    assert download_track_audio("https://soundcloud.com/a/b", "/dl") == "/dl/Song.mp3"


def test_download_sets_bestaudio_and_mp3_postprocessor(monkeypatch):
    monkeypatch.setattr("yt_dlp.YoutubeDL", _FakeYDL)
    download_track_audio("https://soundcloud.com/a/b", "/dl")
    opts = _FakeYDL.last_opts
    assert opts["format"] == "bestaudio/best"
    assert opts["postprocessors"][0]["key"] == "FFmpegExtractAudio"
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"


def test_download_falls_back_to_prepared_name(monkeypatch):
    class _NoRequested(_FakeYDL):
        def extract_info(self, url, download):
            return {"title": "Song"}  # nessun requested_downloads

    monkeypatch.setattr("yt_dlp.YoutubeDL", _NoRequested)
    assert download_track_audio("https://soundcloud.com/a/b", "/dl") == "/dl/Song.mp3"


def test_download_rejects_empty_dest_dir():
    with pytest.raises(SoundCloudAudioError):
        download_track_audio("https://soundcloud.com/a/b", "")


def test_download_rejects_hostile_url():
    with pytest.raises(SoundCloudInvalidUrl):
        download_track_audio("file:///etc/passwd", "/dl")
