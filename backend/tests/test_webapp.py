"""M6: the web app API. The M2 access rules, again through HTTP: a user never sees another
organisation's articles or a wilaya their organisation was not granted."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from test_auth import PASSWORD, login, make_user
from test_data_model import make_article, make_source

from sabq.cli import run
from sabq.db.models import (
    Article,
    FetchRun,
    Organisation,
    Source,
    StoryCluster,
    StoryClusterMember,
    User,
)

pytestmark = pytest.mark.db
T0 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


@pytest.fixture
def world(committed):
    """org-a: Batna source + wilaya 05 (+ 00 by default); org-b: Oran source + wilaya 31."""
    db = committed
    batna, oran = make_source(db, "batna-src"), make_source(db, "oran-src")
    make_user(db, "org-a", "a@org-a.dz")
    make_user(db, "org-b", "b@org-b.dz")
    make_user(db, "org-a", "viewer@org-a.dz", role="viewer")
    run(["org", "source", "org-a", "batna-src"], db, "test")
    run(["org", "wilaya", "org-a", "05"], db, "test")
    run(["org", "source", "org-b", "oran-src"], db, "test")
    run(["org", "wilaya", "org-b", "31"], db, "test")
    articles = {
        "batna-local": make_article(db, batna, "batna-local", "05"),
        "batna-national": make_article(db, batna, "batna-national", "00"),
        "batna-about-oran": make_article(db, batna, "batna-about-oran", "31"),
        "oran-local": make_article(db, oran, "oran-local", "31"),
        "oran-about-batna": make_article(db, oran, "oran-about-batna", "05"),
    }
    for minutes, article in enumerate(articles.values()):
        article.published_at = T0 + timedelta(minutes=minutes)
        article.body_text = "FULL TEXT MUST NEVER LEAVE"
    db.commit()
    return db, {k: a.id for k, a in articles.items()}


def visible(client, **params) -> set[str]:
    response = client.get("/app/articles", params=params)
    assert response.status_code == 200, response.text
    return {item["url"].rsplit("/", 1)[1] for item in response.json()["items"]}


# --- access through HTTP ---------------------------------------------------------------------


def test_each_organisation_sees_only_its_sources_and_wilayas(client, world):
    login(client, "a@org-a.dz")
    assert visible(client) == {"batna-local", "batna-national"}
    login(client, "b@org-b.dz")
    assert visible(client) == {"oran-local"}


def test_detail_of_an_invisible_article_is_404(client, world):
    _, ids = world
    login(client, "a@org-a.dz")
    assert client.get(f"/app/articles/{ids['batna-local']}").status_code == 200
    for hidden in ("oran-local", "oran-about-batna", "batna-about-oran"):
        assert client.get(f"/app/articles/{ids[hidden]}").status_code == 404
    assert client.get("/app/articles/999999").status_code == 404


def test_filters_never_widen_access(client, world):
    login(client, "a@org-a.dz")
    assert visible(client, wilaya="31") == set()  # not granted
    assert visible(client, source="oran-src") == set()  # not subscribed
    assert visible(client, wilaya="05") == {"batna-local"}
    assert visible(client, source="batna-src", wilaya="00") == {"batna-national"}


def test_revoking_and_suspending_take_effect_at_once(client, world):
    db, _ = world
    login(client, "a@org-a.dz")
    run(["org", "wilaya", "org-a", "00", "--revoke"], db, "test")
    db.commit()
    assert visible(client) == {"batna-local"}
    db.execute(update(Organisation).where(Organisation.slug == "org-a").values(status="suspended"))
    db.commit()
    assert visible(client) == set()


def test_full_text_never_leaves(client, world):
    _, ids = world
    login(client, "a@org-a.dz")
    listing = client.get("/app/articles").text
    detail = client.get(f"/app/articles/{ids['batna-local']}").text
    for body in (listing, detail):
        assert "body_text" not in body and "FULL TEXT MUST NEVER LEAVE" not in body


def test_everything_needs_login(client, world):
    for path in (
        "/app/articles",
        "/app/articles/1",
        "/app/wilayas",
        "/app/sources",
        "/app/source-requests",
    ):
        assert client.get(path).status_code == 401
    assert client.post("/app/source-requests", json={"url": "https://x.dz"}).status_code == 401


# --- shapes, order, pages, search ------------------------------------------------------------


def test_item_shape_and_newest_first(client, world):
    login(client, "a@org-a.dz")
    items = client.get("/app/articles").json()["items"]
    assert [i["url"].rsplit("/", 1)[1] for i in items] == ["batna-national", "batna-local"]
    first = items[0]
    assert first["source"] == {"slug": "batna-src", "name": "batna-src", "language": "ar"}
    assert first["wilayas"] == ["00"] and first["story_cluster_id"] is None
    assert first["sort_at"] == first["published_at"]


def test_cursor_pages_cover_everything_once(client, committed):
    db = committed
    source = make_source(db, "big-src")
    make_user(db, "org-c", "c@org-c.dz")
    run(["org", "source", "org-c", "big-src"], db, "test")
    for n in range(7):
        article = make_article(db, source, f"n{n}", "00")
        article.published_at = T0 + timedelta(minutes=n % 3)  # ties on purpose
    db.commit()
    login(client, "c@org-c.dz")
    seen, cursor = [], None
    while True:
        params = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        body = client.get("/app/articles", params=params).json()
        seen += [i["id"] for i in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 7
    assert client.get("/app/articles", params={"cursor": "garbage"}).status_code == 400


def test_search_and_since(client, world):
    db, ids = world
    db.execute(
        update(Article).where(Article.id == ids["batna-local"]).values(title="زلزال في باتنة")
    )
    db.commit()
    login(client, "a@org-a.dz")
    assert visible(client, q="زلزال") == {"batna-local"}
    assert visible(client, q="100%_") == set()  # wildcards are literal
    later = (T0 + timedelta(minutes=1)).isoformat()
    assert visible(client, since=later) == {"batna-national"}


# --- sources, wilayas, source requests ---------------------------------------------------------


def test_my_sources_and_wilayas(client, world):
    login(client, "a@org-a.dz")
    assert [w["code"] for w in client.get("/app/wilayas").json()] == ["00", "05"]
    assert [s["slug"] for s in client.get("/app/sources").json()] == ["batna-src"]


def test_source_requests(client, world):
    login(client, "viewer@org-a.dz")
    url = {"url": "https://new-source.dz/", "note": "جريدة محلية"}
    assert client.post("/app/source-requests", json=url).status_code == 403  # viewers read only
    login(client, "a@org-a.dz", PASSWORD)
    created = client.post("/app/source-requests", json=url)
    assert created.status_code == 201 and created.json()["status"] == "new"
    assert client.post("/app/source-requests", json={"url": "ftp://x"}).status_code == 422
    assert len(client.get("/app/source-requests").json()) == 1
    login(client, "b@org-b.dz")
    assert client.get("/app/source-requests").json() == []  # other organisations' are private
    db, _ = world
    from sabq.db.models import SourceRequest

    assert db.scalar(select(SourceRequest.note)) == "جريدة محلية"


def test_stories_show_only_visible_members(client, world):
    from sabq.db.models import StoryCluster, StoryClusterMember

    db, ids = world
    both_visible = StoryCluster(status="automatic", last_member_at=T0)
    half_visible = StoryCluster(status="automatic", last_member_at=T0)
    db.add_all([both_visible, half_visible])
    db.flush()
    for cluster, keys in (
        (both_visible, ("batna-local", "batna-national")),
        (half_visible, ("batna-local", "oran-local")),
    ):
        for key in keys:
            db.add(
                StoryClusterMember(
                    cluster_id=cluster.id,
                    article_id=ids[key],
                    membership="duplicate",
                    confidence=1.0,
                )
            )
    db.commit()
    login(client, "a@org-a.dz")
    stories = client.get("/app/stories").json()
    assert [s["id"] for s in stories] == [both_visible.id]  # the other has 1 visible article
    assert {a["url"].rsplit("/", 1)[1] for a in stories[0]["articles"]} == {
        "batna-local",
        "batna-national",
    }
    login(client, "b@org-b.dz")
    assert client.get("/app/stories").json() == []  # org-b sees only one of oran-local's story


# --- what the frontend needs -----------------------------------------------------------------


def test_filters_take_several_values(client, world):
    db, ids = world
    second = make_source(db, "second-src")
    run(["org", "source", "org-a", "second-src"], db, "test")
    make_article(db, second, "second-local", "05")
    db.commit()
    login(client, "a@org-a.dz")
    assert visible(client, source=["batna-src"]) == {"batna-local", "batna-national"}
    assert visible(client, source=["batna-src", "second-src"]) == {
        "batna-local",
        "batna-national",
        "second-local",
    }
    assert visible(client, wilaya=["05", "00"], source=["second-src"]) == {"second-local"}
    assert client.get("/app/articles", params={"wilaya": "x"}).status_code == 422


def _story(db, ids, *keys, last_member_at=None, closed_at=None):
    cluster = StoryCluster(status="automatic", last_member_at=last_member_at, closed_at=closed_at)
    db.add(cluster)
    db.flush()
    for key in keys:
        db.add(
            StoryClusterMember(
                cluster_id=cluster.id, article_id=ids[key], membership="duplicate", confidence=0.9
            )
        )
    return cluster


def test_articles_list_their_visible_story_peers_and_edits(client, world):
    db, ids = world
    _story(db, ids, "batna-local", "batna-national", "oran-about-batna")
    db.execute(update(Article).where(Article.id == ids["batna-local"]).values(version=3))
    db.commit()
    login(client, "a@org-a.dz")
    items = {i["id"]: i for i in client.get("/app/articles").json()["items"]}
    local = items[ids["batna-local"]]
    assert local["version"] == 3
    # oran-about-batna is in the story, but org-a does not have its source
    assert [p["id"] for p in local["same_story"]] == [ids["batna-national"]]
    detail = client.get(f"/app/articles/{ids['batna-local']}").json()
    assert [p["id"] for p in detail["same_story"]] == [ids["batna-national"]]


def test_facets_count_today_in_algiers_time(client, world):
    db, ids = world
    now = datetime.now(UTC)
    db.execute(update(Article).values(published_at=now - timedelta(days=3)))
    db.execute(update(Article).where(Article.id == ids["batna-local"]).values(published_at=now))
    db.commit()
    login(client, "a@org-a.dz")
    assert client.get("/app/facets").json() == {
        "total": 1,
        "sources": {"batna-src": 1},
        "wilayas": {"05": 1},
    }
    filtered = client.get("/app/facets", params={"wilaya": "00"}).json()
    assert filtered["total"] == 0 and filtered["wilayas"] == {"05": 1}


def test_stories_filter_and_tell_developing_from_closed(client, world):
    db, ids = world
    now = datetime.now(UTC)
    fresh = _story(db, ids, "batna-local", "batna-national", last_member_at=now)
    run(["org", "wilaya", "org-a", "31"], db, "test")
    extra = make_article(
        db, db.get(Source, db.get(Article, ids["batna-local"]).source_id), "x", "05"
    )
    ids["extra"] = extra.id
    old = _story(db, ids, "extra", "batna-about-oran", last_member_at=now - timedelta(days=4))
    db.commit()
    login(client, "a@org-a.dz")
    stories = client.get("/app/stories").json()
    assert [(s["id"], s["closed"]) for s in stories] == [(fresh.id, False), (old.id, True)]
    params = {"state": "closed"}
    assert [s["id"] for s in client.get("/app/stories", params=params).json()] == [old.id]
    params = {"state": "developing"}
    assert [s["id"] for s in client.get("/app/stories", params=params).json()] == [fresh.id]
    found = client.get("/app/stories", params={"wilaya": "00"}).json()
    assert [s["id"] for s in found] == [fresh.id] and len(found[0]["articles"]) == 2


def test_sources_show_a_friendly_state_never_the_error(client, world):
    db, ids = world
    source = db.scalar(select(Source).where(Source.slug == "batna-src"))
    source.status = "broken"
    db.add(FetchRun(source_id=source.id, started_at=datetime.now(UTC), error="secret stack trace"))
    db.commit()
    login(client, "a@org-a.dz")
    response = client.get("/app/sources")
    row = response.json()[0]
    assert row["state"] == "stopped" and row["last_checked_at"]
    assert "secret stack trace" not in response.text


def test_team_lists_members_and_cancels_only_pending_invitations(client, world):
    db, ids = world
    make_user(db, "org-a", "owner@org-a.dz", role="owner")
    login(client, "viewer@org-a.dz")
    assert client.get("/app/team").status_code == 403

    login(client, "owner@org-a.dz")
    invited = client.post("/auth/invite", json={"email": "new@org-a.dz", "role": "editor"})
    assert invited.status_code == 201
    members = {m["email"]: m for m in client.get("/app/team").json()}
    assert members["new@org-a.dz"]["status"] == "invited"
    assert members["new@org-a.dz"]["invited_at"]
    assert members["a@org-a.dz"]["invited_at"] is None
    assert "b@org-b.dz" not in members

    json_header = {"content-type": "application/json"}
    active = client.delete(f"/app/team/{members['a@org-a.dz']['id']}", headers=json_header)
    assert active.status_code == 409
    pending = members["new@org-a.dz"]["id"]
    assert client.delete(f"/app/team/{pending}", headers=json_header).status_code == 204
    assert "new@org-a.dz" not in {m["email"] for m in client.get("/app/team").json()}
    # the same address can be invited again
    again = client.post("/auth/invite", json={"email": "new@org-a.dz", "role": "viewer"})
    assert again.status_code == 201

    login(client, "b@org-b.dz")
    other = db.scalar(select(User).where(User.email == "new@org-a.dz"))
    assert client.delete(f"/app/team/{other.id}", headers=json_header).status_code == 403
