from ..config import PipelineConfig
from .base import LLMExtractor
from .mock_llm import MockLLMExtractor

__all__ = ["LLMExtractor", "MockLLMExtractor", "build_extractor"]


def build_extractor(config: PipelineConfig) -> LLMExtractor:
    """Return the extractor selected by ``config.extraction_backend``."""
    backend = config.extraction_backend.lower()
    if backend == "mock":
        return MockLLMExtractor()
    if backend == "openai":
        from .openai_llm import OpenAIExtractor

        return OpenAIExtractor(model=config.openai_model)
    raise ValueError(f"Unknown extraction backend: {config.extraction_backend!r}")
