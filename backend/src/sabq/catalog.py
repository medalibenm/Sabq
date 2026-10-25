"""Load the source catalog (`catalog/*.yaml`, reviewed in git) into the database.

Each file is validated in full: the source columns here, the extraction part (listings, fields,
templates...) by `sabq.extract.SourceConfig`. Unknown keys are errors, so typos fail at load.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sabq.audit import record
from sabq.db.models import Source, SourceConfigVersion, SourceWilaya, Wilaya
from sabq.extract.config import SourceConfig

NATIONAL = "00"


class RobotsCheck(BaseModel):
    checked_at: date
    result: str


class CatalogEntry(SourceConfig):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    home_url: str
    language: str
    kind: Literal["official", "agency", "national", "local", "international"]
    wilayas: list[str] = Field(default_factory=lambda: [NATIONAL])  # none listed: National
    tier: Literal["priority", "normal", "secondary"]
    poll_interval_s: int = Field(ge=60)
    egress: Literal["default", "dz_proxy"] = "default"
    enabled: bool = True
    robots: RobotsCheck

    @field_validator("wilayas")
    @classmethod
    def wilaya_codes(cls, codes: list[str]) -> list[str]:
        for code in codes:
            if len(code) != 2 or not code.isdigit():
                raise ValueError(f"wilaya code must be two digits, got {code!r}")
        return codes or [NATIONAL]


@dataclass
class LoadResult:
    created: list[str]
    updated: list[str]
    unchanged: list[str]


def read_catalog(directory: Path) -> list[CatalogEntry]:
    entries = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        entry = CatalogEntry.model_validate(data)
        if entry.slug != path.stem:
            raise ValueError(f"{path.name}: slug {entry.slug!r} does not match the file name")
        entries.append(entry)
    return entries


def _config(entry: CatalogEntry) -> dict[str, Any]:
    return entry.model_dump(mode="json")


def load_catalog(session: Session, entries: list[CatalogEntry], actor: str) -> LoadResult:
    """Upsert sources. A config change creates a new source_config_versions row."""
    wilaya_ids = dict(session.execute(select(Wilaya.code, Wilaya.id)).all())
    result = LoadResult([], [], [])

    for entry in entries:
        unknown = [c for c in entry.wilayas if c not in wilaya_ids]
        if unknown:
            raise ValueError(f"{entry.slug}: unknown wilaya code(s) {unknown}")

        config = _config(entry)
        robots_checked_at = datetime.combine(entry.robots.checked_at, datetime.min.time(), UTC)
        columns = {
            "name": entry.name,
            "home_url": entry.home_url,
            "language": entry.language,
            "kind": entry.kind,
            "tier": entry.tier,
            "poll_interval_s": entry.poll_interval_s,
            "access_method": entry.access_method,
            "egress": entry.egress,
            "enabled": entry.enabled,
            "robots_checked_at": robots_checked_at,
        }

        source = session.scalar(select(Source).where(Source.slug == entry.slug))
        if source is None:
            source = Source(slug=entry.slug, config=config, config_version=1, **columns)
            session.add(source)
            session.flush()
            session.add(
                SourceConfigVersion(
                    source_id=source.id,
                    version=1,
                    config=config,
                    changed_by=actor,
                    reason="added to catalog",
                )
            )
            record(session, actor, "source.created", "source", source.slug)
            result.created.append(entry.slug)
        elif source.config != config:
            source.config_version += 1
            source.config = config
            for key, value in columns.items():
                setattr(source, key, value)
            session.add(
                SourceConfigVersion(
                    source_id=source.id,
                    version=source.config_version,
                    config=config,
                    changed_by=actor,
                    reason="catalog file changed",
                )
            )
            record(
                session,
                actor,
                "source.config_changed",
                "source",
                source.slug,
                {"version": source.config_version},
            )
            result.updated.append(entry.slug)
        else:
            result.unchanged.append(entry.slug)
            continue

        session.execute(delete(SourceWilaya).where(SourceWilaya.source_id == source.id))
        session.add_all(
            SourceWilaya(source_id=source.id, wilaya_id=wilaya_ids[c], assignment_method="manual")
            for c in entry.wilayas
        )

    session.flush()
    return result
