"""LLM-backed extractor using the OpenAI API.

This is real, working code; it just needs ``OPENAI_API_KEY`` and the ``openai``
package. It is intentionally kept behind the same ``LLMExtractor`` interface as
the mock so the pipeline, demo, and eval harness are identical regardless of
backend. Select it with ``FLIP_EXTRACTION_BACKEND=openai``.
"""

from __future__ import annotations

import json

from ..schemas import (
    ExtractedLineItem,
    ExtractionResult,
    FieldValue,
    PurchaseRequisition,
)
from .base import LLMExtractor
from .prompts import build_messages


def _to_field(d: dict) -> FieldValue:
    return FieldValue(value=d.get("value"), confidence=float(d.get("confidence", 0.0)))


class OpenAIExtractor(LLMExtractor):
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini", max_retries: int = 2) -> None:
        try:
            from openai import OpenAI  # imported lazily so the package stays optional
        except ImportError as exc:  # pragma: no cover - exercised only without the dep
            raise ImportError(
                "The 'openai' package is required for OpenAIExtractor. "
                "Install it with `pip install openai`, or use the mock backend."
            ) from exc
        self._client = OpenAI()
        self._model = model
        self._max_retries = max_retries

    def extract(self, pr: PurchaseRequisition, ocr_text: str) -> ExtractionResult:
        messages = build_messages(pr, ocr_text)
        raw = self._call_with_retries(messages)
        data = json.loads(raw)

        line_items = [
            ExtractedLineItem(
                material_code=_to_field(li["material_code"]),
                description=_to_field(li["description"]),
                quantity=_to_field(li["quantity"]),
                unit=_to_field(li["unit"]),
                unit_price=_to_field(li["unit_price"]),
                line_total=_to_field(li["line_total"]),
            )
            for li in data["line_items"]
        ]
        return ExtractionResult(
            pr_number=pr.pr_number,
            vendor_code=_to_field(data["vendor_code"]),
            currency=_to_field(data["currency"]),
            line_items=line_items,
            backend=self.name,
        )

    def _call_with_retries(self, messages: list[dict]) -> str:
        last_err: Exception | None = None
        for _ in range(self._max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content or "{}"
            except Exception as exc:  # broad: network/rate-limit/parse, then retry
                last_err = exc
        raise RuntimeError(f"OpenAI extraction failed after retries: {last_err}")
