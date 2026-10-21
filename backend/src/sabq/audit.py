"""Audit trail for admin mutations (access changes, catalog changes, cluster decisions)."""

from typing import Any

from sqlalchemy.orm import Session

from sabq.db.models import AuditEvent


def record(
    session: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | int,
    details: dict[str, Any] | None = None,
    *,
    organisation_id: int | None = None,
    user_id: int | None = None,
) -> None:
    session.add(
        AuditEvent(
            organisation_id=organisation_id,
            user_id=user_id,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            details=details or {},
        )
    )
