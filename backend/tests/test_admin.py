"""M6: Sabq team endpoints and the OpenAPI document for the frontend."""

import json

import feedparser
import pytest
from test_auth import login, make_user
from test_webapp import world  # noqa: F401  (fixture)

from sabq.cli import DEFAULT_CATALOG

OPENAPI = DEFAULT_CATALOG.parent / "docs" / "openapi.json"


@pytest.mark.db
def test_source_feed_is_valid_rss_with_leads_only(client, world):  # noqa: F811
    db, _ = world
    make_user(db, "sabq", "team@sabq.dz", role="owner", admin=True)
    login(client, "a@org-a.dz")
    assert client.get("/admin/feeds/batna-src.xml").status_code == 403  # not the Sabq team
    login(client, "team@sabq.dz")
    response = client.get("/admin/feeds/batna-src.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/rss+xml")
    parsed = feedparser.parse(response.content)
    assert not parsed.bozo, parsed.get("bozo_exception")
    assert len(parsed.entries) == 3  # all of the source's articles, whatever the wilaya
    assert parsed.entries[0].id.startswith("batna-src:")
    assert "FULL TEXT MUST NEVER LEAVE" not in response.text
    assert client.get("/admin/feeds/missing.xml").status_code == 404


@pytest.mark.db
def test_internal_articles_need_an_organisation_and_keep_its_access(client, world):  # noqa: F811
    db, _ = world
    make_user(db, "sabq", "team@sabq.dz", role="owner", admin=True)
    login(client, "a@org-a.dz")
    assert client.get("/api/articles", params={"organisation": "org-a"}).status_code == 403
    login(client, "team@sabq.dz")
    assert client.get("/api/articles").status_code == 422  # organisation is mandatory
    items = client.get("/api/articles", params={"organisation": "org-a"}).json()
    assert {i["url"].rsplit("/", 1)[1] for i in items} == {"batna-local", "batna-national"}
    assert items[0]["body_text"] == "FULL TEXT MUST NEVER LEAVE"  # internal use only
    assert client.get("/api/articles", params={"organisation": "nope"}).status_code == 404


def test_openapi_document_is_up_to_date():
    from sabq.app import app

    committed = json.loads(OPENAPI.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(app.openapi())), (
        "docs/openapi.json is stale: run `uv run python -m sabq.openapi`"
    )


def test_test_ui_is_served_and_not_in_the_api_contract():
    from fastapi.testclient import TestClient

    from sabq.app import app

    client = TestClient(app)
    page = client.get("/ui")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "/app/stream" in page.text and "/auth/login" in page.text
    assert "/ui" not in app.openapi()["paths"]


@pytest.mark.db
def test_review_list_is_team_only(client, world):  # noqa: F811
    from sabq.db.models import DedupCandidate

    db, ids = world
    db.add(
        DedupCandidate(
            article_id=ids["batna-local"],
            candidate_article_id=ids["oran-local"],
            score=0.87,
            scorer_version=1,
            signals={"conflicts": ["numbers: [15] vs [7] قتيل"], "hours_apart": 2},
        )
    )
    db.commit()
    login(client, "a@org-a.dz")
    assert client.get("/admin/review").status_code == 403
    make_user(db, "sabq", "team@sabq.dz", role="owner", admin=True)
    login(client, "team@sabq.dz")
    (pair,) = client.get("/admin/review").json()
    assert pair["score"] == 0.87 and pair["conflicts"] == ["numbers: [15] vs [7] قتيل"]
    assert pair["a"]["source"] == "batna-src" and pair["b"]["source"] == "oran-src"
