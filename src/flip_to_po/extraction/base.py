"""Extraction layer: OCR text + requisition -> structured, confidence-scored fields.

Two interchangeable backends implement ``LLMExtractor``:

* ``MockLLMExtractor`` — deterministic, offline, no API key. Parses the OCR text
  with tolerant heuristics and assigns a calibrated confidence to every field.
  This is what powers the demo, the tests, and the evaluation harness.
* ``OpenAIExtractor`` — a real LLM call with a structured-output prompt. Shown to
  demonstrate prompt design, grounding, and JSON-schema parsing; needs a key.

Keeping a single interface means the pipeline, the API, and the eval harness are
backend-agnostic — you can A/B a new model by swapping one config value.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import ExtractionResult, PurchaseRequisition


class LLMExtractor(ABC):
    name: str = "abstract"

    @abstractmethod
    def extract(self, pr: PurchaseRequisition, ocr_text: str) -> ExtractionResult:
        """Extract structured PO fields, each tagged with a confidence in [0, 1]."""
        raise NotImplementedError
