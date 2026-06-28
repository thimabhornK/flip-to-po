"""Flip to PO — GenAI purchase-order automation (clean-room, synthetic-data demo).

Public API:

    from flip_to_po import FlipPipeline, PurchaseRequisition
    from flip_to_po.config import PipelineConfig
"""

from .config import DEFAULT_CONFIG, PipelineConfig
from .pipeline import FlipPipeline
from .schemas import (
    Currency,
    FlipDecision,
    FlipResult,
    PurchaseRequisition,
)

__version__ = "1.0.0"
__all__ = [
    "FlipPipeline",
    "PipelineConfig",
    "DEFAULT_CONFIG",
    "PurchaseRequisition",
    "FlipResult",
    "FlipDecision",
    "Currency",
]
