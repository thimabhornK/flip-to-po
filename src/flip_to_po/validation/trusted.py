"""Trusted reference data ("masters") used to validate model output.

In production these are live ERP tables (vendor master, material master /
contract catalogue). Here they are small JSON files written by the synthetic data
generator. Cross-checking every extracted value against an authoritative source
is the single most important defence against acting on a hallucinated value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VendorRecord:
    name: str
    active: bool


@dataclass(frozen=True)
class MaterialRecord:
    description: str
    unit: str
    contract_price: float


class TrustedSources:
    def __init__(
        self,
        vendors: dict[str, VendorRecord],
        materials: dict[str, MaterialRecord],
    ) -> None:
        self.vendors = vendors
        self.materials = materials

    @classmethod
    def load(cls, directory: str | Path) -> "TrustedSources":
        directory = Path(directory)
        vendors_raw = json.loads((directory / "vendor_master.json").read_text())
        materials_raw = json.loads((directory / "material_master.json").read_text())
        vendors = {
            code: VendorRecord(**rec) for code, rec in vendors_raw.items()
        }
        materials = {
            code: MaterialRecord(**rec) for code, rec in materials_raw.items()
        }
        return cls(vendors=vendors, materials=materials)
