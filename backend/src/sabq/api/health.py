"""Service health. Per-source health is added in M7."""

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from sabq import __version__
from sabq.db.session import get_engine

router = APIRouter()


@router.get("/health.json")
async def health(response: Response) -> dict:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": __version__,
        "database": database,
    }
