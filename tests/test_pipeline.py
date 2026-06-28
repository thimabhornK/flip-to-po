"""Tests for decision gating and the end-to-end pipeline."""

from __future__ import annotations

import json

from conftest import make_extraction, make_line

from flip_to_po import FlipPipeline, PurchaseRequisition
from flip_to_po.config import DEFAULT_CONFIG
from flip_to_po.schemas import (
    FlipDecision,
    Severity,
    ValidationIssue,
    ValidationReport,
)
from flip_to_po.validation import Validator, decide


def _report(*issues):
    return ValidationReport(issues=list(issues))


def test_high_confidence_clean_auto_flips():
    res = decide(make_extraction(), _report(), DEFAULT_CONFIG)
    assert res.decision is FlipDecision.AUTO_FLIP


def test_hard_failure_forces_review_even_at_high_confidence():
    issue = ValidationIssue(code="VENDOR_NOT_FOUND", severity=Severity.HARD, message="x")
    res = decide(make_extraction(), _report(issue), DEFAULT_CONFIG)
    assert res.decision is FlipDecision.NEEDS_REVIEW


def test_low_confidence_routes_to_review():
    low = make_extraction([make_line(conf=0.5)])
    res = decide(low, _report(), DEFAULT_CONFIG)
    assert res.decision is FlipDecision.NEEDS_REVIEW


def test_single_soft_issue_still_auto_flips():
    soft = ValidationIssue(code="PRICE_OFF_CONTRACT", severity=Severity.SOFT, message="x")
    res = decide(make_extraction(), _report(soft), DEFAULT_CONFIG)
    # 0.98 * 0.95 = 0.931 >= 0.90
    assert res.decision is FlipDecision.AUTO_FLIP


def test_two_soft_issues_drop_below_threshold():
    s1 = ValidationIssue(code="PRICE_OFF_CONTRACT", severity=Severity.SOFT, message="x")
    s2 = ValidationIssue(code="UNIT_MISMATCH", severity=Severity.SOFT, message="y")
    res = decide(make_extraction(), _report(s1, s2), DEFAULT_CONFIG)
    # 0.98 * 0.95^2 = 0.884 < 0.90
    assert res.decision is FlipDecision.NEEDS_REVIEW


# --------------------------------------------------------------------------- #
# End-to-end pipeline using a tiny on-disk fixture
# --------------------------------------------------------------------------- #
def _write_fixture(tmp_path):
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    (trusted / "vendor_master.json").write_text(
        json.dumps({"V-1": {"name": "Active Co", "active": True}})
    )
    (trusted / "material_master.json").write_text(
        json.dumps({"VLV-100200": {"description": "GATE VALVE 2IN", "unit": "EA", "contract_price": 125.0}})
    )
    attach = tmp_path / "q.txt"
    row = f"1     {'VLV-100200':<14}  {'GATE VALVE 2IN':<30}  {'10':<4}  {'EA':<5}  {'125.00':>10}  {'1,250.00':>10}"
    attach.write_text("QUOTATION\nVendor: V-1\nCurrency: USD\n\n" + row + "\n")
    return trusted, attach


def test_pipeline_auto_flips_clean_requisition(tmp_path):
    trusted, attach = _write_fixture(tmp_path)
    pipe = FlipPipeline(trusted_dir=trusted, config=DEFAULT_CONFIG)
    pr = PurchaseRequisition(
        pr_number="PR-1", requester="t", cost_center="CC-1",
        vendor_code="V-1", currency="USD", attachment_path=str(attach),
    )
    res = pipe.run(pr)
    assert res.decision is FlipDecision.AUTO_FLIP
    assert res.overall_confidence >= 0.9
    assert res.extraction.line_items[0].material_code.value == "VLV-100200"


def test_audit_dict_is_serializable():
    res = decide(make_extraction(), _report(), DEFAULT_CONFIG)
    audit = res.to_audit_dict()
    assert audit["decision"] == "AUTO_FLIP"
    json.dumps(audit)  # must not raise
