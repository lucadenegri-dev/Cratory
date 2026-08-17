from fastapi import APIRouter

from app.core import runtime_settings
from app.integrations.llm import DEFAULT_MODEL, llm_configured

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def status():
    return {
        "configured": llm_configured(),
        "model": (runtime_settings.ai_model() or DEFAULT_MODEL) if llm_configured() else None,
    }
