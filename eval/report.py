"""Render evaluation results: a readable console report + a JSON artifact.

Console output uses ``rich`` when available and degrades to plain text otherwise,
so the harness runs in any environment (CI included).
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.harness import EvalResults

RESULTS_JSON = Path("eval/results.json")


def _plain_report(d: dict) -> str:
    lines = []
    ds = d["dataset"]
    lines.append(f"Dataset: {ds['requisitions']} requisitions, {ds['line_items']} line items")
    lines.append("")
    lines.append("Field accuracy:")
    for k, v in d["extraction"]["field_accuracy"].items():
        lines.append(f"  {k:<14} {v*100:6.2f}%")
    ex = d["extraction"]
    lines.append(f"  {'vendor':<14} {ex['vendor_accuracy']*100:6.2f}%")
    lines.append(f"  {'currency':<14} {ex['currency_accuracy']*100:6.2f}%")
    lines.append("")
    lines.append(f"Macro field accuracy:      {ex['macro_field_accuracy']*100:6.2f}%")
    lines.append(f"Line exact-match:          {ex['line_exact_match']*100:6.2f}%")
    lines.append(f"Requisition exact-match:   {ex['requisition_exact_match']*100:6.2f}%")
    lines.append("")
    lines.append(f"Decisions: {d['decisions']}")
    s = d["safety"]
    lines.append("")
    lines.append("Safety / automation:")
    lines.append(f"  auto-flip rate:       {s['auto_flip_rate']*100:6.2f}%")
    lines.append(f"  auto-flip precision:  {s['auto_flip_precision']*100:6.2f}%   (correct | auto-issued)")
    lines.append(f"  review recall:        {s['review_recall']*100:6.2f}%   (errors routed to human)")
    c = s["confusion"]
    lines.append("")
    lines.append("Confusion (extraction correct? x auto-flipped?):")
    lines.append(f"            auto-flip   review")
    lines.append(f"  correct      {c['correct_autoflip']:>5}   {c['correct_review']:>6}")
    lines.append(f"  incorrect    {c['incorrect_autoflip']:>5}   {c['incorrect_review']:>6}   <- incorrect_autoflip is the risk cell")
    lines.append("")
    lines.append(f"p50 latency: {d['latency']['p50_ms']:.3f} ms / requisition")
    return "\n".join(lines)


def print_report(results: EvalResults) -> dict:
    d = results.to_dict()
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(d, indent=2))

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()

        ext = d["extraction"]
        t = Table(title="Extraction accuracy", title_style="bold")
        t.add_column("Field")
        t.add_column("Accuracy", justify="right")
        for k, v in ext["field_accuracy"].items():
            t.add_row(k, f"{v*100:.2f}%")
        t.add_row("vendor", f"{ext['vendor_accuracy']*100:.2f}%")
        t.add_row("currency", f"{ext['currency_accuracy']*100:.2f}%")
        t.add_section()
        t.add_row("[bold]macro field[/bold]", f"[bold]{ext['macro_field_accuracy']*100:.2f}%[/bold]")
        t.add_row("line exact-match", f"{ext['line_exact_match']*100:.2f}%")
        t.add_row("requisition exact-match", f"{ext['requisition_exact_match']*100:.2f}%")
        console.print(t)

        s = d["safety"]
        st = Table(title="Safety / automation", title_style="bold")
        st.add_column("Metric")
        st.add_column("Value", justify="right")
        st.add_row("auto-flip rate", f"{s['auto_flip_rate']*100:.2f}%")
        st.add_row("[bold]auto-flip precision[/bold]", f"[bold green]{s['auto_flip_precision']*100:.2f}%[/bold green]")
        st.add_row("review recall (of errors)", f"{s['review_recall']*100:.2f}%")
        console.print(st)

        c = s["confusion"]
        ct = Table(title="Extraction-correct  x  auto-flipped", title_style="bold")
        ct.add_column("")
        ct.add_column("auto-flip", justify="right")
        ct.add_column("review", justify="right")
        ct.add_row("correct", str(c["correct_autoflip"]), str(c["correct_review"]))
        ct.add_row("incorrect", f"[red]{c['incorrect_autoflip']}[/red]", str(c["incorrect_review"]))
        console.print(ct)
        console.print(
            Panel.fit(
                f"decisions: {d['decisions']}\n"
                f"p50 latency: {d['latency']['p50_ms']:.3f} ms / requisition\n"
                f"results written to {RESULTS_JSON}",
                title="run summary",
            )
        )
    except ImportError:
        print(_plain_report(d))
        print(f"\nresults written to {RESULTS_JSON}")

    return d
