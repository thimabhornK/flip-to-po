#!/usr/bin/env python3
"""Generate a fully synthetic, reproducible dataset for Flip to PO.

Writes:

    data/trusted_sources/vendor_master.json
    data/trusted_sources/material_master.json
    data/synthetic/attachments/<pr>.txt      # noisy "OCR" of a vendor quotation
    data/synthetic/dataset.json               # [{pr, truth}, ...] with gold labels

The OCR text is deliberately degraded with realistic noise (character
confusions, garbled cells, transposed digits, dropped separators) so that the
extractor — and the validation/gating layers around it — have something
non-trivial to be measured against. Ground-truth labels always hold the correct,
pre-corruption values. No proprietary data is used anywhere.

Run:  python scripts/generate_synthetic_data.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRUSTED_DIR = ROOT / "data" / "trusted_sources"
SYNTH_DIR = ROOT / "data" / "synthetic"
ATTACH_DIR = SYNTH_DIR / "attachments"

SEED = 7
N_REQUISITIONS = 160

# --------------------------------------------------------------------------- #
# Catalogue templates (synthetic, petrochemical-procurement flavoured)
# --------------------------------------------------------------------------- #
CATEGORIES = {
    "VLV": ("EA", ["GATE VALVE", "GLOBE VALVE", "BALL VALVE", "CHECK VALVE"],
            ["2IN 150LB CS", "3IN 300LB SS316", "1IN 600LB CS", "4IN 150LB SS304"]),
    "GSK": ("EA", ["SPIRAL WOUND GASKET", "RING JOINT GASKET", "FLAT GASKET"],
            ["2IN 150LB SS316", "3IN 300LB GRAPHITE", "1.5IN 150LB PTFE"]),
    "FIT": ("EA", ["ELBOW 90DEG", "TEE EQUAL", "REDUCER CONC", "FLANGE WN"],
            ["2IN SCH40 CS", "3IN SCH80 SS316", "1IN SCH40 CS"]),
    "PMP": ("EA", ["CENTRIFUGAL PUMP", "GEAR PUMP", "DIAPHRAGM PUMP"],
            ["5HP 50GPM", "10HP 120GPM", "2HP 20GPM"]),
    "INS": ("EA", ["PRESSURE GAUGE", "TEMP TRANSMITTER", "FLOW METER"],
            ["0-10BAR 2.5IN", "PT100 4-20MA", "DN50 ELECTROMAG"]),
    "CHM": ("KG", ["SODIUM HYDROXIDE", "SULFURIC ACID", "ACTIVATED CARBON"],
            ["TECH GRADE 25KG", "98PCT 30KG", "GRANULAR 25KG"]),
    "MRO": ("BOX", ["NITRILE GLOVES", "SAFETY GOGGLES", "CABLE TIE", "DUCT TAPE"],
            ["L 100PCS", "CLEAR ANTIFOG", "300MM BLACK", "48MM SILVER"]),
}

VENDOR_NAMES = [
    "ACME FLOW CONTROL CO LTD", "SIAM VALVE & FITTING", "DELTA PROCESS EQUIP",
    "ASEAN SEALS SUPPLY", "ORIENT PUMP SYSTEMS", "PRECISION INSTRUMENTS CO",
    "GULF CHEMICALS TRADING", "EASTERN MRO SUPPLY", "PACIFIC INDUSTRIAL",
    "MEKONG ENGINEERING", "BANGKOK SEAL TECH", "ANDAMAN PROCESS PARTS",
]

# --------------------------------------------------------------------------- #
# Corruption types applied to the OCR row (truth stays correct)
# --------------------------------------------------------------------------- #
CORRUPTIONS = [
    ("NONE", 0.60),
    ("NO_COMMA", 0.08),
    ("OCR_O_IN_CODE", 0.06),
    ("DESC_TRUNC", 0.06),
    ("UNIT_GARBLE", 0.04),
    ("PRICE_WRONG_ARITH", 0.05),
    ("PRICE_TRANSPOSE", 0.04),
    ("CODE_WRONG", 0.035),
    # quantity has no trusted-source cross-check, so a confident misread of it is
    # the system's genuine blind spot -> a real (small) residual error mode.
    ("QTY_CONFUSED", 0.02),
]

UNIT_GARBLE_MAP = {"EA": "FA", "KG": "K6", "BOX": "B0X", "SET": "SFT", "PCS": "PGS"}


def fmt_money_comma(x: float) -> str:
    return f"{x:,.2f}"


def fmt_money_plain(x: float) -> str:
    return f"{x:.2f}"


def transpose_two_digits(s: str, rng: random.Random) -> str:
    """Swap two digits that are adjacent in the digit sequence (e.g. across a
    decimal point), preferring a swap that actually changes the value."""
    positions = [i for i, c in enumerate(s) if c.isdigit()]
    if len(positions) < 2:
        return s
    candidates = list(range(len(positions) - 1))
    rng.shuffle(candidates)
    chars = list(s)
    for k in candidates:
        i, j = positions[k], positions[k + 1]
        if chars[i] != chars[j]:
            chars[i], chars[j] = chars[j], chars[i]
            return "".join(chars)
    # all adjacent digit pairs identical; fall back to first pair
    i, j = positions[0], positions[1]
    chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def perturb_value(x: float, rng: random.Random, min_rel=0.05, max_rel=0.25) -> float:
    """Return a value differing from x by a controlled relative amount (random
    sign), so the resulting error is reliably large enough to be detectable."""
    rel = rng.uniform(min_rel, max_rel)
    sign = rng.choice([-1, 1])
    return round(x * (1 + sign * rel), 2)


def build_catalogue(rng: random.Random):
    materials: dict[str, dict] = {}
    for prefix, (unit, nouns, specs) in CATEGORIES.items():
        n = rng.randint(7, 10)
        for _ in range(n):
            code = f"{prefix}-{rng.randint(100000, 999999)}"
            if code in materials:
                continue
            noun = rng.choice(nouns)
            spec = rng.choice(specs)
            base = {
                "VLV": 120, "GSK": 35, "FIT": 28, "PMP": 2200,
                "INS": 180, "CHM": 6, "MRO": 22,
            }[prefix]
            price = round(base * rng.uniform(0.7, 1.6), 2)
            materials[code] = {
                "description": f"{noun} {spec}",
                "unit": unit,
                "contract_price": price,
            }

    vendors: dict[str, dict] = {}
    for i, name in enumerate(VENDOR_NAMES, start=1):
        active = not (i in (4, 9))  # two inactive vendors
        vendors[f"V-{i:05d}"] = {"name": name, "active": active}

    return vendors, materials


def make_row_display(code, desc, qty, unit, unit_price, line_total, corruption, rng):
    """Return the six display strings for one OCR row, after corruption."""
    d_code = code
    d_desc = desc
    d_qty = str(int(qty)) if float(qty).is_integer() else str(qty)
    d_unit = unit
    d_price = fmt_money_comma(unit_price)
    d_amount = fmt_money_comma(line_total)

    if corruption == "NO_COMMA":
        d_price = fmt_money_plain(unit_price)
        d_amount = fmt_money_plain(line_total)

    elif corruption == "OCR_O_IN_CODE":
        # Only confuse digits that have an unambiguous OCR look-alike, so the
        # extractor's repair recovers the exact original value.
        forward = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"}
        prefix, suffix = code.split("-")
        idxs = [i for i, ch in enumerate(suffix) if ch in forward]
        if idxs:
            idx = rng.choice(idxs)
            suffix = suffix[:idx] + forward[suffix[idx]] + suffix[idx + 1:]
            d_code = f"{prefix}-{suffix}"
        # else: no mappable digit -> leave the code clean (acts like NONE)

    elif corruption == "CODE_WRONG":
        prefix, suffix = code.split("-")
        idx = rng.randrange(len(suffix))
        new_digit = str((int(suffix[idx]) + rng.randint(1, 8)) % 10)
        suffix = suffix[:idx] + new_digit + suffix[idx + 1:]
        d_code = f"{prefix}-{suffix}"

    elif corruption == "DESC_TRUNC":
        cut = max(6, int(len(desc) * 0.55))
        d_desc = desc[:cut].rstrip() + " ###"  # ### = OCR garble marker

    elif corruption == "UNIT_GARBLE":
        d_unit = UNIT_GARBLE_MAP.get(unit, unit[:-1] + "0" if unit else unit)

    elif corruption == "PRICE_WRONG_ARITH":
        # The line total no longer equals qty * unit_price -> arithmetic HARD fail.
        d_amount = fmt_money_comma(perturb_value(line_total, rng, 0.05, 0.25))

    elif corruption == "PRICE_TRANSPOSE":
        # Internally consistent but materially off the contract price -> caught by
        # the contract-price deviation check (demonstrates that control working).
        wrong_val = perturb_value(unit_price, rng, 0.05, 0.15)
        d_price = fmt_money_plain(wrong_val)
        d_amount = fmt_money_plain(round(wrong_val * qty, 2))

    elif corruption == "QTY_CONFUSED":
        # Misread quantity, with amount recomputed to stay consistent. There is no
        # authoritative quantity to validate against, so this passes every check.
        q_str = str(int(qty))
        wrong_q_str = transpose_two_digits(q_str, rng)
        try:
            wrong_q = int(wrong_q_str)
        except ValueError:
            wrong_q = int(qty) + 1
        if wrong_q == int(qty) or wrong_q < 1:
            wrong_q = int(qty) + 1
        d_qty = str(wrong_q)
        d_amount = fmt_money_comma(round(unit_price * wrong_q, 2))

    return d_code, d_desc, d_qty, d_unit, d_price, d_amount


def render_attachment(pr_number, vendor_code, currency, rows_display) -> str:
    lines = [
        "QUOTATION",
        f"Quotation No: Q-{pr_number[-6:]}",
        f"Vendor: {vendor_code}",
        f"Currency: {currency}",
        "",
        f"{'LINE':<4}  {'CODE':<14}  {'DESCRIPTION':<40}  "
        f"{'QTY':<4}  {'UNIT':<5}  {'UNIT_PRICE':>12}  {'AMOUNT':>12}",
        "-" * 96,
    ]
    for i, (code, desc, qty, unit, price, amount) in enumerate(rows_display, start=1):
        lines.append(
            f"{i:<4}  {code:<14}  {desc:<40}  "
            f"{qty:<4}  {unit:<5}  {price:>12}  {amount:>12}"
        )
    lines += ["-" * 96, "Terms: contract pricing applies.", "END OF QUOTATION"]
    return "\n".join(lines) + "\n"


def main() -> None:
    rng = random.Random(SEED)
    TRUSTED_DIR.mkdir(parents=True, exist_ok=True)
    ATTACH_DIR.mkdir(parents=True, exist_ok=True)

    vendors, materials = build_catalogue(rng)
    (TRUSTED_DIR / "vendor_master.json").write_text(json.dumps(vendors, indent=2))
    (TRUSTED_DIR / "material_master.json").write_text(json.dumps(materials, indent=2))

    material_codes = list(materials.keys())
    active_vendors = [v for v, r in vendors.items() if r["active"]]
    inactive_vendors = [v for v, r in vendors.items() if not r["active"]]
    corruption_names = [c for c, _ in CORRUPTIONS]
    corruption_weights = [w for _, w in CORRUPTIONS]

    dataset = []
    for n in range(N_REQUISITIONS):
        pr_number = f"PR-{100000 + n}"
        # 4% of requisitions deliberately point at an inactive vendor.
        if rng.random() < 0.04 and inactive_vendors:
            vendor_code = rng.choice(inactive_vendors)
        else:
            vendor_code = rng.choice(active_vendors)
        currency = "USD"

        n_lines = rng.randint(1, 3)
        truth_lines = []
        rows_display = []
        buyer_hints = []
        for _ in range(n_lines):
            code = rng.choice(material_codes)
            mat = materials[code]
            qty = rng.choice([1, 2, 5, 10, 20, 25, 50, 100])
            # Most prices match the contract; ~15% carry a small *legitimate*
            # off-contract drift (a real price update the vendor quoted). These
            # are correct values that should still flow through, exercising the
            # SOFT price-drift path without being errors.
            if rng.random() < 0.10:
                factor = rng.choice([rng.uniform(1.018, 1.028), rng.uniform(0.972, 0.982)])
            else:
                factor = rng.uniform(0.995, 1.005)
            unit_price = round(mat["contract_price"] * factor, 2)
            line_total = round(unit_price * qty, 2)
            truth_lines.append(
                {
                    "material_code": code,
                    "description": mat["description"],
                    "quantity": float(qty),
                    "unit": mat["unit"],
                    "unit_price": unit_price,
                    "line_total": line_total,
                }
            )
            corruption = rng.choices(corruption_names, weights=corruption_weights)[0]
            rows_display.append(
                make_row_display(
                    code, mat["description"], qty, mat["unit"],
                    unit_price, line_total, corruption, rng,
                )
            )
            short = " ".join(mat["description"].split()[:2]).lower()
            buyer_hints.append(f"{short} x{qty}")

        attachment_text = render_attachment(pr_number, vendor_code, currency, rows_display)
        attachment_rel = f"data/synthetic/attachments/{pr_number}.txt"
        (ROOT / attachment_rel).write_text(attachment_text, encoding="utf-8")

        pr = {
            "pr_number": pr_number,
            "requester": f"user{rng.randint(1, 40):02d}",
            "cost_center": f"CC-{rng.randint(1000, 1999)}",
            "vendor_code": vendor_code,
            "currency": currency,
            "attachment_path": attachment_rel,
            "buyer_line_hints": buyer_hints,
        }
        truth = {
            "vendor_code": vendor_code,
            "currency": currency,
            "line_items": truth_lines,
        }
        dataset.append({"pr": pr, "truth": truth})

    (SYNTH_DIR / "dataset.json").write_text(json.dumps(dataset, indent=2))
    print(
        f"Wrote {len(vendors)} vendors, {len(materials)} materials, "
        f"{len(dataset)} requisitions ({sum(len(d['truth']['line_items']) for d in dataset)} line items)."
    )


if __name__ == "__main__":
    main()
