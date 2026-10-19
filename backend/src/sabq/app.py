"""FastAPI application (service `app`). Run: uvicorn sabq.app:app"""

from fastapi import FastAPI

from sabq import __version__
from sabq.api import health
from sabq.logs import configure_logging
from sabq.settings import get_settings

configure_logging(get_settings().log_level)

app = FastAPI(title="Sabq", version=__version__)
app.include_router(health.router)
