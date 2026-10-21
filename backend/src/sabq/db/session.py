"""Database engines and sessions."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from sabq.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@lru_cache
def get_sync_engine() -> Engine:
    """For the CLI and the catalog loader (short, one-off commands)."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sync_sessionmaker() -> sessionmaker:
    return sessionmaker(get_sync_engine(), expire_on_commit=False)
