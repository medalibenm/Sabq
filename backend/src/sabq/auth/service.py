"""Accounts, invitations, password resets and sessions (docs/architecture.md#outputs).

Synchronous and session-based, so the CLI calls it directly and the API through
`AsyncSession.run_sync`. Tokens (invite, reset, session) are random, sent to the user once, and
stored only as SHA-256 hashes. Password hashing is the caller's job (it is slow on purpose, and
the API runs it off the event loop).
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from sabq.audit import record
from sabq.db.models import AuditEvent, AuthToken, Organisation, User, UserSession
from sabq.settings import Settings

ROLES = ("owner", "admin", "editor", "viewer")
# who may invite which roles (a platform admin may invite any role into any organisation)
INVITABLE = {"owner": set(ROLES), "admin": {"admin", "editor", "viewer"}}


class AuthError(Exception):
    """A request the user can fix (shown as a 4xx with this message)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now() -> datetime:
    return datetime.now(UTC)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, digest(token)


def find_user(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def can_invite(inviter: User, organisation_id: int, role: str) -> bool:
    if inviter.platform_admin:
        return True
    return inviter.organisation_id == organisation_id and role in INVITABLE.get(inviter.role, set())


# --- invitations -----------------------------------------------------------------------------


def invite(
    session: Session,
    settings: Settings,
    *,
    organisation: Organisation,
    email: str,
    role: str,
    display_name: str,
    actor: str,
    inviter_id: int | None = None,
) -> tuple[User, str]:
    """Create (or re-invite) an invited user; returns the user and the one-time invite token.
    Earlier invite links of that user stop working."""
    if role not in ROLES:
        raise AuthError(f"unknown role {role!r}")
    email = email.strip()
    if "@" not in email or len(email) > 320:
        raise AuthError("invalid email")
    user = find_user(session, email)
    if user is not None and (user.status != "invited" or user.organisation_id != organisation.id):
        raise AuthError("a user with this email already exists", status=409)
    if user is None:
        user = User(
            organisation_id=organisation.id, email=email, display_name=display_name, role=role
        )
        session.add(user)
        session.flush()
    else:
        user.role, user.display_name = role, display_name or user.display_name
    _expire_tokens(session, user.id, "invite")
    token, token_hash = new_token()
    session.add(
        AuthToken(
            user_id=user.id,
            kind="invite",
            token_hash=token_hash,
            expires_at=now() + timedelta(hours=settings.invite_ttl_hours),
        )
    )
    record(
        session,
        actor,
        "user.invited",
        "user",
        user.id,
        {"email": email, "role": role},
        organisation_id=organisation.id,
        user_id=inviter_id,
    )
    return user, token


def _valid_token(session: Session, kind: str, token: str) -> tuple[AuthToken, User]:
    row = session.scalar(
        select(AuthToken).where(AuthToken.token_hash == digest(token), AuthToken.kind == kind)
    )
    if row is None or row.used_at is not None or row.expires_at <= now():
        raise AuthError("this link is invalid or has expired", status=400)
    user = session.get(User, row.user_id)
    if user.status == "disabled":
        raise AuthError("this link is invalid or has expired", status=400)
    return row, user


def peek(session: Session, kind: str, token: str) -> User:
    """The user of a valid token, which stays unused (the page behind an email link)."""
    return _valid_token(session, kind, token)[1]


def redeem(session: Session, kind: str, token: str) -> User:
    """The user a valid, unused, unexpired token belongs to; the token is used up."""
    row, user = _valid_token(session, kind, token)
    row.used_at = now()
    return user


def inviter_name(session: Session, user: User) -> str | None:
    """Who sent the latest invitation (None when it came from the CLI)."""
    inviter_id = session.scalar(
        select(AuditEvent.user_id)
        .where(AuditEvent.action == "user.invited", AuditEvent.entity_id == str(user.id))
        .order_by(AuditEvent.id.desc())
        .limit(1)
    )
    inviter = session.get(User, inviter_id) if inviter_id else None
    return (inviter.display_name or None) if inviter else None


def cancel_invite(session: Session, user: User, actor: User) -> None:
    """An unaccepted invitation disappears, so the same email can be invited again."""
    session.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    record(
        session,
        f"user:{actor.id}",
        "user.invite_cancelled",
        "user",
        user.id,
        {"email": user.email},
        organisation_id=user.organisation_id,
        user_id=actor.id,
    )
    session.delete(user)


def activate(session: Session, user: User, password_hash: str, display_name: str | None) -> None:
    user.password_hash = password_hash
    user.status = "active"
    if display_name:
        user.display_name = display_name
    record(
        session,
        f"user:{user.id}",
        "user.activated",
        "user",
        user.id,
        organisation_id=user.organisation_id,
        user_id=user.id,
    )


# --- password reset --------------------------------------------------------------------------


def start_reset(session: Session, settings: Settings, email: str) -> tuple[User, str] | None:
    """A reset token for an active user, else None (the caller answers the same either way)."""
    user = find_user(session, email)
    if user is None or user.status != "active":
        return None
    _expire_tokens(session, user.id, "reset")
    token, token_hash = new_token()
    session.add(
        AuthToken(
            user_id=user.id,
            kind="reset",
            token_hash=token_hash,
            expires_at=now() + timedelta(hours=settings.reset_ttl_hours),
        )
    )
    record(
        session,
        f"user:{user.id}",
        "user.password_reset_requested",
        "user",
        user.id,
        organisation_id=user.organisation_id,
        user_id=user.id,
    )
    return user, token


def finish_reset(session: Session, user: User, password_hash: str) -> None:
    if user.status != "active":
        raise AuthError("this link is invalid or has expired", status=400)
    user.password_hash = password_hash
    session.execute(delete(UserSession).where(UserSession.user_id == user.id))  # log out all
    record(
        session,
        f"user:{user.id}",
        "user.password_reset",
        "user",
        user.id,
        organisation_id=user.organisation_id,
        user_id=user.id,
    )


# --- sessions --------------------------------------------------------------------------------


def start_session(session: Session, settings: Settings, user: User) -> str:
    token, token_hash = new_token()
    moment = now()
    session.add(
        UserSession(
            id=token_hash,
            user_id=user.id,
            expires_at=moment + timedelta(days=settings.session_ttl_days),
            last_seen_at=moment,
        )
    )
    user.last_login_at = moment
    return token


def end_session(session: Session, token: str) -> None:
    session.execute(delete(UserSession).where(UserSession.id == digest(token)))


def _expire_tokens(session: Session, user_id: int, kind: str) -> None:
    session.execute(
        update(AuthToken)
        .where(AuthToken.user_id == user_id, AuthToken.kind == kind, AuthToken.used_at.is_(None))
        .values(used_at=now())
    )
