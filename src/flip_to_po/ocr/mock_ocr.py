"""Offline OCR engine.

The synthetic data generator writes each vendor quotation as a ``.txt`` file
whose layout imitates real OCR output (column drift, character confusions such
as O/0 and I/1, missing separators). This engine simply returns that text,
which keeps the whole pipeline deterministic and runnable without cloud calls.

A production engine implementing the same ``OCREngine`` interface would, e.g.::

    import boto3
    class TextractOCR(OCREngine):
        name = "aws-textract"
        def read(self, attachment_path: str) -> str:
            ...  # call textract.detect_document_text and join the blocks
"""

from __future__ import annotations

from pathlib import Path

from .base import OCREngine


class MockOCR(OCREngine):
    name = "mock-ocr"

    def read(self, attachment_path: str) -> str:
        path = Path(attachment_path)
        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {attachment_path}")
        return path.read_text(encoding="utf-8")
