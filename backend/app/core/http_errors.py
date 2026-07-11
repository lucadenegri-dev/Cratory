"""Errori HTTP con codice stabile: il frontend traduce `code` nella lingua
attiva; `message` (inglese) è il fallback leggibile per debug/curl."""
from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, **params) -> HTTPException:
    detail: dict = {"code": code, "message": message}
    if params:
        detail["params"] = params
    return HTTPException(status_code=status_code, detail=detail)
