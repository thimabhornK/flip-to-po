"""Evaluation harness for Flip to PO.

Measures two things that matter for a system that can *act* on its own output:

1. Extraction quality — per-field accuracy, line exact-match, requisition
   exact-match, against gold labels.
2. Decision safety — given the gating policy, how often we auto-issue, and, of
   the POs we auto-issue, how often they are exactly correct (``auto_flip
   precision``), plus how reliably we route our own mistakes to a human
   (``review recall``).

The headline number for a reviewer is **auto-flip precision**: the rate at which
an automatically issued PO is fully correct. The whole point of the confidence +
validation gating is to keep that number very high even when raw extraction is
imperfect.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from flip_to_po import FlipPipeline, PurchaseRequisition
from flip_to_po.config import DEFAULT_CONFIG, PipelineConfig
from flip_to_po.schemas import ExtractionResult, FlipDecision

FIELDS = ["material_code", "description", "quantity", "unit", "unit_price", "line_total"]
MONEY_TOL = 0.01


def _norm_str(s) -> str:
    return " ".join(str(s).split()).upper()


def _num_eq(a, b, tol=MONEY_TOL) -> bool:
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


@dataclass
class FieldCounter:
    correct: int = 0
    total: int = 0

    def add(self, ok: bool) -> None:
        self.total += 1
        self.correct += int(ok)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class EvalResults:
    n_prs: int = 0
    n_lines: int = 0
    field_counters: dict[str, FieldCounter] = field(default_factory=dict)
    vendor_counter: FieldCounter = field(default_factory=FieldCounter)
    currency_counter: FieldCounter = field(default_factory=FieldCounter)
    line_exact: FieldCounter = field(default_factory=FieldCounter)
    pr_exact: FieldCounter = field(default_factory=FieldCounter)

    decisions: dict[str, int] = field(default_factory=dict)
    # 2x2 of (extraction correct?) x (auto-flipped?)
    correct_autoflip: int = 0
    correct_review: int = 0
    incorrect_autoflip: int = 0  # the dangerous quadrant
    incorrect_review: int = 0

    latencies_ms: list[float] = field(default_factory=list)

    # -- derived ------------------------------------------------------- #
    @property
    def auto_flip_rate(self) -> float:
        af = self.decisions.get("AUTO_FLIP", 0)
        return af / self.n_prs if self.n_prs else 0.0

    @property
    def auto_flip_precision(self) -> float:
        af = self.correct_autoflip + self.incorrect_autoflip
        return self.correct_autoflip / af if af else 1.0

    @property
    def review_recall(self) -> float:
        errs = self.incorrect_autoflip + self.incorrect_review
        return self.incorrect_review / errs if errs else 1.0

    @property
    def pr_exact_accuracy(self) -> float:
        return self.pr_exact.accuracy

    @property
    def macro_field_accuracy(self) -> float:
        accs = [c.accuracy for c in self.field_counters.values()]
        return sum(accs) / len(accs) if accs else 0.0

    @property
    def p50_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        s = sorted(self.latencies_ms)
        return s[len(s) // 2]

    def to_dict(self) -> dict:
        return {
            "dataset": {"requisitions": self.n_prs, "line_items": self.n_lines},
            "extraction": {
                "field_accuracy": {k: round(v.accuracy, 4) for k, v in self.field_counters.items()},
                "vendor_accuracy": round(self.vendor_counter.accuracy, 4),
                "currency_accuracy": round(self.currency_counter.accuracy, 4),
                "macro_field_accuracy": round(self.macro_field_accuracy, 4),
                "line_exact_match": round(self.line_exact.accuracy, 4),
                "requisition_exact_match": round(self.pr_exact.accuracy, 4),
            },
            "decisions": self.decisions,
            "safety": {
                "auto_flip_rate": round(self.auto_flip_rate, 4),
                "auto_flip_precision": round(self.auto_flip_precision, 4),
                "review_recall": round(self.review_recall, 4),
                "confusion": {
                    "correct_autoflip": self.correct_autoflip,
                    "incorrect_autoflip": self.incorrect_autoflip,
                    "correct_review": self.correct_review,
                    "incorrect_review": self.incorrect_review,
                },
            },
            "latency": {"p50_ms": round(self.p50_latency_ms, 3)},
        }


def _line_correct(extracted, truth) -> tuple[bool, dict[str, bool]]:
    checks = {
        "material_code": _norm_str(extracted.material_code.value) == _norm_str(truth["material_code"]),
        "description": _norm_str(extracted.description.value) == _norm_str(truth["description"]),
        "quantity": _num_eq(extracted.quantity.value, truth["quantity"], tol=1e-6),
        "unit": _norm_str(extracted.unit.value) == _norm_str(truth["unit"]),
        "unit_price": _num_eq(extracted.unit_price.value, truth["unit_price"]),
        "line_total": _num_eq(extracted.line_total.value, truth["line_total"]),
    }
    return all(checks.values()), checks


def _extraction_correct(extraction: ExtractionResult, truth: dict) -> tuple[bool, dict]:
    vendor_ok = _norm_str(extraction.vendor_code.value) == _norm_str(truth["vendor_code"])
    currency_ok = _norm_str(extraction.currency.value) == _norm_str(truth["currency"])
    truth_lines = truth["line_items"]
    per_line = []
    lines_ok = len(extraction.line_items) == len(truth_lines)
    for ext_line, t_line in zip(extraction.line_items, truth_lines):
        ok, checks = _line_correct(ext_line, t_line)
        per_line.append((ok, checks))
        lines_ok = lines_ok and ok
    return (vendor_ok and currency_ok and lines_ok), {
        "vendor_ok": vendor_ok,
        "currency_ok": currency_ok,
        "lines": per_line,
    }


def evaluate(
    dataset_path: str | Path = "data/synthetic/dataset.json",
    trusted_dir: str | Path = "data/trusted_sources",
    config: PipelineConfig = DEFAULT_CONFIG,
) -> EvalResults:
    dataset = json.loads(Path(dataset_path).read_text())
    pipe = FlipPipeline(trusted_dir=trusted_dir, config=config)

    r = EvalResults()
    r.field_counters = {f: FieldCounter() for f in FIELDS}

    for entry in dataset:
        pr = PurchaseRequisition(**entry["pr"])
        truth = entry["truth"]

        t0 = time.perf_counter()
        result = pipe.run(pr)
        r.latencies_ms.append((time.perf_counter() - t0) * 1000)

        r.n_prs += 1
        r.decisions[result.decision.value] = r.decisions.get(result.decision.value, 0) + 1

        pr_ok, detail = _extraction_correct(result.extraction, truth)
        r.vendor_counter.add(detail["vendor_ok"])
        r.currency_counter.add(detail["currency_ok"])
        for ok, checks in detail["lines"]:
            r.n_lines += 1
            r.line_exact.add(ok)
            for f in FIELDS:
                r.field_counters[f].add(checks[f])
        r.pr_exact.add(pr_ok)

        autoflipped = result.decision is FlipDecision.AUTO_FLIP
        if pr_ok and autoflipped:
            r.correct_autoflip += 1
        elif pr_ok and not autoflipped:
            r.correct_review += 1
        elif not pr_ok and autoflipped:
            r.incorrect_autoflip += 1
        else:
            r.incorrect_review += 1

    return r


if __name__ == "__main__":  # pragma: no cover
    from eval.report import print_report

    print_report(evaluate())
