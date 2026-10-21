"""Validating a config (docs/architecture.md#validating-a-config).

Offline, against saved fixtures in `tests/fixtures/<slug>/`: `listing_*` (two or more snapshots,
any of the source's listings) and `article_<id>.html` (pages whose title must match).
Live, through `sabq.fetch` (robots.txt and pacing apply): every listing, the first one again a
moment later (stability), a few article links (the title must be on the page) and images
(200 and an image type).
"""

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from sabq.catalog import CatalogEntry
from sabq.extract.extractor import ExtractedItem, ExtractError, extract_listing, merge_listings
from sabq.extract.text import clean_text
from sabq.fetch import Fetcher, FetchError

FUTURE_TOLERANCE = timedelta(minutes=10)
MAX_AGE = timedelta(days=30)
LINKS_TO_OPEN = 3
IMAGES_TO_LOAD = 2


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    slug: str
    checks: list[Check] = field(default_factory=list)
    items: list[ExtractedItem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, ok, detail))

    def text(self) -> str:
        status = "OK" if self.ok else "FAILED"
        lines = [f"{self.slug}: {status} ({len(self.items)} articles)"]
        lines += [f"  [{'ok' if c.ok else 'FAIL'}] {c.name}: {c.detail}" for c in self.checks]
        return "\n".join(lines)


# --- listings ------------------------------------------------------------------------------


def check_listings(
    entry: CatalogEntry,
    snapshots: list[tuple[str, bytes]],
    *,
    now: datetime,
    recency: bool = True,
    report: Report | None = None,
) -> Report:
    report = report or Report(entry.slug)
    results = []
    for url, body in snapshots:
        try:
            results.append(extract_listing(entry, url, body))
        except ExtractError as exc:
            report.add("response readable", False, f"{url}: {exc}")
    if not results:
        return report

    counts = ", ".join(
        f"{len(r.items)}" + (f" (+{r.excluded} excluded)" if r.excluded else "") for r in results
    )
    report.add("items found", all(r.items for r in results), f"per snapshot: {counts}")
    rejected = [reason for r in results for reason in r.rejected]
    report.add(
        "required fields",
        not rejected,
        f"{len(rejected)} rejected, e.g. {rejected[:3]}" if rejected else "id, title, link on all",
    )
    report.items = items = merge_listings(results)
    _check_ids(report, results)
    _check_dates(report, entry, results, items, now, recency)

    site = urlsplit(entry.home_url).hostname.removeprefix("www.")
    foreign = [i.url for i in items if not _on_site(i.url, site)]
    report.add(
        "links on the site",
        not foreign,
        f"not on {site}: {foreign[:3]}" if foreign else f"all on {site}",
    )
    dirty = [
        i.external_id
        for i in items
        if "<" in i.title
        or not unicodedata.is_normalized("NFC", i.title)
        or (i.lead and len(i.lead) > entry.lead_max_chars + 1)
    ]
    report.add("clean text", not dirty, f"bad: {dirty[:5]}" if dirty else "no HTML, NFC, lead only")
    with_image = sum(1 for i in items if i.image_url)
    image_expected = "image" in entry.fields.rules()
    report.add(
        "images",
        not image_expected or with_image > 0,
        f"{with_image}/{len(items)} have one" if image_expected else "none in listings",
    )
    return report


def _check_ids(report: Report, results) -> None:
    id_to_key: dict[str, str] = {}
    key_to_id: dict[str, str] = {}
    seen_in: dict[str, int] = {}
    clashes = []
    for result in results:
        for item in {i.external_id: i for i in result.items}.values():
            seen_in[item.external_id] = seen_in.get(item.external_id, 0) + 1
            if id_to_key.setdefault(item.external_id, item.canonical_url_key) != (
                item.canonical_url_key
            ):
                clashes.append(f"id {item.external_id} has two URLs")
            if key_to_id.setdefault(item.canonical_url_key, item.external_id) != item.external_id:
                clashes.append(f"{item.url} has two ids")
    repeated = sum(1 for n in seen_in.values() if n > 1)
    report.add(
        "IDs unique and stable",
        not clashes,
        "; ".join(clashes[:3]) or f"{len(id_to_key)} ids, {repeated} seen in several snapshots",
    )


def _check_dates(report, entry, results, items, now, recency) -> None:
    if "published" not in entry.fields.rules():
        report.add("dates", True, "no date in listings: first_seen until the article page is read")
        return
    failures = [p for r in results for p in r.problems][:3]
    undated = [i.external_id for i in items if i.published_at is None]
    if undated:
        failures.append(f"no date: {undated[:3]}")
    limit = now + FUTURE_TOLERANCE
    future = [i.external_id for i in items if i.published_at and i.published_at > limit]
    if future:
        failures.append(f"in the future: {future[:3]}")
    dated = [i.published_at for i in items if i.published_at]
    if recency and dated and now - max(dated) > MAX_AGE:
        failures.append(f"newest is {max(dated):%Y-%m-%d}, older than {MAX_AGE.days} days")
    newest = f"newest {max(dated):%Y-%m-%d %H:%M} UTC" if dated else "none"
    report.add("dates", not failures, "; ".join(failures) or f"all UTC, {newest}")


def _on_site(url: str, site: str) -> bool:
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    return host == site or host.endswith("." + site)


# --- article pages -------------------------------------------------------------------------


class _TitleParser(HTMLParser):
    """Collects og:title, <title>, <h1> text and JSON-LD headlines (by plain search)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titles: list[str] = []
        self._capture: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("property", values.get("name")) in (
            "og:title",
            "twitter:title",
        ):
            self.titles.append(values.get("content") or "")
        elif tag in ("title", "h1"):
            self._capture, self._buffer = tag, []

    def handle_data(self, data):
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == self._capture:
            self.titles.append("".join(self._buffer))
            self._capture = None


def page_titles(page: bytes) -> list[str]:
    parser = _TitleParser()
    parser.feed(page.decode("utf-8", errors="replace"))
    return [t for t in parser.titles if t.strip()]


def _norm(text: str) -> str:
    # tatweel (ـ) is decoration: "العقـار" == "العقار"
    return " ".join(clean_text(text).replace("ـ", "").split()).casefold()


def title_on_page(title: str, page: bytes) -> bool:
    wanted = _norm(title)
    for candidate in map(_norm, page_titles(page)):
        if wanted in candidate or (len(candidate) >= 10 and candidate in wanted):
            return True
    return False


# --- offline (fixtures) and live -------------------------------------------------------------


def validate_fixtures(entry: CatalogEntry, folder: Path, *, now: datetime) -> Report:
    report = Report(entry.slug)
    listings = sorted(folder.glob("listing_*"))
    if len(listings) < 2:
        report.add("fixtures", False, f"need two listing_* snapshots in {folder}")
        if not listings:
            return report
    snapshots = [(entry.listings[0], path.read_bytes()) for path in listings]
    check_listings(entry, snapshots, now=now, recency=False, report=report)
    by_id = {item.external_id: item for item in report.items}
    for page in sorted(folder.glob("article_*.html")):
        article_id = page.stem.removeprefix("article_")
        item = by_id.get(article_id)
        if item is None:
            report.add(f"article {article_id}", False, "not found in the listings")
        elif entry.link_check == "skip":
            report.add(f"article {article_id}", True, "title check skipped (link_check: skip)")
        else:
            found = title_on_page(item.title, page.read_bytes())
            report.add(
                f"article {article_id}",
                found,
                "title on the page" if found else f"title not on the page: {item.title[:60]}",
            )
    return report


async def validate_live(entry: CatalogEntry, fetcher: Fetcher, *, now: datetime) -> Report:
    report = Report(entry.slug)
    snapshots: list[tuple[str, bytes]] = []
    try:
        for url in [*entry.listings, entry.listings[0]]:  # first listing twice: stability
            result = await fetcher.get(url, egress=entry.egress)
            if result.not_modified:
                body = next(b for u, b in snapshots if u == url)
            elif result.ok:
                body = result.content
            else:
                report.add("listings fetched", False, f"{url}: HTTP {result.status}")
                return report
            snapshots.append((url, body))
    except FetchError as exc:
        report.add("listings fetched", False, str(exc))
        return report
    report.add("listings fetched", True, f"{len(entry.listings)} listing(s), first one twice")
    check_listings(entry, snapshots, now=now, report=report)

    if entry.link_check == "skip":
        report.add("links open the article", True, "skipped (link_check: skip)")
    else:
        failures = []
        for item in report.items[:LINKS_TO_OPEN]:
            try:
                page = await fetcher.get(item.url, egress=entry.egress)
                if not (page.ok and title_on_page(item.title, page.content)):
                    failures.append(f"{item.external_id} (HTTP {page.status})")
            except FetchError as exc:
                failures.append(f"{item.external_id}: {exc}")
        opened = min(LINKS_TO_OPEN, len(report.items))
        report.add(
            "links open the article",
            opened > 0 and not failures,
            f"title missing: {failures}" if failures else f"{opened} opened, titles found",
        )

    images = [item.image_url for item in report.items if item.image_url][:IMAGES_TO_LOAD]
    failures = []
    for url in images:
        try:
            result = await fetcher.get(url, egress=entry.egress)
            kind = result.headers.get("content-type", "")
            if not (result.ok and kind.startswith("image/")):
                failures.append(f"{url} (HTTP {result.status}, {kind or 'no type'})")
        except FetchError as exc:
            failures.append(f"{url}: {exc}")
    if images:
        report.add(
            "images load",
            not failures,
            f"failed: {failures}" if failures else f"{len(images)} loaded",
        )
    return report
