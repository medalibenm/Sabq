"""Login endpoints (docs/architecture.md#outputs): accounts by invitation, email + password."""

import asyncio
import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from sabq.api.deps import DB, AppSettings, LoggedIn, json_only
from sabq.auth import mail, service
from sabq.auth.passwords import hash_password, needs_rehash, policy_error, verify_password
from sabq.auth.ratelimit import FailureLimiter
from sabq.db.models import Organisation, User
from sabq.settings import Settings, get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
writes = [Depends(json_only)]


@lru_cache
def limiter() -> FailureLimiter:
    settings = get_settings()
    return FailureLimiter(settings.login_max_failures, settings.login_failure_window_s)


# --- shapes ----------------------------------------------------------------------------------


class OrganisationOut(BaseModel):
    slug: str
    name: str
    status: str


class MeOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    platform_admin: bool
    organisation: OrganisationOut


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class InviteIn(BaseModel):
    email: str = Field(max_length=320)
    role: str = Field(pattern="^(owner|admin|editor|viewer)$")
    display_name: str = Field(default="", max_length=200)
    organisation: str | None = Field(
        default=None, description="Organisation slug; Sabq team only (default: your own)"
    )


class InviteOut(BaseModel):
    email: str
    role: str
    status: str
    email_sent: bool


class AcceptIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=1024)
    display_name: str | None = Field(default=None, max_length=200)


class ForgotIn(BaseModel):
    email: str = Field(max_length=320)


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=1024)


def me_out(user: User, organisation: Organisation) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        platform_admin=user.platform_admin,
        organisation=OrganisationOut(
            slug=organisation.slug, name=organisation.name, status=organisation.status
        ),
    )


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=int(settings.session_ttl_days * 86400),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


async def _checked_hash(password: str) -> str:
    error = policy_error(password)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    return await asyncio.to_thread(hash_password, password)


async def _send(settings: Settings, message: mail.Mail) -> bool:
    try:
        await asyncio.to_thread(mail.send, settings, message)
        return True
    except Exception:
        log.exception("email to %s not sent", message.to)
        return False


# --- endpoints -------------------------------------------------------------------------------


@router.post("/login", dependencies=writes)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DB,
    settings: AppSettings,
) -> MeOut:
    keys = (
        f"email:{body.email.strip().lower()}",
        f"ip:{request.client.host if request.client else '-'}",
    )
    if limiter().blocked(*keys):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed attempts, wait")
    user = await db.run_sync(lambda s: service.find_user(s, body.email))
    stored = user.password_hash if user else None
    valid = await asyncio.to_thread(verify_password, stored, body.password)
    if not valid or user.status != "active":
        limiter().fail(*keys)
        log.info("failed login for %s", keys[0])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    limiter().clear(keys[0])
    if needs_rehash(user.password_hash):
        user.password_hash = await asyncio.to_thread(hash_password, body.password)
    token = await db.run_sync(lambda s: service.start_session(s, settings, user))
    await db.commit()
    set_session_cookie(response, settings, token)
    return me_out(user, await db.get(Organisation, user.organisation_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=writes)
async def logout(
    response: Response,
    viewer: LoggedIn,
    db: DB,
    settings: AppSettings,
) -> None:
    await db.run_sync(lambda s: service.end_session(s, viewer.token))
    await db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me")
async def me(viewer: LoggedIn) -> MeOut:
    return me_out(viewer.user, viewer.organisation)


@router.post("/invite", status_code=status.HTTP_201_CREATED, dependencies=writes)
async def invite(
    body: InviteIn,
    viewer: LoggedIn,
    db: DB,
    settings: AppSettings,
) -> InviteOut:
    organisation = viewer.organisation
    if body.organisation and body.organisation != organisation.slug:
        if not viewer.user.platform_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "you can only invite to your own")
        organisation = await db.scalar(
            select(Organisation).where(Organisation.slug == body.organisation)
        )
        if organisation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such organisation")
    if not service.can_invite(viewer.user, organisation.id, body.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "your role cannot invite this role")
    user, token = await db.run_sync(
        lambda s: service.invite(
            s,
            settings,
            organisation=organisation,
            email=body.email,
            role=body.role,
            display_name=body.display_name,
            actor=f"user:{viewer.user.id}",
            inviter_id=viewer.user.id,
        )
    )
    await db.commit()
    sent = await _send(settings, mail.invite_mail(settings, user.email, organisation.name, token))
    return InviteOut(email=user.email, role=user.role, status=user.status, email_sent=sent)


@router.post("/accept-invite", dependencies=writes)
async def accept_invite(
    body: AcceptIn,
    response: Response,
    db: DB,
    settings: AppSettings,
) -> MeOut:
    password_hash = await _checked_hash(body.password)

    def accept(s):
        user = service.redeem(s, "invite", body.token)
        service.activate(s, user, password_hash, body.display_name)
        return user, service.start_session(s, settings, user)

    user, token = await db.run_sync(accept)
    await db.commit()
    set_session_cookie(response, settings, token)
    return me_out(user, await db.get(Organisation, user.organisation_id))


@router.post("/forgot", status_code=status.HTTP_202_ACCEPTED, dependencies=writes)
async def forgot(
    body: ForgotIn,
    db: DB,
    settings: AppSettings,
) -> dict:
    """Always the same answer, so it does not reveal which emails have an account."""
    key = f"reset:{body.email.strip().lower()}"
    if not limiter().blocked(key):
        limiter().fail(key)  # counts requests: at most a few reset emails per window
        started = await db.run_sync(lambda s: service.start_reset(s, settings, body.email))
        await db.commit()
        if started:
            user, token = started
            await _send(settings, mail.reset_mail(settings, user.email, token))
    return {"status": "if this email has an account, a reset link was sent"}


@router.post("/reset", dependencies=writes)
async def reset(
    body: ResetIn,
    response: Response,
    db: DB,
    settings: AppSettings,
) -> MeOut:
    password_hash = await _checked_hash(body.password)

    def do_reset(s):
        user = service.redeem(s, "reset", body.token)
        service.finish_reset(s, user, password_hash)
        return user, service.start_session(s, settings, user)

    user, token = await db.run_sync(do_reset)
    await db.commit()
    set_session_cookie(response, settings, token)
    return me_out(user, await db.get(Organisation, user.organisation_id))
