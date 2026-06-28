"""FastAPI surface for the pipeline.

Mirrors the production integration shape: the procurement system POSTs a
requisition (plus a pointer to the uploaded attachment) and receives a structured
flip decision back. Run with::

    uvicorn flip_to_po.api.app:app --reload

Then POST to /flip (see /docs for the interactive schema).
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from ..config import DEFAULT_CONFIG
from ..pipeline import FlipPipeline
from ..schemas import FlipResult, PurchaseRequisition

TRUSTED_DIR = os.getenv("FLIP_TRUSTED_DIR", "data/trusted_sources")

app = FastAPI(
    title="Flip to PO",
    version="1.0.0",
    description="Auto-generate purchase orders from unstructured vendor documents.",
)

_pipeline: FlipPipeline | None = None


def get_pipeline() -> FlipPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = FlipPipeline(trusted_dir=TRUSTED_DIR, config=DEFAULT_CONFIG)
    return _pipeline


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "backend": DEFAULT_CONFIG.extraction_backend}


@app.post("/flip", response_model=FlipResult)
def flip(pr: PurchaseRequisition) -> FlipResult:
    """Process one requisition and return the flip decision + full audit trail."""
    return get_pipeline().run(pr)
