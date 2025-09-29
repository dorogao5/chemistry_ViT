"""OCR functionality using Mistral for chemistry images."""

from __future__ import annotations

import base64
import json
import re

from mistralai import ImageURLChunk, Mistral

from exceptions import ChemistryOCRError


class ChemistryOCR:
    """Wraps Mistral OCR for chemistry images."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key is required for OCR")
        self.client = Mistral(api_key=api_key)

    def process_image_bytes(self, data: bytes, mime_type: str = "image/png", output_format: str = "markdown") -> str:
        if not data:
            raise ChemistryOCRError("Empty image payload")

        base64_data_url = f"data:{mime_type};base64,{base64.b64encode(data).decode()}"

        try:
            ocr_response = self.client.ocr.process(
                document=ImageURLChunk(image_url=base64_data_url),
                model="mistral-ocr-latest",
            )
        except Exception as exc:  # noqa: BLE001
            raise ChemistryOCRError(f"Mistral OCR request failed: {exc}") from exc

        if not ocr_response.pages:
            raise ChemistryOCRError("OCR response contains no pages")

        markdown_content = ocr_response.pages[0].markdown

        if output_format.lower() == "markdown":
            return markdown_content
        if output_format.lower() == "json":
            response_dict = json.loads(ocr_response.model_dump_json())
            return json.dumps(response_dict, indent=2, ensure_ascii=False)
        if output_format.lower() == "text":
            text_only = re.sub(r"\*\*|__|~~|\*|_", "", markdown_content)
            text_only = re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", text_only)
            text_only = re.sub(r"#+\s*", "", text_only)
            return text_only
        return markdown_content
