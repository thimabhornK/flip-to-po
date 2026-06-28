#!/usr/bin/env python3
"""End-to-end demo: run the pipeline and show the full audit trail for three
representative requisitions — one auto-flipped, one blocked by a hard validation
rule, and one routed to review on low confidence.

Run:  python scripts/demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flip_to_po import FlipPipeline, PurchaseRequisition  # noqa: E402
from flip_to_po.config import DEFAULT_CONFIG  # noqa: E402
from flip_to_po.schemas import FlipDecision, Severity  # noqa: E402

DATASET = ROOT / "data" / "synthetic" / "dataset.json"
TRUSTED = ROOT / "data" / "trusted_sources"


def _pick_examples(pipe, dataset):
    """Choose one auto-flip, one hard-failure review, one low-confidence review."""
    picks: dict[str, tuple] = {}
    for entry in dataset:
        pr = PurchaseRequisition(**entry["pr"])
        res = pipe.run(pr)
        if res.decision is FlipDecision.AUTO_FLIP and "auto" not in picks:
            picks["auto"] = (pr, res)
        elif res.decision is FlipDecision.NEEDS_REVIEW:
            if res.validation.has_hard_failure and "hard" not in picks:
                picks["hard"] = (pr, res)
            elif not res.validation.has_hard_failure and "soft" not in picks:
                picks["soft"] = (pr, res)
        if len(picks) == 3:
            break
    return picks


def main() -> None:
    if not DATASET.exists():
        sys.exit("Dataset not found. Run: python scripts/generate_synthetic_data.py")

    pipe = FlipPipeline(trusted_dir=TRUSTED, config=DEFAULT_CONFIG)
    dataset = json.loads(DATASET.read_text())
    picks = _pick_examples(pipe, dataset)

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
    except ImportError:
        sys.exit("This demo needs `rich`. Install with: pip install rich")

    console = Console()
    console.print(
        Panel.fit(
            "[bold]Flip to PO[/bold] — GenAI purchase-order automation\n"
            f"backend: {DEFAULT_CONFIG.extraction_backend}   "
            f"auto-flip threshold: {DEFAULT_CONFIG.auto_flip_threshold}",
            border_style="cyan",
        )
    )

    labels = {
        "auto": ("AUTO-FLIPPED (PO issued automatically)", "green"),
        "hard": ("ROUTED TO REVIEW (hard validation failure)", "red"),
        "soft": ("ROUTED TO REVIEW (low confidence)", "yellow"),
    }

    for key in ("auto", "hard", "soft"):
        if key not in picks:
            continue
        pr, res = picks[key]
        title, color = labels[key]
        console.rule(f"[bold {color}]{title}[/bold {color}]")
        console.print(
            f"[bold]{pr.pr_number}[/bold]  vendor={res.extraction.vendor_code.value}  "
            f"currency={res.extraction.currency.value}  requester={pr.requester}"
        )

        ocr_text = pipe.ocr.read(pr.attachment_path)
        console.print(Panel(ocr_text.strip(), title="vendor quotation (OCR text)", border_style="dim"))

        t = Table(title="extracted line items (value @ confidence)")
        t.add_column("#", justify="right")
        t.add_column("material")
        t.add_column("description")
        t.add_column("qty", justify="right")
        t.add_column("unit")
        t.add_column("unit price", justify="right")
        t.add_column("line total", justify="right")
        for i, li in enumerate(res.extraction.line_items):
            def cell(fv):
                c = fv.confidence
                style = "green" if c >= 0.9 else "yellow" if c >= 0.6 else "red"
                return f"{fv.value} [{style}]({c:.2f})[/{style}]"
            t.add_row(
                str(i),
                cell(li.material_code), cell(li.description), cell(li.quantity),
                cell(li.unit), cell(li.unit_price), cell(li.line_total),
            )
        console.print(t)

        if res.validation.issues:
            vt = Table(title="validation issues")
            vt.add_column("severity")
            vt.add_column("code")
            vt.add_column("message")
            for issue in res.validation.issues:
                sty = "red" if issue.severity is Severity.HARD else "yellow"
                vt.add_row(f"[{sty}]{issue.severity.value}[/{sty}]", issue.code, issue.message)
            console.print(vt)
        else:
            console.print("[green]no validation issues[/green]")

        console.print(
            Panel.fit(
                f"decision: [bold {color}]{res.decision.value}[/bold {color}]   "
                f"overall confidence: [bold]{res.overall_confidence:.3f}[/bold]\n"
                f"{res.rationale}",
                border_style=color,
            )
        )
        console.print()


if __name__ == "__main__":
    main()
