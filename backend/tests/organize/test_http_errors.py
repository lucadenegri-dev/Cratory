"""api_error: HTTPException con detail strutturato {code, message, params?}."""
from app.organize.core.http_errors import api_error


def test_detail_strutturato():
    exc = api_error(404, "plan_draft_missing", "No draft plan")
    assert exc.status_code == 404
    assert exc.detail == {"code": "plan_draft_missing", "message": "No draft plan"}


def test_params_opzionali():
    exc = api_error(409, "job_running", "Job already running", job="scan")
    assert exc.detail["params"] == {"job": "scan"}
