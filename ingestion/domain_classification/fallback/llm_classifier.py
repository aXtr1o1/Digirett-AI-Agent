# """
# domain_classification/fallback/llm_classifier.py
# =================================================
# Stub for future LLM-based classification fallback.
# """

# from __future__ import annotations

# import logging
# from typing import Tuple

# logger = logging.getLogger(__name__)


# class LLMClassifier:
#     """Fallback classifier that will use Azure OpenAI or Claude in the future."""

#     def classify(self, text: str) -> Tuple[str, str]:
#         """
#         Placeholder. Once implemented, this will prompt an LLM
#         to classify the domain of the provided text.
#         """
#         # For now, just log a warning and return unknown
#         logger.warning("LLM Classifier not yet implemented. Returning 'ukjent'.")
#         return "ukjent", ""
