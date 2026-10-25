"""FastAPI application (service `app`). Run: uvicorn sabq.app:app

OpenAPI for the frontend: /docs (interactive), /openapi.json; a copy is kept in
docs/openapi.json and checked by the tests.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sabq import __version__
from sabq.api import admin, auth, health, stream, ui, webapp
from sabq.auth.service import AuthError
from sabq.db.session import get_engine
from sabq.logs import configure_logging
from sabq.settings import get_settings

configure_logging(get_settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.broadcaster = stream.make_broadcaster()  # LISTEN for new articles (SSE)
    app.state.broadcaster.start()
    yield
    await app.state.broadcaster.stop()
    await get_engine().dispose()  # close pooled connections cleanly on shutdown


app = FastAPI(title="Sabq", version=__version__, lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(webapp.router)
app.include_router(stream.router)
app.include_router(admin.router)
app.include_router(ui.router)


@app.exception_handler(AuthError)
async def auth_error(request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)
