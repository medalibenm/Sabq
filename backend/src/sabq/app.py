"""FastAPI application (service `app`). Run: uvicorn sabq.app:app

OpenAPI for the frontend: /docs (interactive), /openapi.json; a copy is kept in
docs/openapi.json and checked by the tests.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sabq import __version__
from sabq.api import auth, health, webapp
from sabq.auth.service import AuthError
from sabq.logs import configure_logging
from sabq.settings import get_settings

configure_logging(get_settings().log_level)

app = FastAPI(title="Sabq", version=__version__)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(webapp.router)


@app.exception_handler(AuthError)
async def auth_error(request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)
