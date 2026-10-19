"""SQLAlchemy models. Tables are added in M2 (docs/architecture.md, data model)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
