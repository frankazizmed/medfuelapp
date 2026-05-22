from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from medfuel.config import get_settings
from medfuel.db.orm import Base

# Ensure tests never touch a developer's real .env by forcing a known config.
os.environ.setdefault("MEDFUEL_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("MEDFUEL_CONTACT_EMAIL", "tests@example.com")
os.environ.setdefault("MEDFUEL_USER_AGENT", "MedFuel-Tests/0.1 (tests@example.com)")
get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture()
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
