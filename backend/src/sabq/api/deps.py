"""Request dependencies: database session, the logged-in user, role checks.

CSRF: the session cookie is `SameSite=Lax`, and every state-changing request must send
`Content-Type: application/json`, which a cross-site form cannot do without a CORS preflight
(and no CORS is enabled). See decisions 2026-10-25.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sabq.auth.service import digest, now
from sabq.db.models import Organisation, User, UserSession
from sabq.db.session import get_sessionmaker
from sabq.settings import Settings, get_settings

SESSION_TOUCH = timedelta(minutes=5)  # how often a used session is extended (fewer writes)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


DB = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def json_only(request: Request) -> None:
    kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if kind != "application/json":
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "send JSON (Content-Type: application/json)"
        )


@dataclass
class Viewer:
    user: User
    organisation: Organisation
    token: str


def _not_logged_in() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")


async def current(request: Request, db: DB, settings: AppSettings) -> Viewer:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _not_logged_in()
    row = await db.get(UserSession, digest(token))
    moment = now()
    if row is None or row.expires_at <= moment:
        raise _not_logged_in()
    user = await db.get(User, row.user_id)
    if user is None or user.status != "active":
        raise _not_logged_in()
    organisation = await db.get(Organisation, user.organisation_id)
    if moment - row.last_seen_at > SESSION_TOUCH:  # sliding expiry
        row.last_seen_at = moment
        row.expires_at = moment + timedelta(days=settings.session_ttl_days)
        await db.commit()
    return Viewer(user, organisation, token)


LoggedIn = Annotated[Viewer, Depends(current)]


def roles(*allowed: str):
    """The logged-in user must have one of these roles in their organisation."""

    async def check(viewer: LoggedIn) -> Viewer:
        if viewer.user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "your role does not allow this")
        return viewer

    return check


async def platform_admin(viewer: LoggedIn) -> Viewer:
    if not viewer.user.platform_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sabq team only")
    return viewer
