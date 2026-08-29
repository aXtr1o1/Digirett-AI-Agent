"""
utils/document_parser.py — Isolated PDF Text Extraction Utility
"""

import logging
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class DocumentParser:

    @staticmethod
    def extract_text_from_pdf(content: bytes) -> str:
        """Extract text from raw PDF bytes using PyMuPDF (fitz)."""
        if not content:
            return ""

        try:
            doc = fitz.open(stream=content, filetype="pdf")
            extracted_pages = []

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text()
                if text.strip():
                    extracted_pages.append(text)

            doc.close()
            full_text = "\n\n".join(extracted_pages)
            logger.info(f" Extracted {len(full_text)} characters across {len(extracted_pages)} pages")
            return full_text
        except Exception as exc:
            logger.error(f" DocumentParser PDF extraction failed | {exc}", exc_info=True)
            raise ValueError(f"Failed to parse PDF document: {exc}") from exc
