"""M6: login, invitations, password reset, sessions (docs/architecture.md#outputs)."""

import re
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from sabq.auth import service
from sabq.auth.passwords import hash_password, verify_password
from sabq.auth.ratelimit import FailureLimiter
from sabq.cli import run
from sabq.db.models import AuditEvent, AuthToken, User, UserSession

pytestmark = pytest.mark.db
PASSWORD = "correct horse battery"
JSON = {"content-type": "application/json"}


def make_user(db, org_slug, email, role="editor", *, password=PASSWORD, admin=False) -> User:
    from sabq.db.models import Organisation

    if db.scalar(select(Organisation).where(Organisation.slug == org_slug)) is None:
        run(["org", "create", org_slug, org_slug.title()], db, "test")
    org = db.scalar(select(Organisation).where(Organisation.slug == org_slug))
    user = User(
        organisation_id=org.id,
        email=email,
        role=role,
        status="active",
        password_hash=hash_password(password),
        platform_admin=admin,
    )
    db.add(user)
    db.commit()
    return user


def login(client, email, password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def token_from(message) -> str:
    return re.search(r"token=([\w-]+)", message.body).group(1)


# --- login, me, logout -----------------------------------------------------------------------


def test_login_sets_a_secure_session_cookie_and_logout_ends_it(client, committed):
    make_user(committed, "tariq", "Editor@Tariq.dz")
    response = login(client, "editor@tariq.dz")  # email is case-insensitive
    assert response.status_code == 200
    assert response.json()["organisation"]["slug"] == "tariq"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert client.get("/auth/me").json()["email"] == "Editor@Tariq.dz"

    assert client.post("/auth/logout", headers=JSON).status_code == 204
    assert client.get("/auth/me").status_code == 401
    assert committed.scalar(select(func.count()).select_from(UserSession)) == 0


def test_wrong_password_unknown_email_and_inactive_user_look_the_same(client, committed):
    make_user(committed, "tariq", "a@tariq.dz")
    disabled = make_user(committed, "tariq", "b@tariq.dz")
    disabled.status = "disabled"
    committed.commit()
    answers = [
        login(client, "a@tariq.dz", "wrong password!"),
        login(client, "nobody@tariq.dz"),
        login(client, "b@tariq.dz"),
    ]
    assert {(r.status_code, r.json()["detail"]) for r in answers} == {
        (401, "wrong email or password")
    }


def test_failed_logins_are_rate_limited(client, committed):
    make_user(committed, "tariq", "a@tariq.dz")
    for _ in range(5):
        assert login(client, "a@tariq.dz", "wrong password!").status_code == 401
    assert login(client, "a@tariq.dz").status_code == 429  # even the right password, for now


def test_writes_need_json(client, committed):
    make_user(committed, "tariq", "a@tariq.dz")
    form = client.post("/auth/login", data={"email": "a@tariq.dz", "password": PASSWORD})
    assert form.status_code == 415  # a cross-site form post can't log anyone in or out


def test_expired_session_is_refused(client, committed):
    make_user(committed, "tariq", "a@tariq.dz")
    login(client, "a@tariq.dz")
    committed.execute(update(UserSession).values(expires_at=service.now() - timedelta(seconds=1)))
    committed.commit()
    assert client.get("/auth/me").status_code == 401


# --- invitations -----------------------------------------------------------------------------


def test_invite_then_accept_logs_the_new_user_in(client, committed):
    make_user(committed, "tariq", "owner@tariq.dz", role="owner")
    login(client, "owner@tariq.dz")
    response = client.post(
        "/auth/invite", json={"email": "new@tariq.dz", "role": "editor", "display_name": "سارة"}
    )
    assert response.status_code == 201
    assert response.json() == {
        "email": "new@tariq.dz",
        "role": "editor",
        "status": "invited",
        "email_sent": True,
    }
    (message,) = client.outbox
    assert message.to == "new@tariq.dz" and "accept-invite?token=" in message.body

    client.cookies.clear()
    short = client.post("/auth/accept-invite", json={"token": token_from(message), "password": "x"})
    assert short.status_code == 400  # password policy, and the link still works afterwards
    accepted = client.post(
        "/auth/accept-invite", json={"token": token_from(message), "password": PASSWORD}
    )
    assert accepted.status_code == 200
    assert accepted.json()["display_name"] == "سارة"
    assert client.get("/auth/me").status_code == 200
    again = client.post(
        "/auth/accept-invite", json={"token": token_from(message), "password": PASSWORD}
    )
    assert again.status_code == 400  # single use
    actions = committed.scalars(select(AuditEvent.action)).all()
    assert {"user.invited", "user.activated"} <= set(actions)


def test_who_may_invite_whom(client, committed):
    make_user(committed, "tariq", "admin@tariq.dz", role="admin")
    make_user(committed, "other", "x@other.dz")
    login(client, "admin@tariq.dz")
    invite = lambda **body: client.post("/auth/invite", json={"role": "editor", **body})  # noqa: E731
    assert invite(email="e@tariq.dz").status_code == 201
    assert invite(email="o@tariq.dz", role="owner").status_code == 403  # admin can't make owners
    assert invite(email="x@other.dz", organisation="other").status_code == 403
    assert invite(email="x@other.dz").status_code == 409  # exists in another organisation

    make_user(committed, "tariq", "viewer@tariq.dz", role="viewer")
    login(client, "viewer@tariq.dz")
    assert invite(email="v2@tariq.dz").status_code == 403


def test_platform_admin_invites_into_any_organisation(client, committed):
    make_user(committed, "sabq", "team@sabq.dz", role="owner", admin=True)
    make_user(committed, "tariq", "someone@tariq.dz")
    login(client, "team@sabq.dz")
    response = client.post(
        "/auth/invite", json={"email": "boss@tariq.dz", "role": "owner", "organisation": "tariq"}
    )
    assert response.status_code == 201
    user = committed.scalar(select(User).where(User.email == "boss@tariq.dz"))
    assert user.organisation_id == committed.scalar(
        select(User.organisation_id).where(User.email == "someone@tariq.dz")
    )


def test_reinvite_replaces_the_old_link(client, committed):
    make_user(committed, "tariq", "owner@tariq.dz", role="owner")
    login(client, "owner@tariq.dz")
    for _ in range(2):
        client.post("/auth/invite", json={"email": "new@tariq.dz", "role": "viewer"})
    first, second = client.outbox
    client.cookies.clear()
    old = client.post(
        "/auth/accept-invite", json={"token": token_from(first), "password": PASSWORD}
    )
    assert old.status_code == 400
    new = client.post(
        "/auth/accept-invite", json={"token": token_from(second), "password": PASSWORD}
    )
    assert new.status_code == 200


def test_expired_invite_is_refused(client, committed):
    make_user(committed, "tariq", "owner@tariq.dz", role="owner")
    login(client, "owner@tariq.dz")
    client.post("/auth/invite", json={"email": "new@tariq.dz", "role": "viewer"})
    committed.execute(update(AuthToken).values(expires_at=service.now() - timedelta(minutes=1)))
    committed.commit()
    token = token_from(client.outbox[0])
    response = client.post("/auth/accept-invite", json={"token": token, "password": PASSWORD})
    assert response.status_code == 400


# --- password reset --------------------------------------------------------------------------


def test_forgot_and_reset_password(client, committed):
    make_user(committed, "tariq", "a@tariq.dz")
    other_device = login(client, "a@tariq.dz").cookies
    client.cookies.clear()

    unknown = client.post("/auth/forgot", json={"email": "nobody@tariq.dz"})
    known = client.post("/auth/forgot", json={"email": "A@tariq.dz"})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()  # no way to tell which emails have accounts
    (message,) = client.outbox
    assert message.to == "a@tariq.dz"

    new_password = "a much better passphrase"
    reset = client.post(
        "/auth/reset", json={"token": token_from(message), "password": new_password}
    )
    assert reset.status_code == 200
    assert login(client, "a@tariq.dz", new_password).status_code == 200
    assert login(client, "a@tariq.dz").status_code == 401  # old password gone
    client.cookies.clear()
    client.cookies.update(other_device)
    assert client.get("/auth/me").status_code == 401  # other sessions logged out


def test_forgot_is_limited_per_email(client, committed):
    make_user(committed, "tariq", "a@tariq.dz")
    for _ in range(8):
        assert client.post("/auth/forgot", json={"email": "a@tariq.dz"}).status_code == 202
    assert len(client.outbox) == 5


# --- CLI and building blocks -----------------------------------------------------------------


def test_cli_invite_sends_the_email_and_admin_flag_is_audited(client, committed):
    run(["org", "create", "tariq", "Tariq News"], committed, "test")
    committed.commit()
    out = run(["user", "invite", "tariq", "boss@tariq.dz", "owner"], committed, "test")
    assert "email sent" in out
    assert client.outbox[0].to == "boss@tariq.dz"
    run(["user", "admin", "boss@tariq.dz"], committed, "test")
    committed.commit()
    assert committed.scalar(select(User.platform_admin).where(User.email == "boss@tariq.dz"))
    assert "user.platform_admin_granted" in committed.scalars(select(AuditEvent.action)).all()


def test_tokens_are_stored_hashed(client, committed):
    make_user(committed, "tariq", "owner@tariq.dz", role="owner")
    login(client, "owner@tariq.dz")
    client.post("/auth/invite", json={"email": "new@tariq.dz", "role": "viewer"})
    token = token_from(client.outbox[0])
    stored = committed.scalars(select(AuthToken.token_hash)).all()
    assert token not in stored and service.digest(token) in stored
    session_token = client.cookies.get("sabq_session")
    assert committed.get(UserSession, session_token) is None
    assert committed.get(UserSession, service.digest(session_token)) is not None


def test_password_hashing():
    stored = hash_password(PASSWORD)
    assert stored.startswith("$argon2id$")
    assert verify_password(stored, PASSWORD) and not verify_password(stored, "nope nope nope")
    assert not verify_password(None, PASSWORD)


def test_failure_limiter_window():
    now = [0.0]
    limiter = FailureLimiter(3, 60, clock=lambda: now[0])
    limiter.fail("k")
    limiter.fail("k")
    limiter.fail("k")
    assert limiter.blocked("k") and not limiter.blocked("other")
    now[0] = 61
    assert not limiter.blocked("k")


def test_can_invite_rules():
    owner = User(organisation_id=1, role="owner", platform_admin=False)
    admin = User(organisation_id=1, role="admin", platform_admin=False)
    editor = User(organisation_id=1, role="editor", platform_admin=False)
    team = User(organisation_id=9, role="viewer", platform_admin=True)
    assert service.can_invite(owner, 1, "owner") and not service.can_invite(owner, 2, "viewer")
    assert service.can_invite(admin, 1, "admin") and not service.can_invite(admin, 1, "owner")
    assert not service.can_invite(editor, 1, "viewer")
    assert service.can_invite(team, 2, "owner")
