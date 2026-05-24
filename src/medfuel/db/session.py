from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from medfuel.config import get_settings
from medfuel.db.orm import Base


def normalize_database_url(url: str) -> str:
    """Coerce bare Postgres URLs onto the psycopg (v3) driver.

    Managed hosts (Render, Supabase, Heroku) hand out `postgres://` or
    `postgresql://` URLs. SQLAlchemy would otherwise reach for psycopg2; we
    ship psycopg 3, so rewrite the scheme to `postgresql+psycopg://`. SQLite
    and already-qualified URLs pass through untouched.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    url = normalize_database_url(settings.database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables. Use Alembic migrations once a Postgres target is wired."""
    Base.metadata.create_all(get_engine())
