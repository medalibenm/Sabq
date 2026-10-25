"""M4: config-driven extraction (docs/plan.md). Every catalog source must extract correctly from
its fixtures; the building blocks are tested on small cases."""

import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
import yaml
from pydantic import ValidationError

from sabq.catalog import CatalogEntry, read_catalog
from sabq.cli import DEFAULT_CATALOG, DEFAULT_FIXTURES
from sabq.extract import SourceConfig, canonical_url_key, extract_listing, merge_listings
from sabq.extract.dates import parse_date
from sabq.extract.paths import find_all, find_first
from sabq.extract.text import clean_text
from sabq.extract.validate import title_on_page, validate_fixtures, validate_live
from sabq.fetch import Fetcher
from sabq.settings import Settings

CATALOG = {entry.slug: entry for entry in read_catalog(DEFAULT_CATALOG)}
NOW = datetime.now(UTC)


def fixture(slug: str, name: str) -> bytes:
    return (DEFAULT_FIXTURES / slug / name).read_bytes()


# --- every catalog source, from its fixtures ---------------------------------------------------


@pytest.mark.parametrize("slug", sorted(CATALOG))
def test_catalog_source_passes_validation_on_fixtures(slug):
    report = validate_fixtures(CATALOG[slug], DEFAULT_FIXTURES / slug, now=NOW)
    assert report.ok, report.text()


def items(slug: str, name: str = "listing_1"):
    entry = CATALOG[slug]
    path = next((DEFAULT_FIXTURES / slug).glob(f"{name}.*"))
    return extract_listing(entry, entry.listings[0], path.read_bytes())


def test_aps_ids_links_images_and_exclusions():
    result = items("aps-ar")
    assert all(len(i.external_id) == 8 for i in result.items)
    assert all(i.url.startswith("https://www.aps.dz/") for i in result.items)
    assert all(i.image_url.startswith("https://www.aps.dz/api/image/") for i in result.items)
    assert not any("/dossier/" in i.url or "/video/" in i.url for i in result.items)


def test_anadolu_dates_are_converted_to_utc():
    by_id = {i.external_id: i for i in items("aa-ar").items}
    first = by_id["4092100"]  # 17:51:47 +0300 in the feed
    assert first.published_at == datetime(2026, 10, 17, 14, 51, 47, tzinfo=UTC)


def test_mouradia_section_map_and_link_template():
    for item in items("mouradia-ar", "listing_2").items:
        assert item.section in ("president", "presidency")
        assert item.url == f"https://www.el-mouradia.dz/ar/{item.section}/{item.external_id}"
        assert item.image_url.startswith("https://backend.el-mouradia.dz/uploads/")
        assert len(item.lead) <= 301  # full body shortened to a lead


def test_elhidhab_naive_dates_read_as_algiers_time():
    by_id = {i.external_id: i for i in items("elhidhab-ar").items}
    assert by_id["12019"].published_at == datetime(2026, 10, 15, 7, 26, 53, tzinfo=UTC)


def test_djelfa_id_and_section_from_the_link():
    first = items("djelfainfo-ar").items[0]
    assert (first.external_id, first.section) == ("152481", "news/algerie")
    assert first.lead is None  # feed description repeats the title; lead from the page (M5)


# --- extractor behaviour on small configs ------------------------------------------------------


def config(**changes) -> SourceConfig:
    base = {
        "access_method": "json_api",
        "listings": ["https://site.dz/api/list"],
        "fields": {"id": "$.id", "title": "$.title", "link": "$.url", "published": "$.date"},
    }
    return SourceConfig.model_validate({**base, **changes})


def run(cfg: SourceConfig, data: list[dict]):
    import json

    return extract_listing(cfg, cfg.listings[0], json.dumps(data).encode())


def test_value_map_default_exclusion_and_templates():
    cfg = config(
        fields={
            "id": "$.id",
            "title": "$.title",
            "section": "$.cat",
            "image": "$.img",
            "kind": "$.kind",
        },
        value_maps={"section": {"1": "president", "_default": "presidency"}},
        templates={"link": "https://site.dz/{section}/{id}", "image": "https://cdn.site.dz{image}"},
        exclude={"kind": "^video$"},
    )
    result = run(
        cfg,
        [
            {"id": "a", "title": "A", "cat": 1, "img": "/a.jpg"},
            {"id": "b", "title": "B", "cat": 9},
            {"id": "c", "title": "C", "cat": 1, "kind": "video"},
        ],
    )
    a, b = result.items
    assert (a.url, a.image_url) == ("https://site.dz/president/a", "https://cdn.site.dz/a.jpg")
    assert (b.url, b.image_url) == ("https://site.dz/presidency/b", None)  # no image: no template
    assert result.excluded == 1


def test_missing_required_fields_are_rejected_not_guessed():
    result = run(config(), [{"id": 1, "url": "/x"}, {"title": "T", "url": "/y"}, "noise"])
    assert result.items == []
    assert result.rejected == ["item 0: no title", "item 1: no id", "item 2: not an object"]


def test_unreadable_date_keeps_the_article_as_first_seen():
    result = run(config(), [{"id": 1, "title": "T", "url": "/x", "date": "yesterday-ish"}])
    (item,) = result.items
    assert (item.published_at, item.published_at_confidence) == (None, "first_seen")
    assert result.problems and "yesterday-ish" in result.problems[0]


def test_relative_links_resolved_and_html_cleaned():
    (item,) = run(config(), [{"id": 7, "title": "<b>عاجل</b> &amp; خبر", "url": "/n/7"}]).items
    assert item.url == "https://site.dz/n/7"
    assert item.title == "عاجل & خبر"


def test_listings_merge_by_id_then_by_canonical_url():
    cfg = config()
    one = run(cfg, [{"id": 1, "title": "T", "url": "https://site.dz/a/?utm_source=x"}])
    two = run(
        cfg,
        [
            {"id": 1, "title": "T again", "url": "https://site.dz/a"},  # same id
            {"id": 2, "title": "T", "url": "https://www.site.dz/a/"},  # same article URL, new id
            {"id": 3, "title": "Other", "url": "https://site.dz/b"},
        ],
    )
    merged = merge_listings([one, two])
    assert [(i.external_id, i.title) for i in merged] == [("1", "T"), ("3", "Other")]


def test_content_hash_changes_with_title_lead_or_image():
    cfg = config(fields={"id": "$.id", "title": "$.title", "link": "$.url", "lead": "$.lead"})
    base = {"id": 1, "title": "T", "url": "/x", "lead": "L"}
    h1 = run(cfg, [base]).items[0].content_hash
    assert run(cfg, [base]).items[0].content_hash == h1
    assert run(cfg, [{**base, "lead": "L2"}]).items[0].content_hash != h1


# --- config errors fail at catalog load ------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"feilds": {}}, "Extra inputs"),  # typo
        ({"fields": {"id": "$.id", "title": "$.t"}}, "`link` needs a field or a template"),
        ({"templates": {"link": "https://x/{nope}"}}, "unknown field 'nope'"),
        (
            {"fields": {"id": {"path": "$.u", "regex": "\\d+"}, "title": "$.t", "link": "$.u"}},
            "capturing group",
        ),
        ({"fields": {"id": "id", "title": "$.t", "link": "$.u"}}, "must start with"),
        ({"access_method": "html"}, "has no extractor yet"),
        ({"access_method": "embedded"}, "`embedded` is required"),
        ({"exclude": {"missing": "x"}}, "unknown field 'missing'"),
        ({"dates": {"published_tz": "Africa/Algeirs"}}, "unknown time zone"),
    ],
)
def test_bad_configs_are_rejected(changes, message):
    with pytest.raises(ValidationError, match=message):
        config(**changes)


def test_catalog_file_typo_fails(tmp_path: Path):
    data = yaml.safe_load((DEFAULT_CATALOG / "awras-ar.yaml").read_text(encoding="utf-8"))
    data["poll_intervall_s"] = 60
    with pytest.raises(ValidationError, match="poll_intervall_s"):
        CatalogEntry.model_validate(data)


def test_stored_config_round_trip():
    entry = CATALOG["aps-ar"]
    assert SourceConfig.of(entry.model_dump(mode="json")) == SourceConfig.of(
        entry.model_dump(mode="json")
    )
    assert SourceConfig.of(entry.model_dump(mode="json")).embedded.kind == "next_f"


# --- building blocks -------------------------------------------------------------------------


def test_paths():
    data = {"a": {"b": [{"c": 1}, {"c": 2}]}, "wp:x": [{"u": "v"}], "n": None}
    assert find_first(data, "$.a.b[1].c") == 2
    assert list(find_all(data, "$.a.b[*].c")) == [1, 2]
    assert find_first(data, "$['wp:x'][0].u") == "v"
    assert find_first(data, "$.a.b[5].c") is None
    assert find_first(data, "$.missing.deeper") is None
    with pytest.raises(ValueError):
        find_first(data, "$.a..b")


@pytest.mark.parametrize(
    ("value", "tz", "expected"),
    [
        ("2026-10-17T14:07:54.254Z", "UTC", datetime(2026, 10, 17, 14, 7, 54, 254000, UTC)),
        ("2026-10-20T19:08:52+01:00", "UTC", datetime(2026, 10, 20, 18, 8, 52, tzinfo=UTC)),
        ("2026-10-17T14:17:22", "UTC", datetime(2026, 10, 17, 14, 17, 22, tzinfo=UTC)),
        ("2026-10-17T14:17:22", "Africa/Algiers", datetime(2026, 10, 17, 13, 17, 22, tzinfo=UTC)),
        (
            "2026-07-01 12:00:00",
            "Africa/Algiers",
            datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
        ),  # no DST
        ("Sat, 17 Oct 2026 17:51:47 +0300", "UTC", datetime(2026, 10, 17, 14, 51, 47, tzinfo=UTC)),
        (
            "Sat, 17 Oct 2026 17:51:47 -0000",
            "Africa/Algiers",
            datetime(2026, 10, 17, 16, 51, 47, tzinfo=UTC),
        ),
    ],
)
def test_dates(value, tz, expected):
    assert parse_date(value, tz) == expected


def test_bad_date_raises():
    with pytest.raises(ValueError):
        parse_date("hier à 15h", "Africa/Algiers")


def test_canonical_url_key():
    key = canonical_url_key("https://elauresnews.dz/%d8%a7%d8%b3/")
    assert canonical_url_key("http://WWW.ElAuresNews.dz/اس?utm_source=fb#top") == key
    assert canonical_url_key("https://elauresnews.dz:443/%D8%A7%D8%B3") == key
    assert canonical_url_key("https://a.dz/p?id=2&page=1") == canonical_url_key(
        "https://a.dz/p?page=1&id=2&fbclid=x"
    )
    assert canonical_url_key("https://a.dz/p?id=2") != canonical_url_key("https://a.dz/p?id=3")
    assert canonical_url_key("/n/7", base="https://a.dz/list") == "https://a.dz/n/7"


def test_clean_text():
    assert clean_text("<p>الجزائر&nbsp;- افتتحت</p>\n\n") == "الجزائر - افتتحت"
    assert clean_text("&amp;quot;x&amp;quot;") == '"x"'  # double-escaped feeds
    assert clean_text("one two three four", max_chars=9) == "one two…"
    decomposed = "أ"  # alef + combining hamza above
    assert clean_text(decomposed) == "أ"


def test_title_on_page():
    page = '<html><head><meta property="og:title" content="العقار | الأوراس"></head>'.encode()
    assert title_on_page("العقـار", page)  # tatweel ignored
    assert not title_on_page("خبر آخر تماما", page)


# --- live validation path, against a fake site -------------------------------------------------


def test_live_validation_through_the_fetcher():
    entry = CATALOG["djelfainfo-ar"]
    listing = fixture("djelfainfo-ar", "listing_1.xml")
    article = fixture("djelfainfo-ar", "article_152481.html")
    other = b'<html><head><meta property="og:title" content="something else"></head></html>'

    def handler(request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        if url.endswith("/robots.txt"):
            return httpx2.Response(200, content=fixture("djelfainfo-ar", "robots.txt"))
        if url == entry.listings[0]:
            return httpx2.Response(200, content=listing)
        if url.endswith("/152481.html"):
            return httpx2.Response(200, content=article)
        if url.endswith(".html"):
            return httpx2.Response(200, content=other)
        return httpx2.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    class Clock:
        t = 0.0

        def monotonic(self):
            return self.t

        def now(self):
            return NOW

        async def sleep(self, seconds):
            self.t += seconds

    async def scenario():
        async with Fetcher(
            Settings(),
            transport=httpx2.MockTransport(handler),
            clock=Clock(),
            rng=random.Random(0),
        ) as fetcher:
            return await validate_live(entry, fetcher, now=NOW)

    report = asyncio.run(scenario())
    checks = {check.name: check for check in report.checks}
    assert checks["listings fetched"].ok and checks["images load"].ok
    assert not checks["links open the article"].ok  # only 152481's page carries its title
    assert "152478" in checks["links open the article"].detail


# --- article pages (M5) ------------------------------------------------------------------------


def test_article_page_fills_only_what_the_listing_lacks():
    from dataclasses import replace

    from sabq.extract.config import ArticlePage
    from sabq.extract.page import enrich, read_page

    page = fixture("djelfainfo-ar", "article_152481.html")
    data = read_page(page)
    assert data.json_ld and data.json_ld[0]["@type"] == "NewsArticle"  # BreadcrumbList ignored

    item = replace(items("djelfainfo-ar").items[0], published_at=None)
    rules = ArticlePage(
        lead="og:description",
        published="json_ld:datePublished",
        author="json_ld:author",
        image="og:image",
    )
    filled = enrich(item, rules, page, naive_tz="UTC", lead_max=300)
    assert filled.lead.startswith("الرئيس تبون يجري حركة جزئية في سلك الولاة")
    assert filled.published_at == datetime(2026, 10, 20, 18, 8, 52, tzinfo=UTC)  # +01:00 on page
    assert filled.author == "محمد شبيري"
    assert filled.image_url == item.image_url  # the listing had one: kept
    assert filled.content_hash != item.content_hash  # the lead is part of what readers see
    assert enrich(item, ArticlePage(), page, naive_tz="UTC", lead_max=300) is item
