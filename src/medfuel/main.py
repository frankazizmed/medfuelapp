from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from medfuel.api.routes import router
from medfuel.config import Settings, get_settings
from medfuel.db.session import init_db
from medfuel.observability import configure_logging

log = logging.getLogger(__name__)


def _recover_orphaned_jobs(settings: Settings) -> None:
    """Fail jobs left non-terminal by a previous process (crash/redeploy).

    A fresh process can't be running them, so any with a stale heartbeat are
    reclaimed; healthy jobs heartbeating elsewhere stay untouched.
    """
    from medfuel.db.registry import DocumentRegistry
    from medfuel.db.session import get_sessionmaker

    session = get_sessionmaker()()
    try:
        failed = DocumentRegistry(session).fail_stale_jobs(
            timeout_seconds=settings.job_timeout_seconds
        )
        session.commit()
        if failed:
            log.warning(
                "recovered %d orphaned job(s) at startup",
                len(failed),
                extra={"job_ids": failed},
            )
    except Exception:  # noqa: BLE001 - startup recovery must not block boot
        session.rollback()
        log.warning("orphaned-job recovery failed at startup", exc_info=True)
    finally:
        session.close()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()
    _recover_orphaned_jobs(settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="MedFuel Regulatory Intelligence API",
        version="0.1.0",
        description="Phase 1: regulator-first connectors and document registry.",
        lifespan=_lifespan,
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    return app


app = create_app()
