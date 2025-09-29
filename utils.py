"""Utility functions for the chemistry OCR pipeline."""

from __future__ import annotations

import os
from typing import Iterable

from exceptions import ChemistryOCRError


def ensure_api_key() -> str:
    api_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise ChemistryOCRError("API key is not configured")
    return api_key


def process_images_with_env_key(images: Iterable[tuple[bytes, str]]) -> list[bytes]:
    from pipeline import ChemistryPipeline
    
    pipeline = ChemistryPipeline(ensure_api_key())
    results: list[bytes] = []
    for data, mime_type in images:
        results.append(pipeline.process_image_bytes(data, mime_type=mime_type))
    return results
