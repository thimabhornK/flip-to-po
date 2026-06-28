"""Shared test fixtures and helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flip_to_po.schemas import (  # noqa: E402
    Currency,
    ExtractedLineItem,
    ExtractionResult,
    FieldValue,
    PurchaseRequisition,
)
from flip_to_po.validation import (  # noqa: E402
    MaterialRecord,
    TrustedSources,
    VendorRecord,
)


def make_pr(**overrides) -> PurchaseRequisition:
    base = dict(
        pr_number="PR-TEST",
        requester="tester",
        cost_center="CC-0001",
        vendor_code="V-1",
        currency=Currency.USD,
        attachment_path="unused.txt",
        buyer_line_hints=[],
    )
    base.update(overrides)
    return PurchaseRequisition(**base)


def fv(value, conf=0.99) -> FieldValue:
    return FieldValue(value=value, confidence=conf)


def make_line(
    code="VLV-100200", desc="GATE VALVE 2IN", qty=10.0,
    unit="EA", price=125.0, total=1250.0, conf=0.99,
) -> ExtractedLineItem:
    return ExtractedLineItem(
        material_code=fv(code, conf),
        description=fv(desc, conf),
        quantity=fv(qty, conf),
        unit=fv(unit, conf),
        unit_price=fv(price, conf),
        line_total=fv(total, conf),
    )


def make_extraction(lines=None, vendor="V-1", currency="USD") -> ExtractionResult:
    return ExtractionResult(
        pr_number="PR-TEST",
        vendor_code=fv(vendor),
        currency=fv(currency),
        line_items=lines if lines is not None else [make_line()],
        backend="mock-llm",
    )


@pytest.fixture
def sources() -> TrustedSources:
    vendors = {
        "V-1": VendorRecord(name="Active Co", active=True),
        "V-2": VendorRecord(name="Dead Co", active=False),
    }
    materials = {
        "VLV-100200": MaterialRecord(description="GATE VALVE 2IN", unit="EA", contract_price=125.0),
    }
    return TrustedSources(vendors=vendors, materials=materials)
