"""Sweep the auto-flip confidence threshold to show the core trade-off.

Raising the threshold issues fewer POs automatically but makes the auto-issued
set safer (higher precision). This is the single most important operating dial,
so we plot it explicitly. Run:  python -m eval.sweep
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from flip_to_po.config import DEFAULT_CONFIG

from eval.harness import evaluate

THRESHOLDS = [0.80, 0.85, 0.90, 0.93, 0.95, 0.98]
SWEEP_JSON = Path("eval/sweep.json")


def run_sweep(thresholds=THRESHOLDS) -> list[dict]:
    rows = []
    for t in thresholds:
        cfg = dataclasses.replace(DEFAULT_CONFIG, auto_flip_threshold=t)
        r = evaluate(config=cfg)
        rows.append(
            {
                "threshold": t,
                "auto_flip_rate": round(r.auto_flip_rate, 4),
                "auto_flip_precision": round(r.auto_flip_precision, 4),
                "review_recall": round(r.review_recall, 4),
                "incorrect_autoflip": r.incorrect_autoflip,
            }
        )
    return rows


def print_sweep(rows: list[dict]) -> None:
    SWEEP_JSON.parent.mkdir(parents=True, exist_ok=True)
    SWEEP_JSON.write_text(json.dumps(rows, indent=2))
    try:
        from rich.console import Console
        from rich.table import Table

        t = Table(title="Auto-flip threshold sweep", title_style="bold")
        t.add_column("threshold", justify="right")
        t.add_column("auto-flip rate", justify="right")
        t.add_column("auto-flip precision", justify="right")
        t.add_column("review recall", justify="right")
        t.add_column("incorrect auto-flips", justify="right")
        for r in rows:
            t.add_row(
                f"{r['threshold']:.2f}",
                f"{r['auto_flip_rate']*100:.1f}%",
                f"{r['auto_flip_precision']*100:.1f}%",
                f"{r['review_recall']*100:.1f}%",
                str(r["incorrect_autoflip"]),
            )
        Console().print(t)
    except ImportError:
        print(f"{'thr':>5} {'auto%':>7} {'prec%':>7} {'recall%':>8} {'bad':>4}")
        for r in rows:
            print(
                f"{r['threshold']:>5.2f} {r['auto_flip_rate']*100:>7.1f} "
                f"{r['auto_flip_precision']*100:>7.1f} {r['review_recall']*100:>8.1f} "
                f"{r['incorrect_autoflip']:>4}"
            )
    print(f"sweep written to {SWEEP_JSON}")


if __name__ == "__main__":  # pragma: no cover
    print_sweep(run_sweep())
