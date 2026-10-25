"""Reading an article's own page for what its listing lacks (decision 2026-10-21).

Only metadata the site publishes for this purpose is read: `<meta>` tags (Open Graph, article:,
twitter:, name=) and JSON-LD article objects. Listing values always win; the page only fills
gaps (e.g. Djelfa Info's feed has no lead, its page has `og:description`).
"""

import contextlib
import json
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from sabq.extract.config import ArticlePage
from sabq.extract.dates import parse_date
from sabq.extract.extractor import ExtractedItem, content_hash
from sabq.extract.text import clean_text

ARTICLE_TYPES = {
    "NewsArticle",
    "Article",
    "ReportageNewsArticle",
    "AnalysisNewsArticle",
    "BlogPosting",
}

PEOPLE = {"author", "creator", "publisher"}  # objects whose `name` is wanted, not their `url`


@dataclass
class PageData:
    meta: dict[str, str] = field(default_factory=dict)  # "og:description", "description"...
    json_ld: list[dict[str, Any]] = field(default_factory=list)  # article objects only


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.data = PageData()
        self._in_json_ld = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key and values.get("content") is not None:
                self.data.meta.setdefault(key.strip().lower(), values["content"])
        elif tag == "script" and (values.get("type") or "").lower() == "application/ld+json":
            self._in_json_ld, self._buffer = True, []

    def handle_data(self, data):
        if self._in_json_ld:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            with contextlib.suppress(ValueError):  # broken JSON-LD is common; meta may do
                self.data.json_ld.extend(_articles(json.loads("".join(self._buffer))))


def _articles(node: Any) -> list[dict]:
    if isinstance(node, list):
        return [a for child in node for a in _articles(child)]
    if not isinstance(node, dict):
        return []
    if "@graph" in node:
        return _articles(node["@graph"])
    kinds = node.get("@type")
    kinds = set(kinds) if isinstance(kinds, list) else {kinds}
    return [node] if kinds & ARTICLE_TYPES else []


def read_page(page: bytes) -> PageData:
    parser = _PageParser()
    parser.feed(page.decode("utf-8", errors="replace"))
    return parser.data


def page_value(data: PageData, source: str) -> str | None:
    kind, key = source.split(":", 1)
    if kind == "json_ld":
        prefer = ("name", "url") if key in PEOPLE else ("url", "name")
        for article in data.json_ld:
            value = _plain(article.get(key), prefer)
            if value:
                return value
        return None
    name = key if kind == "meta" else f"{kind}:{key}"
    return (data.meta.get(name.lower()) or "").strip() or None


def _plain(value: Any, prefer: tuple[str, str]) -> str | None:
    """JSON-LD values can be a string, an object ({"url": ...}, {"name": ...}) or a list."""
    if isinstance(value, list):
        return next((v for v in (_plain(x, prefer) for x in value) if v), None)
    if isinstance(value, dict):
        return _plain(value.get(prefer[0]) or value.get(prefer[1]), prefer)
    return str(value).strip() if value is not None else None


def enrich(
    item: ExtractedItem, rules: ArticlePage, page: bytes, *, naive_tz: str, lead_max: int
) -> ExtractedItem:
    data = read_page(page)
    changes: dict[str, Any] = {}
    if item.lead is None and rules.lead:
        changes["lead"] = clean_text(page_value(data, rules.lead), lead_max) or None
    if item.image_url is None and rules.image:
        image = page_value(data, rules.image)
        url = urljoin(item.url, image) if image else None
        if url and urlsplit(url).scheme in ("http", "https"):
            changes["image_url"] = url
    if item.published_at is None and rules.published:
        value = page_value(data, rules.published)
        if value:
            try:
                changes["published_at"] = parse_date(value, naive_tz)
                changes["published_at_confidence"] = "source_meta"
            except ValueError:
                pass
    if item.author is None and rules.author:
        changes["author"] = clean_text(page_value(data, rules.author)) or None
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        return item
    updated = replace(item, **changes)
    digest = content_hash(updated.title, updated.lead, updated.image_url)
    return replace(updated, content_hash=digest)
