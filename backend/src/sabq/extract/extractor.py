"""One generic extractor: a listing response + the source config → articles.

    response bytes → raw items (feed entries, JSON objects, or objects embedded in the page)
                   → field values (paths, regex) → value maps → exclusions → templates
                   → cleaned article (UTC dates, absolute URLs, NFC text, lead only)

Items missing an ID, title or link are rejected (counted, never guessed); a date that cannot be
read leaves the article with `first_seen` confidence and is reported as a problem. Listings of
one source are merged by ID, then by canonical URL key (`merge_listings`).
"""

import hashlib
import json
import re
import string
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import feedparser

from sabq.extract.config import Embedded, FieldRule, SourceConfig
from sabq.extract.dates import parse_date
from sabq.extract.paths import find_all, find_first
from sabq.extract.text import clean_text
from sabq.extract.urls import canonical_url_key

MAX_EXTERNAL_ID = 255
_NEXT_F_PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')


class ExtractError(Exception):
    """The response is not what the config expects (not a feed, not JSON, no embedded data)."""


@dataclass(frozen=True)
class ExtractedItem:
    external_id: str
    url: str
    canonical_url_key: str
    title: str
    lead: str | None
    image_url: str | None
    section: str | None
    author: str | None
    published_at: datetime | None  # aware UTC
    published_at_confidence: str  # source_meta | page_text | first_seen
    modified_at: datetime | None
    content_hash: str  # title + lead + image: a change means a new article version


@dataclass
class ListingResult:
    url: str
    items: list[ExtractedItem] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)  # "item 3: no title"
    excluded: int = 0  # dropped by `exclude` (dossiers, videos...)
    problems: list[str] = field(default_factory=list)  # kept, but something was unreadable


def extract_listing(config: SourceConfig, listing_url: str, body: bytes) -> ListingResult:
    result = ListingResult(listing_url)
    rules = config.fields.rules()
    regexes = {name: re.compile(rule.regex) for name, rule in rules.items() if rule.regex}
    exclude = {name: re.compile(pattern) for name, pattern in config.exclude.items()}

    for position, raw in enumerate(raw_items(config, body)):
        if not isinstance(raw, dict):
            result.rejected.append(f"item {position}: not an object")
            continue
        values = {name: _value(raw, rule, regexes.get(name)) for name, rule in rules.items()}
        _apply_value_maps(values, config.value_maps)
        if any(values.get(name) and rx.search(values[name]) for name, rx in exclude.items()):
            result.excluded += 1
            continue
        snapshot = dict(values)
        for name, template in config.templates.items():
            values[name] = _render(template, snapshot)
        item = _build(config, listing_url, values, position, result)
        if item is not None:
            result.items.append(item)
    return result


def merge_listings(results: list[ListingResult]) -> list[ExtractedItem]:
    """First occurrence wins: the same article in several listings is one article."""
    by_id: dict[str, ExtractedItem] = {}
    keys: set[str] = set()
    for result in results:
        for item in result.items:
            if item.external_id in by_id or item.canonical_url_key in keys:
                continue
            by_id[item.external_id] = item
            keys.add(item.canonical_url_key)
    return list(by_id.values())


# --- response → raw items ------------------------------------------------------------------


def raw_items(config: SourceConfig, body: bytes) -> list[Any]:
    kind = config.payload_kind
    if kind == "feed":
        parsed = feedparser.parse(body)
        if parsed.bozo and not parsed.entries:
            raise ExtractError(f"not a readable feed: {parsed.get('bozo_exception')}")
        data: Any = parsed.entries
    elif kind == "json":
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise ExtractError(f"not JSON: {exc}") from None
    else:
        data = embedded_objects(config.embedded, body.decode("utf-8", errors="replace"))
    return list(find_all(data, config.items))


def embedded_objects(rule: Embedded, page: str) -> list[Any]:
    """Next.js app router pages stream their data as `self.__next_f.push([1, "<chunk>"])`; the
    chunks joined are a text in which each item is a JSON object starting with `object_start`."""
    chunks = _NEXT_F_PUSH.findall(page)
    if not chunks:
        raise ExtractError("no self.__next_f data in the page")
    payload = "".join(json.loads(chunk) for chunk in chunks)
    decoder, objects, start = json.JSONDecoder(), [], 0
    while (position := payload.find(rule.object_start, start)) != -1:
        try:
            obj, start = decoder.raw_decode(payload, position)
            objects.append(obj)
        except ValueError:
            start = position + 1
    return objects


# --- raw item → values -----------------------------------------------------------------------


def _value(raw: dict, rule: FieldRule, regex: re.Pattern | None) -> str | None:
    """First non-empty value among the rule's paths (after its regex, if any)."""
    for path in rule.paths:
        value = find_first(raw, path)
        if value is None or isinstance(value, (dict, list)):
            continue
        text = str(value).strip()
        if regex is not None:
            match = regex.search(text)
            text = match.group(1).strip() if match else ""
        if text:
            return text
    return None


def _apply_value_maps(values: dict[str, str | None], maps: dict[str, dict[str, str]]) -> None:
    for name, mapping in maps.items():
        value = values.get(name)
        if value is not None and value in mapping:
            values[name] = mapping[value]
        elif "_default" in mapping:
            values[name] = mapping["_default"]


class _TemplateFormatter(string.Formatter):
    def format_field(self, value: Any, format_spec: str) -> str:
        if format_spec == "path":
            return quote(str(value), safe="/%")
        return super().format_field(value, format_spec)


def _render(template: str, values: dict[str, str | None]) -> str | None:
    """None when a value the template needs is missing (e.g. no image)."""
    try:
        refs = {name for _, name, _, _ in string.Formatter().parse(template) if name}
        if any(not values.get(name) for name in refs):
            return None
        return _TemplateFormatter().format(template, **values)
    except (KeyError, ValueError):
        return None


# --- values → article ------------------------------------------------------------------------


def _build(
    config: SourceConfig,
    listing_url: str,
    values: dict[str, str | None],
    position: int,
    result: ListingResult,
) -> ExtractedItem | None:
    external_id = values.get("id")
    title = clean_text(values.get("title"))
    url = _absolute(listing_url, values.get("link"))
    missing = [
        name for name, value in (("id", external_id), ("title", title), ("link", url)) if not value
    ]
    if missing:
        result.rejected.append(f"item {position}: no {', '.join(missing)}")
        return None
    if len(external_id) > MAX_EXTERNAL_ID:
        result.rejected.append(f"item {position}: id longer than {MAX_EXTERNAL_ID}")
        return None

    tz = config.dates.published_tz
    published, confidence = None, "first_seen"
    if values.get("published"):
        try:
            published, confidence = parse_date(values["published"], tz), config.dates.confidence
        except ValueError as exc:
            result.problems.append(f"{external_id}: published: {exc}")
    modified = None
    if values.get("modified"):
        try:
            modified = parse_date(values["modified"], tz)
        except ValueError as exc:
            result.problems.append(f"{external_id}: modified: {exc}")

    lead = clean_text(values.get("lead"), config.lead_max_chars) or None
    image = _absolute(listing_url, values.get("image"))
    digest = hashlib.sha256("\n".join((title, lead or "", image or "")).encode()).hexdigest()
    return ExtractedItem(
        external_id=external_id,
        url=url,
        canonical_url_key=canonical_url_key(url),
        title=title,
        lead=lead,
        image_url=image,
        section=clean_text(values.get("section")) or None,
        author=clean_text(values.get("author")) or None,
        published_at=published,
        published_at_confidence=confidence,
        modified_at=modified,
        content_hash=digest,
    )


def _absolute(base: str, value: str | None) -> str | None:
    if not value:
        return None
    url = urljoin(base, value.strip())
    return url if urlsplit(url).scheme in ("http", "https") and urlsplit(url).netloc else None
