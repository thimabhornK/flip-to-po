"""End-to-end orchestration: OCR -> extraction -> validation -> decision.

``FlipPipeline`` is the single object the demo, the API, and the eval harness all
use. Constructed once (loading the trusted sources and the configured backend) it
processes any number of requisitions.
"""

from __future__ import annotations

from pathlib import Path

from .config import DEFAULT_CONFIG, PipelineConfig
from .extraction import build_extractor
from .ocr import MockOCR, OCREngine
from .schemas import FlipResult, PurchaseRequisition
from .validation import TrustedSources, Validator, decide


class FlipPipeline:
    def __init__(
        self,
        trusted_dir: str | Path,
        config: PipelineConfig = DEFAULT_CONFIG,
        ocr: OCREngine | None = None,
    ) -> None:
        self.config = config
        self.ocr = ocr or MockOCR()
        self.extractor = build_extractor(config)
        self.validator = Validator(TrustedSources.load(trusted_dir), config)

    def run(self, pr: PurchaseRequisition) -> FlipResult:
        ocr_text = self.ocr.read(pr.attachment_path)
        extraction = self.extractor.extract(pr, ocr_text)
        validation = self.validator.validate(extraction)
        return decide(extraction, validation, self.config)
