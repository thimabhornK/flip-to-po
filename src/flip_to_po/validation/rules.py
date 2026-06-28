"""Business-rule validation.

Turns an ``ExtractionResult`` into a ``ValidationReport`` by cross-checking every
value against the trusted masters and against internal arithmetic consistency.

Severity policy (the part a reviewer should scrutinise):

* HARD  -> blocks an automatic flip no matter how confident the model was.
          Used for things that are unambiguously wrong or unsafe to act on:
          unknown/inactive vendor, unknown material, non-positive quantity, a
          line whose total does not equal qty x unit_price, or a failed parse.
* SOFT  -> lowers confidence but does not block on its own. Used for plausible
          deviations: a unit that disagrees with the master, or a price that
          drifts from the contracted price beyond tolerance.
"""

from __future__ import annotations

from ..config import PipelineConfig
from ..schemas import (
    ExtractedLineItem,
    ExtractionResult,
    Severity,
    ValidationIssue,
    ValidationReport,
)
from .trusted import TrustedSources


def _rel_close(a: float, b: float, rel_tol: float) -> bool:
    if a is None or b is None:
        return False
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= rel_tol


class Validator:
    def __init__(self, sources: TrustedSources, config: PipelineConfig) -> None:
        self.sources = sources
        self.config = config

    def validate(self, result: ExtractionResult) -> ValidationReport:
        issues: list[ValidationIssue] = []
        issues.extend(self._validate_vendor(result))
        for idx, item in enumerate(result.line_items):
            issues.extend(self._validate_line(idx, item))
        return ValidationReport(issues=issues)

    # ------------------------------------------------------------------ #
    def _validate_vendor(self, result: ExtractionResult) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        vendor = result.vendor_code.value
        record = self.sources.vendors.get(vendor)
        if record is None:
            issues.append(
                ValidationIssue(
                    code="VENDOR_NOT_FOUND",
                    severity=Severity.HARD,
                    message=f"Vendor {vendor!r} is not in the vendor master.",
                )
            )
        elif not record.active:
            issues.append(
                ValidationIssue(
                    code="VENDOR_INACTIVE",
                    severity=Severity.HARD,
                    message=f"Vendor {vendor!r} ({record.name}) is inactive.",
                )
            )
        return issues

    def _validate_line(self, idx: int, item: ExtractedLineItem) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        code = item.material_code.value
        qty = item.quantity.value
        unit = item.unit.value
        unit_price = item.unit_price.value
        line_total = item.line_total.value

        # Parse failures -> always HARD.
        if None in (code, qty, unit, unit_price, line_total):
            issues.append(
                ValidationIssue(
                    code="PARSE_FAILURE",
                    severity=Severity.HARD,
                    message="One or more fields could not be parsed.",
                    line_index=idx,
                )
            )
            return issues

        # Quantity sanity.
        if qty <= 0:
            issues.append(
                ValidationIssue(
                    code="NON_POSITIVE_QTY",
                    severity=Severity.HARD,
                    message=f"Quantity {qty} is not positive.",
                    line_index=idx,
                )
            )

        # Arithmetic integrity: total must equal qty * unit_price.
        expected = qty * unit_price
        if not _rel_close(expected, line_total, self.config.price_rel_tolerance):
            issues.append(
                ValidationIssue(
                    code="LINE_TOTAL_MISMATCH",
                    severity=Severity.HARD,
                    message=(
                        f"Line total {line_total} != qty*unit_price "
                        f"({qty}*{unit_price}={expected:.2f})."
                    ),
                    line_index=idx,
                )
            )

        # Value-based approval gate: high-value lines always go to a human.
        if line_total > self.config.review_above_value:
            issues.append(
                ValidationIssue(
                    code="HIGH_VALUE_REVIEW",
                    severity=Severity.HARD,
                    message=(
                        f"Line value {line_total} exceeds auto-issue limit "
                        f"{self.config.review_above_value:.0f}; routed to a buyer."
                    ),
                    line_index=idx,
                )
            )

        # Material master cross-checks.
        material = self.sources.materials.get(code)
        if material is None:
            issues.append(
                ValidationIssue(
                    code="MATERIAL_NOT_FOUND",
                    severity=Severity.HARD,
                    message=f"Material {code!r} is not in the material master.",
                    line_index=idx,
                )
            )
            return issues

        if unit.upper() != material.unit.upper():
            issues.append(
                ValidationIssue(
                    code="UNIT_MISMATCH",
                    severity=Severity.SOFT,
                    message=f"Unit {unit!r} != master unit {material.unit!r}.",
                    line_index=idx,
                )
            )

        if not _rel_close(
            unit_price, material.contract_price, self.config.contract_price_rel_tolerance
        ):
            deviation = abs(unit_price - material.contract_price) / max(
                abs(material.contract_price), 1e-9
            )
            # Small drift is plausible (price updates) -> SOFT confidence penalty.
            # A large deviation on a *contract* item is almost certainly an error
            # or an off-contract price we must not auto-pay -> HARD block.
            if deviation > self.config.contract_price_hard_deviation:
                issues.append(
                    ValidationIssue(
                        code="PRICE_DEVIATION_BLOCK",
                        severity=Severity.HARD,
                        message=(
                            f"Unit price {unit_price} deviates {deviation:.1%} from "
                            f"contract price {material.contract_price} (>"
                            f"{self.config.contract_price_hard_deviation:.0%}); blocked."
                        ),
                        line_index=idx,
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        code="PRICE_OFF_CONTRACT",
                        severity=Severity.SOFT,
                        message=(
                            f"Unit price {unit_price} drifts {deviation:.1%} from "
                            f"contract price {material.contract_price}."
                        ),
                        line_index=idx,
                    )
                )

        return issues
