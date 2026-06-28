"""Runtime configuration.

Every tunable that affects a business decision lives here so it can be reviewed,
versioned, and swept in the evaluation harness — never buried in code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineConfig:
    # --- backend selection ------------------------------------------------- #
    # "mock" runs fully offline & deterministic. "openai" calls a real LLM.
    extraction_backend: str = field(
        default_factory=lambda: os.getenv("FLIP_EXTRACTION_BACKEND", "mock")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("FLIP_OPENAI_MODEL", "gpt-4o-mini")
    )

    # --- decision gating --------------------------------------------------- #
    # A PR is auto-flipped only if overall confidence clears this bar AND no
    # HARD validation issue is present. This single number is the dial the
    # business turns to trade automation rate against precision.
    auto_flip_threshold: float = field(
        default_factory=lambda: float(os.getenv("FLIP_AUTO_THRESHOLD", "0.90"))
    )

    # Each SOFT validation issue applies a multiplicative penalty to confidence.
    soft_issue_penalty: float = 0.05

    # --- numeric tolerances ------------------------------------------------ #
    # Relative tolerance when checking line_total == qty * unit_price and when
    # checking an extracted unit price against the contracted price.
    price_rel_tolerance: float = 0.01      # 1%
    contract_price_rel_tolerance: float = 0.02  # 2%: within this, price is accepted
    contract_price_hard_deviation: float = 0.03  # >3% off contract -> hard block

    # --- value-based gate -------------------------------------------------- #
    # A line whose value exceeds this is always routed to a human regardless of
    # confidence — mirrors procurement approval limits and bounds the financial
    # blast radius of any single auto-issued error (e.g. a misread quantity).
    review_above_value: float = 50_000.0

    # --- reproducibility --------------------------------------------------- #
    seed: int = 7


DEFAULT_CONFIG = PipelineConfig()
