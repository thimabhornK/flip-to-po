"""Prompt assets for the LLM-backed extractor.

The design goals encoded here are the ones that matter in production document
intelligence: (1) force grounding in the supplied text to suppress hallucination,
(2) demand a strict JSON shape so the output is machine-parseable, and (3) ask the
model to *self-report* a per-field confidence so downstream gating has a signal.
"""

from __future__ import annotations

import json

# JSON Schema the model must conform to. Sent in the prompt and (when the SDK
# supports it) as a response_format for hard validation.
EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor_code": {"$ref": "#/$defs/field"},
        "currency": {"$ref": "#/$defs/field"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "material_code": {"$ref": "#/$defs/field"},
                    "description": {"$ref": "#/$defs/field"},
                    "quantity": {"$ref": "#/$defs/field"},
                    "unit": {"$ref": "#/$defs/field"},
                    "unit_price": {"$ref": "#/$defs/field"},
                    "line_total": {"$ref": "#/$defs/field"},
                },
                "required": [
                    "material_code", "description", "quantity",
                    "unit", "unit_price", "line_total",
                ],
            },
        },
    },
    "required": ["vendor_code", "currency", "line_items"],
    "$defs": {
        "field": {
            "type": "object",
            "properties": {
                "value": {},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["value", "confidence"],
        }
    },
}

SYSTEM_PROMPT = (
    "You are a precise procurement document-extraction engine. You convert the "
    "raw OCR text of a vendor quotation into structured purchase-order line "
    "items. You must extract values ONLY from the supplied OCR text and "
    "requisition metadata. If a value is not present in the text, do not invent "
    "it: report your best reading and lower the confidence accordingly. "
    "OCR text frequently contains character confusions (O/0, I/1, S/5, B/8) and "
    "lost column separators — correct these only when the intended value is "
    "unambiguous, and reflect any uncertainty in the confidence score. "
    "Return ONLY a JSON object matching the provided schema; no prose."
)

USER_PROMPT_TEMPLATE = """\
### Requisition metadata
PR number: {pr_number}
Buyer-entered vendor code: {vendor_code}
Buyer-entered currency: {currency}
Buyer line hints (sparse, may be incomplete):
{buyer_hints}

### Vendor quotation (raw OCR text)
\"\"\"
{ocr_text}
\"\"\"

### Task
Extract: vendor_code, currency, and every line item with material_code,
description, quantity, unit, unit_price, line_total. For each field, return an
object {{"value": ..., "confidence": <0..1>}}. Confidence must reflect how
clearly the value is supported by the OCR text.

### Output JSON schema
{schema}
"""


def build_messages(pr, ocr_text: str) -> list[dict]:
    hints = "\n".join(f"  - {h}" for h in pr.buyer_line_hints) or "  (none)"
    user = USER_PROMPT_TEMPLATE.format(
        pr_number=pr.pr_number,
        vendor_code=pr.vendor_code,
        currency=pr.currency.value,
        buyer_hints=hints,
        ocr_text=ocr_text,
        schema=json.dumps(EXTRACTION_JSON_SCHEMA, indent=2),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
