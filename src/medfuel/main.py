from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from medfuel.api.routes import router
from medfuel.db.session import init_db


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
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
