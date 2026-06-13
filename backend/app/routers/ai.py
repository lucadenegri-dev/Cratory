from fastapi import APIRouter

from app.core.config import settings
from app.integrations.llm import DEFAULT_MODEL, llm_configured

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def status():
    return {
        "configured": llm_configured(),
        "model": (settings.ai_model or DEFAULT_MODEL) if llm_configured() else None,
    }
