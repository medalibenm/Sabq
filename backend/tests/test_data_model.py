"""M2: wilaya seed, catalog loader, access boundaries, admin CLI (docs/plan.md)."""

import hashlib
import shutil
import unicodedata
from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select

from sabq.access import visible_articles
from sabq.catalog import load_catalog, read_catalog
from sabq.cli import DEFAULT_CATALOG, CliError, run
from sabq.db.models import (
    Article,
    ArticleWilaya,
    AuditEvent,
    Organisation,
    OrganisationSource,
    OrganisationWilaya,
    Source,
    SourceConfigVersion,
    SourceWilaya,
    User,
    Wilaya,
)

pytestmark = pytest.mark.db
ACTOR = "test"


# --- helpers -------------------------------------------------------------------------------


def wilaya_id(session, code: str) -> int:
    return session.scalar(select(Wilaya.id).where(Wilaya.code == code))


def make_source(session, slug: str) -> Source:
    source = Source(
        slug=slug,
        name=slug,
        home_url=f"https://{slug}.example/",
        language="ar",
        kind="local",
        tier="normal",
        poll_interval_s=300,
        access_method="rss",
        config={},
    )
    session.add(source)
    session.flush()
    return source


def make_org(session, slug: str, sources=(), wilayas=()) -> Organisation:
    run(["org", "create", slug, slug.title()], session, ACTOR)  # grants 00 National
    for source in sources:
        run(["org", "source", slug, source.slug], session, ACTOR)
    for code in wilayas:
        run(["org", "wilaya", slug, code], session, ACTOR)
    return session.scalar(select(Organisation).where(Organisation.slug == slug))


def make_article(session, source: Source, external_id: str, *codes: str) -> Article:
    url = f"https://{source.slug}.example/{external_id}"
    article = Article(
        source_id=source.id,
        external_id=external_id,
        url=url,
        canonical_url=url,
        canonical_url_key=url,
        title=f"عنوان {external_id}",
        language="ar",
        published_at_confidence="source_meta",
        content_hash=hashlib.sha256(url.encode()).hexdigest(),
    )
    session.add(article)
    session.flush()
    session.add_all(
        ArticleWilaya(
            article_id=article.id, wilaya_id=wilaya_id(session, c), assignment_method="source"
        )
        for c in codes
    )
    session.flush()
    return article


def visible_ids(session, org: Organisation) -> set[str]:
    return {a.external_id for a in session.scalars(visible_articles(org.id))}


# --- wilaya seed ---------------------------------------------------------------------------


def test_wilaya_seed(session):
    rows = session.execute(select(Wilaya.code, Wilaya.name_ar, Wilaya.active_from)).all()
    assert len(rows) == 70  # 69 wilayas + 00 National
    codes = sorted(code for code, _, _ in rows)
    assert codes == [f"{n:02d}" for n in range(70)]
    assert {code for code, _, active in rows if active} == {f"{n}" for n in range(59, 70)}
    assert all(unicodedata.is_normalized("NFC", name) for _, name, _ in rows)


# --- access boundaries ---------------------------------------------------------------------


@pytest.fixture
def world(session):
    """Two organisations sharing nothing, plus one article per interesting case."""
    batna_src, oran_src = make_source(session, "batna-src"), make_source(session, "oran-src")
    org_a = make_org(session, "org-a", sources=[batna_src], wilayas=["05"])
    org_b = make_org(session, "org-b", sources=[oran_src], wilayas=["31"])
    make_article(session, batna_src, "batna-local", "05")
    make_article(session, batna_src, "batna-national", "00")
    make_article(session, batna_src, "batna-about-oran", "31")  # source granted, wilaya not
    make_article(session, oran_src, "oran-local", "31")
    make_article(session, oran_src, "oran-about-batna", "05")  # wilaya granted, source not
    return session, org_a, org_b


def test_each_organisation_sees_only_its_sources_and_wilayas(world):
    session, org_a, org_b = world
    assert visible_ids(session, org_a) == {"batna-local", "batna-national"}
    assert visible_ids(session, org_b) == {"oran-local"}


def test_national_is_granted_by_default_and_revocable(world):
    session, org_a, _ = world
    run(["org", "wilaya", "org-a", "00", "--revoke"], session, ACTOR)
    assert visible_ids(session, org_a) == {"batna-local"}


def test_revoking_a_source_hides_its_articles(world):
    session, org_a, _ = world
    run(["org", "source", "org-a", "batna-src", "--revoke"], session, ACTOR)
    assert visible_ids(session, org_a) == set()


def test_suspended_organisation_sees_nothing(world):
    session, org_a, _ = world
    org_a.status = "suspended"
    session.flush()
    assert visible_ids(session, org_a) == set()


def test_organisation_without_wilayas_sees_nothing(world):
    session, org_a, _ = world
    run(["org", "wilaya", "org-a", "00", "--revoke"], session, ACTOR)
    run(["org", "wilaya", "org-a", "05", "--revoke"], session, ACTOR)
    assert visible_ids(session, org_a) == set()


def test_article_in_two_wilayas_is_visible_through_either(world):
    session, org_a, org_b = world
    oran_src = session.scalar(select(Source).where(Source.slug == "oran-src"))
    run(["org", "source", "org-a", "oran-src"], session, ACTOR)
    make_article(session, oran_src, "storm-05-31", "05", "31")
    assert "storm-05-31" in visible_ids(session, org_a)  # through 05
    assert "storm-05-31" in visible_ids(session, org_b)  # through 31


# --- catalog loader ------------------------------------------------------------------------


def test_load_real_catalog(session):
    result = load_catalog(session, read_catalog(DEFAULT_CATALOG), ACTOR)
    # created on an empty database, unchanged if a previous `catalog load` already ran
    assert {"awras-ar", "elhidhab-ar"} <= set(result.created + result.unchanged)
    awras = session.scalar(select(Source).where(Source.slug == "awras-ar"))
    assert (awras.kind, awras.access_method, awras.poll_interval_s) == ("local", "wp_json", 1800)
    assert awras.config["listings"][0].startswith("https://elauresnews.dz/wp-json/")
    codes = session.scalars(
        select(Wilaya.code).join(SourceWilaya).where(SourceWilaya.source_id == awras.id)
    ).all()
    assert codes == ["05"]

    again = load_catalog(session, read_catalog(DEFAULT_CATALOG), ACTOR)
    assert again.created == [] and again.updated == []


def copy_catalog(tmp_path: Path, slug: str = "awras-ar") -> Path:
    shutil.copy(DEFAULT_CATALOG / f"{slug}.yaml", tmp_path / f"{slug}.yaml")
    return tmp_path / f"{slug}.yaml"


def edit(path: Path, **changes) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_config_change_creates_a_new_version(session, tmp_path):
    path = copy_catalog(tmp_path)
    load_catalog(session, read_catalog(tmp_path), ACTOR)
    edit(path, poll_interval_s=900)
    result = load_catalog(session, read_catalog(tmp_path), ACTOR)

    assert result.updated == ["awras-ar"]
    source = session.scalar(select(Source).where(Source.slug == "awras-ar"))
    assert (source.config_version, source.poll_interval_s) == (2, 900)
    versions = session.scalars(
        select(SourceConfigVersion.version).where(SourceConfigVersion.source_id == source.id)
    ).all()
    assert sorted(versions) == [1, 2]


def test_source_without_wilaya_is_national(session, tmp_path):
    edit(copy_catalog(tmp_path), wilayas=[])
    load_catalog(session, read_catalog(tmp_path), ACTOR)
    source_id = session.scalar(select(Source.id).where(Source.slug == "awras-ar"))
    codes = session.scalars(
        select(Wilaya.code).join(SourceWilaya).where(SourceWilaya.source_id == source_id)
    ).all()
    assert codes == ["00"]


def test_unknown_wilaya_is_rejected(session, tmp_path):
    edit(copy_catalog(tmp_path), wilayas=["99"])
    with pytest.raises(ValueError, match="unknown wilaya"):
        load_catalog(session, read_catalog(tmp_path), ACTOR)


def test_slug_must_match_file_name(tmp_path):
    path = copy_catalog(tmp_path)
    path.rename(tmp_path / "other.yaml")
    with pytest.raises(ValueError, match="does not match"):
        read_catalog(tmp_path)


# --- admin CLI and audit -------------------------------------------------------------------


def test_org_create_is_audited_and_unique(session):
    run(["org", "create", "tariq", "Tariq News"], session, ACTOR)
    actions = session.scalars(select(AuditEvent.action).order_by(AuditEvent.id)).all()
    assert actions[-2:] == ["organisation.created", "organisation.wilaya_granted"]
    with pytest.raises(CliError, match="already exists"):
        run(["org", "create", "tariq", "Again"], session, ACTOR)


def test_user_email_is_unique_ignoring_case(session):
    run(["org", "create", "tariq", "Tariq News"], session, ACTOR)
    run(["user", "create", "tariq", "Journalist@Tariq.dz", "editor"], session, ACTOR)
    user = session.scalar(select(User).where(func.lower(User.email) == "journalist@tariq.dz"))
    assert (user.role, user.status, user.password_hash) == ("editor", "invited", None)
    with pytest.raises(CliError, match="already exists"):
        run(["user", "create", "tariq", "journalist@tariq.dz", "viewer"], session, ACTOR)


def test_org_show_lists_grants(session):
    run(["org", "create", "tariq", "Tariq News"], session, ACTOR)
    run(["org", "wilaya", "tariq", "05"], session, ACTOR)
    out = run(["org", "show", "tariq"], session, ACTOR)
    assert "00 National, 05 Batna" in out


def test_grant_is_idempotent(session):
    run(["org", "create", "tariq", "Tariq News"], session, ACTOR)
    run(["org", "wilaya", "tariq", "05"], session, ACTOR)
    run(["org", "wilaya", "tariq", "05"], session, ACTOR)
    org_id = session.scalar(select(Organisation.id).where(Organisation.slug == "tariq"))
    count = session.scalar(
        select(func.count())
        .select_from(OrganisationWilaya)
        .where(OrganisationWilaya.organisation_id == org_id)
    )
    assert count == 2  # 00 + 05, no duplicate row


def test_unknown_organisation_or_source(session):
    with pytest.raises(CliError, match="no organisation"):
        run(["org", "wilaya", "nobody", "05"], session, ACTOR)
    run(["org", "create", "tariq", "Tariq News"], session, ACTOR)
    with pytest.raises(CliError, match="no source"):
        run(["org", "source", "tariq", "missing-src"], session, ACTOR)
    assert session.scalar(select(func.count()).select_from(OrganisationSource)) == 0
