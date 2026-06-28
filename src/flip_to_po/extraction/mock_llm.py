"""Offline, deterministic extractor.

This stands in for an LLM document-extraction call. It parses the (intentionally
noisy) OCR text and assigns each field a confidence that reflects how cleanly the
value could be read:

* clean numeric token           -> high confidence
* OCR look-alike repaired       -> confidence reduced per repair
* illegible / garbled cell      -> low confidence, value kept as read
* unknown unit-of-measure       -> low confidence

The point is to mimic how a real model behaves: it is usually right and
confident, occasionally right-but-unsure, and rarely confidently wrong — which is
exactly the regime the downstream validation + gating layers are designed for.
"""

from __future__ import annotations

import re

from ..schemas import (
    Currency,
    ExtractedLineItem,
    ExtractionResult,
    FieldValue,
    PurchaseRequisition,
)
from .base import LLMExtractor

# Characters OCR commonly confuses with digits.
_CONFUSION = {"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8", "Z": "2"}
_KNOWN_UNITS = {"EA", "SET", "BOX", "KG", "G", "M", "L", "ROLL", "PACK", "DRUM", "CAN", "PCS"}
_ILLEGIBLE_MARK = "###"  # the synthetic OCR emits this where a cell is garbled

# Confidence constants (kept here so they are easy to find and to sweep).
_NUMERIC_BASE = 0.98          # inherent discount: numbers always carry OCR risk
_NUMERIC_REPAIR_PENALTY = 0.10
_CODE_BASE = 0.99
_CODE_REPAIR_PENALTY = 0.07
_DESC_CLEAN = 0.99
_DESC_ILLEGIBLE = 0.50
_UNIT_KNOWN = 0.99
_UNIT_UNKNOWN = 0.55
_PARSE_FAIL = 0.30
_FLOOR = 0.50


def _repair_numeric(token: str) -> tuple[str, int]:
    out, n = [], 0
    for ch in token:
        if ch in _CONFUSION and not ch.isdigit():
            out.append(_CONFUSION[ch])
            n += 1
        else:
            out.append(ch)
    return "".join(out), n


def _parse_number(raw: str) -> FieldValue:
    """Parse a numeric cell, repairing OCR confusions and scoring confidence."""
    stripped = raw.replace(",", "").strip()
    repaired, n_repairs = _repair_numeric(stripped)
    try:
        value = float(repaired)
    except ValueError:
        return FieldValue(value=None, confidence=_PARSE_FAIL)
    conf = max(_FLOOR, _NUMERIC_BASE - _NUMERIC_REPAIR_PENALTY * n_repairs)
    return FieldValue(value=value, confidence=conf)


def _parse_code(raw: str) -> FieldValue:
    m = re.match(r"^([A-Z]{2,5})-(.+)$", raw.strip())
    if not m:
        return FieldValue(value=raw.strip(), confidence=_PARSE_FAIL)
    prefix, suffix = m.group(1), m.group(2)
    repaired, n_repairs = _repair_numeric(suffix)
    conf = max(_FLOOR, _CODE_BASE - _CODE_REPAIR_PENALTY * n_repairs)
    return FieldValue(value=f"{prefix}-{repaired}", confidence=conf)


def _parse_description(raw: str) -> FieldValue:
    raw = raw.strip()
    if _ILLEGIBLE_MARK in raw:
        cleaned = raw.replace(_ILLEGIBLE_MARK, "").strip()
        return FieldValue(value=cleaned, confidence=_DESC_ILLEGIBLE)
    return FieldValue(value=raw, confidence=_DESC_CLEAN)


def _parse_unit(raw: str) -> FieldValue:
    token = raw.strip().upper()
    if token in _KNOWN_UNITS:
        return FieldValue(value=token, confidence=_UNIT_KNOWN)
    return FieldValue(value=token, confidence=_UNIT_UNKNOWN)


class MockLLMExtractor(LLMExtractor):
    name = "mock-llm"

    _ROW_RE = re.compile(r"^\s*\d+\s{2,}")  # a data row starts with "<n>  "

    def extract(self, pr: PurchaseRequisition, ocr_text: str) -> ExtractionResult:
        vendor_fv, currency_fv = self._parse_header(ocr_text, pr)
        line_items = [
            self._parse_row(line)
            for line in ocr_text.splitlines()
            if self._ROW_RE.match(line)
        ]
        return ExtractionResult(
            pr_number=pr.pr_number,
            vendor_code=vendor_fv,
            currency=currency_fv,
            line_items=line_items,
            backend=self.name,
        )

    # ------------------------------------------------------------------ #
    def _parse_header(self, text: str, pr: PurchaseRequisition):
        vendor_match = re.search(r"Vendor:\s*(V-\d+)", text)
        vendor = vendor_match.group(1) if vendor_match else pr.vendor_code
        vendor_fv = FieldValue(value=vendor, confidence=0.99 if vendor_match else 0.6)

        cur_match = re.search(r"Currency:\s*([A-Z]{3})", text)
        currency = cur_match.group(1) if cur_match else pr.currency.value
        try:
            Currency(currency)
            cur_conf = 0.99 if cur_match else 0.7
        except ValueError:
            currency, cur_conf = pr.currency.value, 0.6
        currency_fv = FieldValue(value=currency, confidence=cur_conf)
        return vendor_fv, currency_fv

    def _parse_row(self, line: str) -> ExtractedLineItem:
        tokens = re.split(r"\s{2,}", line.strip())
        if len(tokens) != 7:
            # Unexpected column structure: emit a low-confidence best effort so
            # the gating layer routes this PR to a human.
            low = FieldValue(value=None, confidence=_PARSE_FAIL)
            return ExtractedLineItem(
                material_code=low, description=low, quantity=low,
                unit=low, unit_price=low, line_total=low,
            )
        _, code, desc, qty, unit, price, amount = tokens
        return ExtractedLineItem(
            material_code=_parse_code(code),
            description=_parse_description(desc),
            quantity=_parse_number(qty),
            unit=_parse_unit(unit),
            unit_price=_parse_number(price),
            line_total=_parse_number(amount),
        )
