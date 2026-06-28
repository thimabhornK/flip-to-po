"""Tests for the offline extractor: parsing, OCR repair, and confidence calibration."""

from __future__ import annotations

from conftest import make_pr

from flip_to_po.extraction.mock_llm import MockLLMExtractor

HEADER = "QUOTATION\nVendor: V-1\nCurrency: USD\n\n"


def _row(code, desc, qty, unit, price, amount):
    return f"1     {code:<14}  {desc:<30}  {qty:<4}  {unit:<5}  {price:>10}  {amount:>10}"


def extract_one(code, desc, qty, unit, price, amount):
    text = HEADER + _row(code, desc, qty, unit, price, amount) + "\n"
    result = MockLLMExtractor().extract(make_pr(), text)
    assert len(result.line_items) == 1
    return result.line_items[0]


def test_clean_row_parses_with_high_confidence():
    li = extract_one("VLV-100200", "GATE VALVE 2IN", "10", "EA", "125.00", "1,250.00")
    assert li.material_code.value == "VLV-100200"
    assert li.quantity.value == 10.0
    assert li.unit.value == "EA"
    assert li.unit_price.value == 125.0
    assert li.line_total.value == 1250.0
    assert li.min_confidence() >= 0.9


def test_ocr_confusion_in_code_is_repaired():
    # "O" in place of "0" should be recovered, with reduced confidence.
    li = extract_one("VLV-10O200", "GATE VALVE 2IN", "10", "EA", "125.00", "1,250.00")
    assert li.material_code.value == "VLV-100200"
    assert 0.5 <= li.material_code.confidence < 0.99


def test_missing_thousands_separator_still_parses():
    li = extract_one("VLV-100200", "GATE VALVE 2IN", "10", "EA", "125.00", "1250.00")
    assert li.line_total.value == 1250.0
    assert li.line_total.confidence >= 0.9


def test_illegible_description_lowers_confidence():
    li = extract_one("VLV-100200", "GATE VALVE ###", "10", "EA", "125.00", "1,250.00")
    assert "###" not in li.description.value
    assert li.description.confidence < 0.6


def test_unknown_unit_lowers_confidence():
    li = extract_one("VLV-100200", "GATE VALVE 2IN", "10", "ZZ", "125.00", "1,250.00")
    assert li.unit.confidence < 0.6


def test_header_vendor_and_currency_parsed():
    text = HEADER + _row("VLV-100200", "GATE VALVE 2IN", "10", "EA", "125.00", "1,250.00") + "\n"
    result = MockLLMExtractor().extract(make_pr(), text)
    assert result.vendor_code.value == "V-1"
    assert result.currency.value == "USD"
