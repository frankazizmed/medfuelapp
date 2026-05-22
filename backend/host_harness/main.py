"""Minimal host harness — mounts the Clinical Evidence island in one line.

This file is NOT part of the island. It exists only so the island can be
exercised end-to-end. The real MedFuel host app will mount the island
the same way.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import clinical_evidence

app = FastAPI(title="MedFuel Host Harness", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# One line to integrate the entire island.
app.include_router(clinical_evidence.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "host": "MedFuel harness",
        "islands": "clinical-evidence",
        "docs": "/docs",
    }
