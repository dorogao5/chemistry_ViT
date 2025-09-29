"""Utility pipeline for converting chemistry images into Word documents for the web app.

This module provides backward compatibility by re-exporting all classes and functions
from the refactored modules.
"""

# Import all classes and functions from the refactored modules
from exceptions import ChemistryOCRError
from markdown_converter import MarkdownToWordConverter
from ocr import ChemistryOCR
from pipeline import ChemistryPipeline
from utils import ensure_api_key, process_images_with_env_key
from vision_extractor import SYSTEM_PROMPT_CHEMISTRY_VIT, VisionChemistryExtractor

# Re-export all public APIs for backward compatibility
__all__ = [
    "ChemistryOCRError",
    "ChemistryOCR",
    "MarkdownToWordConverter",
    "VisionChemistryExtractor", 
    "ChemistryPipeline",
    "SYSTEM_PROMPT_CHEMISTRY_VIT",
    "ensure_api_key",
    "process_images_with_env_key",
]
