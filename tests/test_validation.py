"""Tests for the business-rule validation and its HARD/SOFT severity policy."""

from __future__ import annotations

from conftest import make_extraction, make_line

from flip_to_po.config import DEFAULT_CONFIG
from flip_to_po.schemas import Severity
from flip_to_po.validation import Validator


def codes(report, severity=None):
    return {
        i.code for i in report.issues if severity is None or i.severity is severity
    }


def test_clean_extraction_has_no_issues(sources):
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction())
    assert report.issues == []
    assert not report.has_hard_failure


def test_unknown_vendor_is_hard(sources):
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction(vendor="V-999"))
    assert "VENDOR_NOT_FOUND" in codes(report, Severity.HARD)
    assert report.has_hard_failure


def test_inactive_vendor_is_hard(sources):
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction(vendor="V-2"))
    assert "VENDOR_INACTIVE" in codes(report, Severity.HARD)


def test_unknown_material_is_hard(sources):
    line = make_line(code="VLV-999999")
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction([line]))
    assert "MATERIAL_NOT_FOUND" in codes(report, Severity.HARD)


def test_arithmetic_mismatch_is_hard(sources):
    line = make_line(qty=10.0, price=125.0, total=9999.0)
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction([line]))
    assert "LINE_TOTAL_MISMATCH" in codes(report, Severity.HARD)


def test_large_price_deviation_is_hard(sources):
    # 200 vs contract 125 = 60% off -> hard block (arithmetic kept consistent).
    line = make_line(price=200.0, total=2000.0)
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction([line]))
    assert "PRICE_DEVIATION_BLOCK" in codes(report, Severity.HARD)


def test_small_price_drift_is_soft(sources):
    # 128 vs 125 = 2.4% -> within hard band (3%) but beyond accept (2%) -> soft.
    line = make_line(price=128.0, total=1280.0)
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction([line]))
    assert "PRICE_OFF_CONTRACT" in codes(report, Severity.SOFT)
    assert not report.has_hard_failure


def test_unit_mismatch_is_soft(sources):
    line = make_line(unit="SET")
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction([line]))
    assert "UNIT_MISMATCH" in codes(report, Severity.SOFT)


def test_high_value_line_is_routed_to_review(sources):
    line = make_line(qty=1000.0, price=125.0, total=125000.0)
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction([line]))
    assert "HIGH_VALUE_REVIEW" in codes(report, Severity.HARD)


def test_non_positive_quantity_is_hard(sources):
    line = make_line(qty=0.0, total=0.0)
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction([line]))
    assert "NON_POSITIVE_QTY" in codes(report, Severity.HARD)


def test_parse_failure_is_hard(sources):
    line = make_line()
    line.unit_price.value = None
    report = Validator(sources, DEFAULT_CONFIG).validate(make_extraction([line]))
    assert "PARSE_FAILURE" in codes(report, Severity.HARD)
