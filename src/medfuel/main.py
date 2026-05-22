from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from medfuel.api.routes import router
from medfuel.db.session import init_db

# Importing the IP ORM module side-effect-registers the IP tables with
# the shared Base metadata so init_db() creates them in one pass.
from medfuel.ip import db_orm as _ip_db_orm  # noqa: F401  (registration only)
from medfuel.ip.api import router as ip_router


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="MedFuel Diligence API",
        version="0.2.0",
        description=(
            "Regulatory + IP intelligence pipeline. Phase 1-3 regulatory and "
            "Phase 4 IP modules share the same registry, citations engine, "
            "and narrative LLM."
        ),
        lifespan=_lifespan,
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(ip_router)
    return app


app = create_app()
