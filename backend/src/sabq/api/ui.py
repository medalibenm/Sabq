"""Test UI for the owner (plan "Test UI"): one static page at /ui, not the final frontend, which
Caddy serves from `frontend/`. It only calls the public API (login happens in the page)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)
PAGE = Path(__file__).parent / "static" / "ui.html"


@router.get("/ui")
async def ui() -> FileResponse:
    return FileResponse(PAGE, media_type="text/html", headers={"Cache-Control": "no-store"})
