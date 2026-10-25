"""Test UI for the owner (plan "Test UI"): one static page at /ui, not the final frontend.
It only calls the public API, so it needs nothing of its own (login happens in the page)."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(include_in_schema=False)
PAGE = Path(__file__).parent / "static" / "ui.html"


@router.get("/ui")
@router.get("/accept-invite")  # links in invite emails
@router.get("/reset-password")  # links in password reset emails
async def ui() -> FileResponse:
    return FileResponse(PAGE, media_type="text/html", headers={"Cache-Control": "no-store"})


@router.get("/")
async def home() -> RedirectResponse:
    return RedirectResponse("/ui")
