"""Admin commands (no admin UI yet). Run: python -m sabq.cli <command> ...

  catalog load [--dir PATH]
  org create SLUG NAME
  org show SLUG
  org wilaya SLUG CODE [--revoke]
  org source SLUG SOURCE_SLUG [--revoke]
  user create ORG_SLUG EMAIL ROLE [--name NAME]

Every access change is written to audit_events with actor "cli:<os user>".
"""

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sabq.audit import record
from sabq.catalog import NATIONAL, load_catalog, read_catalog
from sabq.db.models import (
    Organisation,
    OrganisationSource,
    OrganisationWilaya,
    Source,
    User,
    Wilaya,
)
from sabq.db.session import get_sync_sessionmaker

# backend/src/sabq/cli.py -> repository root /catalog (in the image: /srv/catalog)
DEFAULT_CATALOG = Path(__file__).resolve().parents[3] / "catalog"


class CliError(Exception):
    pass


def _org(session: Session, slug: str) -> Organisation:
    org = session.scalar(select(Organisation).where(Organisation.slug == slug))
    if org is None:
        raise CliError(f"no organisation {slug!r}")
    return org


def _one(session: Session, model, column, value, label: str):
    row = session.scalar(select(model).where(column == value))
    if row is None:
        raise CliError(f"no {label} {value!r}")
    return row


def _set_link(session: Session, model, key: dict, enabled: bool) -> None:
    link = session.get(model, key)
    if link is None:
        session.add(model(**key, enabled=enabled))
    else:
        link.enabled = enabled


def catalog_load(session: Session, actor: str, directory: Path) -> str:
    result = load_catalog(session, read_catalog(directory), actor)
    return (
        f"created {len(result.created)} {result.created}, updated {len(result.updated)} "
        f"{result.updated}, unchanged {len(result.unchanged)}"
    )


def org_create(session: Session, actor: str, slug: str, name: str) -> str:
    if session.scalar(select(Organisation).where(Organisation.slug == slug)):
        raise CliError(f"organisation {slug!r} already exists")
    org = Organisation(slug=slug, name=name)
    session.add(org)
    session.flush()
    national = _one(session, Wilaya, Wilaya.code, NATIONAL, "wilaya")
    session.add(OrganisationWilaya(organisation_id=org.id, wilaya_id=national.id))
    record(session, actor, "organisation.created", "organisation", slug, organisation_id=org.id)
    record(
        session,
        actor,
        "organisation.wilaya_granted",
        "wilaya",
        NATIONAL,
        {"default": True},
        organisation_id=org.id,
    )
    return f"created organisation {slug} (granted {NATIONAL} National by default)"


def org_wilaya(session: Session, actor: str, slug: str, code: str, revoke: bool) -> str:
    org = _org(session, slug)
    wilaya = _one(session, Wilaya, Wilaya.code, code, "wilaya")
    _set_link(
        session,
        OrganisationWilaya,
        {"organisation_id": org.id, "wilaya_id": wilaya.id},
        not revoke,
    )
    action = "organisation.wilaya_revoked" if revoke else "organisation.wilaya_granted"
    record(session, actor, action, "wilaya", code, organisation_id=org.id)
    return f"{'revoked' if revoke else 'granted'} wilaya {code} {wilaya.name_fr} for {slug}"


def org_source(session: Session, actor: str, slug: str, source_slug: str, revoke: bool) -> str:
    org = _org(session, slug)
    source = _one(session, Source, Source.slug, source_slug, "source")
    _set_link(
        session,
        OrganisationSource,
        {"organisation_id": org.id, "source_id": source.id},
        not revoke,
    )
    action = "organisation.source_revoked" if revoke else "organisation.source_granted"
    record(session, actor, action, "source", source_slug, organisation_id=org.id)
    return f"{'revoked' if revoke else 'granted'} source {source_slug} for {slug}"


def org_show(session: Session, slug: str) -> str:
    org = _org(session, slug)
    wilayas = session.execute(
        select(Wilaya.code, Wilaya.name_fr)
        .join(OrganisationWilaya, OrganisationWilaya.wilaya_id == Wilaya.id)
        .where(OrganisationWilaya.organisation_id == org.id, OrganisationWilaya.enabled)
        .order_by(Wilaya.code)
    ).all()
    sources = session.scalars(
        select(Source.slug)
        .join(OrganisationSource, OrganisationSource.source_id == Source.id)
        .where(OrganisationSource.organisation_id == org.id, OrganisationSource.enabled)
        .order_by(Source.slug)
    ).all()
    users = session.execute(
        select(User.email, User.role, User.status)
        .where(User.organisation_id == org.id)
        .order_by(User.email)
    ).all()
    lines = [f"{org.slug}: {org.name} ({org.status})"]
    lines.append("  wilayas: " + (", ".join(f"{c} {n}" for c, n in wilayas) or "none"))
    lines.append("  sources: " + (", ".join(sources) or "none"))
    lines.append("  users:   " + (", ".join(f"{e} ({r}, {s})" for e, r, s in users) or "none"))
    return "\n".join(lines)


def user_create(
    session: Session, actor: str, org_slug: str, email: str, role: str, name: str
) -> str:
    org = _org(session, org_slug)
    email = email.strip()
    if session.scalar(select(User).where(func.lower(User.email) == email.lower())):
        raise CliError(f"a user with email {email!r} already exists")
    user = User(organisation_id=org.id, email=email, display_name=name, role=role)
    session.add(user)
    session.flush()
    record(
        session,
        actor,
        "user.created",
        "user",
        user.id,
        {"email": email, "role": role},
        organisation_id=org.id,
    )
    return f"created user {email} ({role}) in {org_slug}, status invited (invite email: M6)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sabq")
    sub = parser.add_subparsers(dest="group", required=True)

    catalog = sub.add_parser("catalog").add_subparsers(dest="command", required=True)
    load = catalog.add_parser("load", help="load catalog/*.yaml into the database")
    load.add_argument("--dir", type=Path, default=DEFAULT_CATALOG)

    org = sub.add_parser("org").add_subparsers(dest="command", required=True)
    create = org.add_parser("create")
    create.add_argument("slug")
    create.add_argument("name")
    show = org.add_parser("show")
    show.add_argument("slug")
    wil = org.add_parser("wilaya", help="grant (or --revoke) a wilaya")
    wil.add_argument("slug")
    wil.add_argument("code")
    wil.add_argument("--revoke", action="store_true")
    src = org.add_parser("source", help="grant (or --revoke) a source")
    src.add_argument("slug")
    src.add_argument("source_slug")
    src.add_argument("--revoke", action="store_true")

    user = sub.add_parser("user").add_subparsers(dest="command", required=True)
    ucreate = user.add_parser("create")
    ucreate.add_argument("org_slug")
    ucreate.add_argument("email")
    ucreate.add_argument("role", choices=["owner", "admin", "editor", "viewer"])
    ucreate.add_argument("--name", default="")
    return parser


def run(argv: list[str], session: Session, actor: str) -> str:
    args = build_parser().parse_args(argv)
    match (args.group, args.command):
        case ("catalog", "load"):
            return catalog_load(session, actor, args.dir)
        case ("org", "create"):
            return org_create(session, actor, args.slug, args.name)
        case ("org", "show"):
            return org_show(session, args.slug)
        case ("org", "wilaya"):
            return org_wilaya(session, actor, args.slug, args.code, args.revoke)
        case ("org", "source"):
            return org_source(session, actor, args.slug, args.source_slug, args.revoke)
        case ("user", "create"):
            return user_create(session, actor, args.org_slug, args.email, args.role, args.name)
    raise CliError("unknown command")


def main() -> None:
    actor = f"cli:{getpass.getuser()}"
    with get_sync_sessionmaker()() as session:
        try:
            print(run(sys.argv[1:], session, actor))
            session.commit()
        except (CliError, ValueError) as error:
            session.rollback()
            sys.exit(f"error: {error}")


if __name__ == "__main__":
    main()
