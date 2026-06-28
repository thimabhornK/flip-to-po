"""Core data models for the Flip to PO pipeline.

These schemas are the contract between every stage of the system:

    OCR  ->  Extraction  ->  Validation  ->  Confidence/Decision

`*Truth` models carry plain, known-correct values (used by the synthetic data
generator and the evaluation harness). `Extracted*` models carry the *predicted*
values together with a per-field confidence, because every value the model
produces must be auditable and gate-able before a PO is auto-issued.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Currency(str, Enum):
    USD = "USD"
    THB = "THB"
    EUR = "EUR"


class FlipDecision(str, Enum):
    """Terminal decision for a purchase requisition."""

    AUTO_FLIP = "AUTO_FLIP"        # confidence + validation high enough to issue a PO automatically
    NEEDS_REVIEW = "NEEDS_REVIEW"  # routed to a human buyer
    REJECTED = "REJECTED"          # hard, unrecoverable failure (e.g. unknown vendor)


class Severity(str, Enum):
    INFO = "INFO"
    SOFT = "SOFT"   # lowers confidence but does not block an auto-flip on its own
    HARD = "HARD"   # blocks auto-flip regardless of confidence


# --------------------------------------------------------------------------- #
# Field-level prediction
# --------------------------------------------------------------------------- #
class FieldValue(BaseModel):
    """A single extracted value with the model's confidence in it."""

    value: Any
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("confidence")
    @classmethod
    def _round(cls, v: float) -> float:
        return round(v, 4)


# --------------------------------------------------------------------------- #
# Ground-truth line item / requisition (synthetic data + eval labels)
# --------------------------------------------------------------------------- #
class LineItemTruth(BaseModel):
    material_code: str
    description: str
    quantity: float
    unit: str
    unit_price: float
    line_total: float


class PurchaseRequisition(BaseModel):
    """The input the buyer prepares in the ERP, plus the vendor attachment.

    In production this comes off the procurement system over REST; here it is
    produced by the synthetic data generator. `buyer_line_hints` mirrors the
    sparse, free-text rows a buyer types into SAP — deliberately incomplete, so
    the system has to recover the authoritative values from the attachment.
    """

    pr_number: str
    requester: str
    cost_center: str
    vendor_code: str
    currency: Currency
    attachment_path: str
    buyer_line_hints: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Extraction output
# --------------------------------------------------------------------------- #
class ExtractedLineItem(BaseModel):
    material_code: FieldValue
    description: FieldValue
    quantity: FieldValue
    unit: FieldValue
    unit_price: FieldValue
    line_total: FieldValue

    def min_confidence(self) -> float:
        return min(
            self.material_code.confidence,
            self.description.confidence,
            self.quantity.confidence,
            self.unit.confidence,
            self.unit_price.confidence,
            self.line_total.confidence,
        )


class ExtractionResult(BaseModel):
    pr_number: str
    vendor_code: FieldValue
    currency: FieldValue
    line_items: list[ExtractedLineItem]
    backend: str  # which extractor produced this (mock-llm, openai, ...)

    def min_confidence(self) -> float:
        confidences = [self.vendor_code.confidence, self.currency.confidence]
        confidences += [li.min_confidence() for li in self.line_items]
        return min(confidences) if confidences else 0.0


# --------------------------------------------------------------------------- #
# Validation output
# --------------------------------------------------------------------------- #
class ValidationIssue(BaseModel):
    code: str
    severity: Severity
    message: str
    line_index: int | None = None  # None == requisition-level issue


class ValidationReport(BaseModel):
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def has_hard_failure(self) -> bool:
        return any(i.severity is Severity.HARD for i in self.issues)

    @property
    def soft_issue_count(self) -> int:
        return sum(1 for i in self.issues if i.severity is Severity.SOFT)


# --------------------------------------------------------------------------- #
# Final decision
# --------------------------------------------------------------------------- #
class FlipResult(BaseModel):
    pr_number: str
    decision: FlipDecision
    overall_confidence: float = Field(ge=0.0, le=1.0)
    extraction: ExtractionResult
    validation: ValidationReport
    rationale: str

    def to_audit_dict(self) -> dict[str, Any]:
        """Compact, log-friendly record (mirrors the production flip-log row)."""
        return {
            "pr_number": self.pr_number,
            "decision": self.decision.value,
            "overall_confidence": self.overall_confidence,
            "backend": self.extraction.backend,
            "hard_failures": [
                i.code for i in self.validation.issues if i.severity is Severity.HARD
            ],
            "soft_issues": [
                i.code for i in self.validation.issues if i.severity is Severity.SOFT
            ],
            "rationale": self.rationale,
        }
