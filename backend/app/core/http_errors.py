"""Errori HTTP con codice stabile: il frontend traduce `code` nella lingua
attiva; `message` (inglese) è il fallback leggibile per debug/curl."""
from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str,
              headers: dict | None = None, **params) -> HTTPException:
    """`headers` (es. Cache-Control) non entra nel body: FastAPI li applica
    alla risposta via `HTTPException.headers`, la forma di `detail` resta
    identica agli altri errori."""
    detail: dict = {"code": code, "message": message}
    if params:
        detail["params"] = params
    return HTTPException(status_code=status_code, detail=detail, headers=headers)
