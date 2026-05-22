"""POST /clinical-evidence/{run_id}/pdf — render the section to PDF.

Uses Playwright Chromium against the host frontend's print view. If
Playwright isn't available the endpoint returns 503 with an explanatory
body so the host can degrade gracefully.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from clinical_evidence.api import runner

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{run_id}/pdf")
async def export_pdf(run_id: str, frontend_base: str = "http://localhost:3000") -> Response:
    state = runner.state_of(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    payload = runner.payload_of(run_id)
    if payload is None:
        raise HTTPException(status_code=409, detail="payload not ready")

    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Playwright not installed in this environment. Install with "
                "`pip install playwright && playwright install chromium`."
            ),
        ) from exc

    qs = urlencode({"print": "1"})
    url = f"{frontend_base.rstrip('/')}/clinical-evidence/{run_id}?{qs}"
    pdf_bytes: bytes
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle")
            pdf_bytes = await page.pdf(
                format="A4",
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            await browser.close()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="clinical-evidence-{run_id}.pdf"'
        },
    )
