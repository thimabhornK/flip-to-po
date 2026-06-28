"""OCR layer: turn an unstructured attachment into raw text.

In production this is AWS Textract / a Tesseract service that converts a scanned
vendor quotation (PDF/image) into text. Here it is abstracted behind a tiny
interface so the rest of the pipeline never knows or cares which engine ran.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class OCREngine(ABC):
    name: str = "abstract"

    @abstractmethod
    def read(self, attachment_path: str) -> str:
        """Return the recognised text for the document at ``attachment_path``."""
        raise NotImplementedError
