from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

from ingestion.models.legal_section import LegalBlock, NormalizedLegalSection
from ingestion.adapters.legal_html_parser import parse_legal_blocks

logger = logging.getLogger(__name__)


class LawSectionAdapter:
    @staticmethod
    def adapt(
        paragraph: Dict[str, Any],
        law_metadata: Dict[str, Any],
        order_index: int = 1,
    ) -> NormalizedLegalSection:
        dok_id = str(law_metadata.get("dok_id") or law_metadata.get("canonical_document_id") or "").strip()
        doc_title = str(
            law_metadata.get("title")
            or law_metadata.get("short_title")
            or law_metadata.get("tittel")
            or "Uten tittel"
        ).strip()

        # Paragraph identification
        p_id = str(paragraph.get("paragraf_id") or paragraph.get("id") or f"paragraf-{order_index}").strip()
        p_num = str(
            paragraph.get("paragraf_nr")
            or paragraph.get("paragraf_nummer")
            or paragraph.get("nummer")
            or order_index
        ).strip()

        if not p_num.startswith("§"):
            section_number = f"§ {p_num}"
        else:
            section_number = p_num

        source_section_key = f"{dok_id}/{p_id}"

        # Section & chapter titles
        section_title = (
            paragraph.get("heading")
            or paragraph.get("tittel")
            or paragraph.get("overskrift")
            or None
        )
        if section_title:
            section_title = section_title.strip() or None

        chapter_number = (
            paragraph.get("kapittel_nr")
            or paragraph.get("kapittel_nummer")
            or paragraph.get("chapter_number")
            or None
        )
        if chapter_number:
            chapter_number = str(chapter_number).strip() or None

        chapter_title = (
            paragraph.get("kapittel_tittel")
            or paragraph.get("kapittel_navn")
            or paragraph.get("chapter_title")
            or None
        )
        if chapter_title:
            chapter_title = str(chapter_title).strip() or None

        # Source URL
        raw_p_url = paragraph.get("paragraf_url") or paragraph.get("source_url") or paragraph.get("url")
        if raw_p_url:
            if not str(raw_p_url).startswith("http"):
                source_url = f"https://lovdata.no/dokument/{str(raw_p_url).lstrip('/')}"
            else:
                source_url = str(raw_p_url)
        elif dok_id and section_number:
            clean_sec = section_number.replace(" ", "")
            source_url = f"https://lovdata.no/dokument/{dok_id}/{clean_sec}"
        elif dok_id:
            source_url = f"https://lovdata.no/dokument/{dok_id}"
        else:
            source_url = ""

        # Repeal status
        opphevet_val = paragraph.get("opphevet")
        is_repealed = bool(opphevet_val == 1 or opphevet_val is True or str(opphevet_val).lower() in ("true", "1", "opphevet"))
        is_active = not is_repealed

        # Content extraction: Primary HTML, Fallback Text
        innhold_html = (paragraph.get("innhold_html") or paragraph.get("html") or "").strip()
        innhold_text = (
            paragraph.get("innhold_text")
            or paragraph.get("text")
            or paragraph.get("innhold")
            or paragraph.get("tekst")
            or ""
        ).strip()

        structured_blocks: List[LegalBlock] = []
        raw_html = innhold_html

        if innhold_html:
            parsed_blocks = parse_legal_blocks(innhold_html)
            structured_blocks = [b for b in parsed_blocks if b.text and b.text.strip()]

        html_text = "\n\n".join(b.text.strip() for b in structured_blocks).strip()

        # Check if HTML extraction is significantly incomplete compared to available plain text
        is_incomplete_html = (
            bool(innhold_text)
            and len(innhold_text) > 50
            and len(html_text) < 0.4 * len(innhold_text)
        )

        # Fallback to innhold_text if HTML parsing yielded no valid text or incomplete text
        if (not structured_blocks or not html_text or is_incomplete_html) and innhold_text:
            if is_incomplete_html and html_text:
                logger.warning(
                    "HTML parse for %s yielded incomplete text (%d chars vs %d in innhold_text). Falling back to innhold_text.",
                    source_section_key,
                    len(html_text),
                    len(innhold_text),
                )
            raw_html = ""
            structured_blocks = []
            lines = [l.strip() for l in innhold_text.splitlines() if l.strip()]
            for l_idx, line in enumerate(lines):
                structured_blocks.append(
                    LegalBlock(block_type="TEXT", text=line, prefix=None, order=l_idx)
                )
            source_text = "\n\n".join(b.text for b in structured_blocks if b.text).strip()
        else:
            source_text = html_text

        # Safety net: if source_text is still empty but innhold_html contains text
        if not source_text and innhold_html:
            clean_soup_text = BeautifulSoup(innhold_html, "html.parser").get_text(separator="\n", strip=True)
            if clean_soup_text:
                lines = [l.strip() for l in clean_soup_text.splitlines() if l.strip()]
                structured_blocks = [
                    LegalBlock(block_type="TEXT", text=l, prefix=None, order=idx)
                    for idx, l in enumerate(lines)
                ]
                source_text = "\n\n".join(b.text for b in structured_blocks if b.text).strip()

        candidate_domains = list(law_metadata.get("candidate_domain_ids") or [])
        version_date = str(
            law_metadata.get("sist_endret_dato")
            or law_metadata.get("last_amended_date")
            or law_metadata.get("kunngjort_dato")
            or law_metadata.get("announced_date")
            or law_metadata.get("ikrafttredelse_dato")
            or law_metadata.get("dato")
            or law_metadata.get("version_date")
            or ""
        ).strip()

        return NormalizedLegalSection(
            legal_document_id=dok_id,
            canonical_document_id=dok_id,
            document_type="LAW",
            document_title=doc_title,
            section_type="LAW_PARAGRAPH",
            source_section_key=source_section_key,
            section_number=section_number,
            section_title=section_title,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            raw_html=raw_html,
            source_text=source_text,
            structured_blocks=structured_blocks,
            source_url=source_url,
            candidate_domain_ids=candidate_domains,
            is_active=is_active,
            is_repealed=is_repealed,
            version_date=version_date,
            taxonomy_version="v1",
        )

    @classmethod
    def adapt_all(
        cls,
        paragraphs: List[Dict[str, Any]],
        law_metadata: Dict[str, Any],
    ) -> List[NormalizedLegalSection]:
        """Adapts a list of paragraph records for a given law."""
        return [
            cls.adapt(p, law_metadata, order_index=idx)
            for idx, p in enumerate(paragraphs, start=1)
        ]
