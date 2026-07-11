"""api_error: HTTPException con detail strutturato {code, message, params?}."""
from app.core.http_errors import api_error


def test_detail_strutturato():
    exc = api_error(404, "playlist_not_found", "Playlist not found")
    assert exc.status_code == 404
    assert exc.detail == {"code": "playlist_not_found", "message": "Playlist not found"}


def test_params_opzionali():
    exc = api_error(409, "job_running", "Job already running", job="index")
    assert exc.detail["params"] == {"job": "index"}
