"""The extraction part of a source config (`catalog/<slug>.yaml`), docs/architecture.md layer 2.

    access_method: rss | wp_json | json_api | embedded
    listings: [URL, ...]           # merged and de-duplicated by ID
    items: $[*]                    # where the item list is (JSON / embedded); feeds: their entries
    embedded: {kind: next_f, object_start: '{"id_article":'}   # access_method: embedded only
    fields:                        # path, list of paths (first non-empty), or {path, regex}
      id: $.id                     # required; regex takes the first group
      title: $.title.rendered      # required
      link: $.link                 # required unless a template builds it
      published / modified / lead / image / section / author: optional
      <other name>: ...            # extra values, for templates and exclusions only
    value_maps: {section: {"1": president, _default: presidency}}
    templates: {link: "https://site/{section}/{id}", image: "https://site/api/image/{image}"}
                                   # {name:path} percent-encodes the value (keeps "/")
    exclude: {alias: '^(dossier|video)/'}   # drop the item when the value matches
    dates: {published_tz: UTC, confidence: source_meta}   # tz for naive dates
    lead_max_chars: 300
    article_page: {...}            # what to read from article pages (ingestion, M5)
    link_check: title | skip       # validation: does the link show the article title?

Feed items are feedparser entries: `$.title`, `$.link`, `$.id` (guid), `$.published`,
`$.summary`, `$.enclosures[0].href`, `$.tags[0].term`, `$.author`.
"""

import re
import string
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sabq.extract.paths import compile_path

PayloadKind = Literal["feed", "json", "embedded"]
PAYLOAD_KIND: dict[str, PayloadKind] = {
    "rss": "feed",
    "wp_json": "json",
    "json_api": "json",
    "embedded": "embedded",
}
OUTPUT_FIELDS = (
    "id",
    "title",
    "link",
    "published",
    "modified",
    "lead",
    "image",
    "section",
    "author",
)
TEMPLATE_SPECS = {"", "path"}


class FieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | list[str]
    regex: str | None = None

    @property
    def paths(self) -> list[str]:
        return [self.path] if isinstance(self.path, str) else self.path

    @field_validator("path")
    @classmethod
    def paths_compile(cls, value: str | list[str]) -> str | list[str]:
        for path in [value] if isinstance(value, str) else value:
            compile_path(path)
        if value == []:
            raise ValueError("at least one path")
        return value

    @field_validator("regex")
    @classmethod
    def regex_has_a_group(cls, value: str | None) -> str | None:
        if value is not None and re.compile(value).groups < 1:
            raise ValueError(f"regex needs a capturing group: {value!r}")
        return value


FieldSpec = str | list[str] | FieldRule


def as_rule(spec: FieldSpec) -> FieldRule:
    return spec if isinstance(spec, FieldRule) else FieldRule(path=spec)


class Fields(BaseModel):
    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, FieldSpec]

    id: FieldSpec
    title: FieldSpec
    link: FieldSpec | None = None
    published: FieldSpec | None = None
    modified: FieldSpec | None = None
    lead: FieldSpec | None = None
    image: FieldSpec | None = None
    section: FieldSpec | None = None
    author: FieldSpec | None = None

    @model_validator(mode="after")
    def specs_are_valid(self) -> "Fields":
        self.rules()  # plain-string specs are checked when turned into FieldRules
        return self

    def rules(self) -> dict[str, FieldRule]:
        named = {name: getattr(self, name) for name in OUTPUT_FIELDS}
        return {
            name: as_rule(spec)
            for name, spec in {**named, **(self.__pydantic_extra__ or {})}.items()
            if spec is not None
        }


class Embedded(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["next_f"]  # Next.js app router payload, `self.__next_f.push([1, "..."])`
    object_start: str = Field(pattern=r"^\{")  # each item is the JSON object starting with this


class DateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    published_tz: str = "UTC"
    confidence: Literal["source_meta", "page_text"] = "source_meta"
    tz_verified: bool = True

    @field_validator("published_tz")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown time zone {value!r}") from None
        return value


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_method: Literal["rss", "wp_json", "sitemap", "embedded", "json_api", "html", "headless"]
    listings: list[str] = Field(min_length=1)
    items: str = "$[*]"
    embedded: Embedded | None = None
    fields: Fields
    value_maps: dict[str, dict[str, str]] = {}
    templates: dict[str, str] = {}
    exclude: dict[str, str] = {}
    dates: DateRule = DateRule()
    lead_max_chars: int = Field(default=300, ge=50)
    article_page: dict[str, str] | None = None
    # Validation opens a few links and looks for the article title. `skip` only for sites that
    # answer every URL with the same JavaScript page (El Mouradia); check those in a browser.
    link_check: Literal["title", "skip"] = "title"

    @classmethod
    def of(cls, stored: dict) -> "SourceConfig":
        """The extraction part of a stored catalog config (`sources.config`)."""
        return cls.model_validate({k: v for k, v in stored.items() if k in cls.model_fields})

    @property
    def payload_kind(self) -> PayloadKind:
        return PAYLOAD_KIND[self.access_method]

    @field_validator("listings")
    @classmethod
    def absolute_urls(cls, urls: list[str]) -> list[str]:
        for url in urls:
            if not url.startswith("https://") and not url.startswith("http://"):
                raise ValueError(f"listing must be an absolute http(s) URL: {url!r}")
        return urls

    @model_validator(mode="after")
    def consistent(self) -> "SourceConfig":
        if self.access_method not in PAYLOAD_KIND:
            raise ValueError(f"access_method {self.access_method!r} has no extractor yet")
        if (self.access_method == "embedded") != (self.embedded is not None):
            raise ValueError("`embedded` is required for access_method embedded, and only then")
        compile_path(self.items)
        names = set(self.fields.rules())
        if "link" not in names and "link" not in self.templates:
            raise ValueError("`link` needs a field or a template")
        for section in ("value_maps", "exclude"):
            for name in getattr(self, section):
                if name not in names:
                    raise ValueError(f"{section}: unknown field {name!r}")
        for name, template in self.templates.items():
            if name not in OUTPUT_FIELDS:
                raise ValueError(f"templates: {name!r} is not an output field")
            for ref, spec in template_refs(template):
                if ref not in names:
                    raise ValueError(f"templates.{name}: unknown field {ref!r}")
                if spec not in TEMPLATE_SPECS:
                    raise ValueError(f"templates.{name}: unknown format {spec!r} (use :path)")
        for pattern in self.exclude.values():
            re.compile(pattern)
        return self


def template_refs(template: str) -> list[tuple[str, str]]:
    return [
        (name, spec or "")
        for _, name, spec, _ in string.Formatter().parse(template)
        if name is not None
    ]
