from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from bs4 import BeautifulSoup, NavigableString, Tag

from ingestion.models.legal_section import LegalBlock, NormalizedLegalSection
from ingestion.adapters.legal_html_parser import parse_legal_blocks
from ingestion.src.chunking.legal_chunker import LegalSectionChunker
from ingestion.adapters.url_cleaner import clean_lovdata_url

logger = logging.getLogger(__name__)


def section_splitter(text: str, max_tokens: int = 1500) -> List[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks: List[str] = []
    curr_parts: List[str] = []
    curr_len = 0
    # Approximate ~4 characters per token
    char_limit = max_tokens * 4

    for p in paragraphs:
        p_len = len(p)
        if curr_parts and (curr_len + p_len > char_limit):
            chunks.append("\n\n".join(curr_parts))
            curr_parts = [p]
            curr_len = p_len
        else:
            curr_parts.append(p)
            curr_len += p_len

    if curr_parts:
        chunks.append("\n\n".join(curr_parts))

    return chunks if chunks else [text]


class RegulationSectionAdapter:
    @classmethod
    def adapt_all(
        cls,
        regulation_dict: Dict[str, Any],
    ) -> List[NormalizedLegalSection]:
        canon_id = str(
            regulation_dict.get("canonical_id")
            or regulation_dict.get("canonical_document_id")
            or regulation_dict.get("sf_dok_id")
            or regulation_dict.get("dok_id")
            or ""
        ).strip()

        doc_title = str(
            regulation_dict.get("title")
            or regulation_dict.get("short_title")
            or regulation_dict.get("tittel")
            or "Uten tittel"
        ).strip()

        fulltext_html = regulation_dict.get("fulltekst") or regulation_dict.get("content") or regulation_dict.get("innhold_html")

        if not isinstance(fulltext_html, str) or not fulltext_html.strip():
            logger.debug("Regulation %s has no usable fulltekst string.", canon_id)
            return []

        soup = BeautifulSoup(fulltext_html, "html.parser")
        for clutter in soup(["script", "style", "nav", "header", "footer"]):
            clutter.decompose()
        articles = soup.find_all("article", class_="legalArticle")
        if articles:
            return cls._adapt_structured_articles(regulation_dict, canon_id, doc_title, articles)
        headers: List[Tag] = []
        for el in soup.find_all(re.compile(r'^(h[1-6]|b|strong|article)$')):
            t = el.get_text(strip=True)
            if re.search(r'§\s*\d+[\w\-]*', t) or re.search(r'paragraf\s*\d+', t, re.IGNORECASE):
                if el not in headers and not any(el in h.descendants for h in headers):
                    headers.append(el)

        if not headers:
            for el in soup.find_all(["p", "div"]):
                t = el.get_text(strip=True)
                if t.startswith("§") or t.lower().startswith("paragraf"):
                    if el not in headers:
                        headers.append(el)
        if headers and len(headers) >= 2:
            return cls._adapt_discovered_headers(regulation_dict, soup, canon_id, doc_title, headers)
        logger.info("Regulation %s has < 2 section headers. Routing to _extract_unstructured_sections()", canon_id)
        return cls._extract_unstructured_sections(regulation_dict, soup, canon_id, doc_title)

    @classmethod
    def _adapt_structured_articles(
        cls,
        regulation_dict: Dict[str, Any],
        canon_id: str,
        doc_title: str,
        articles: List[Tag],
    ) -> List[NormalizedLegalSection]:
        sections: List[NormalizedLegalSection] = []
        seen_section_keys: Set[str] = set()

        for idx, article in enumerate(articles, start=1):
            lovdata_url = article.get("data-lovdata-url") or article.get("data-lovdata-URL")
            data_name = article.get("data-name")
            art_id = article.get("id")

            if lovdata_url and str(lovdata_url).strip():
                source_section_key = str(lovdata_url).strip()
            elif data_name and str(data_name).strip():
                clean_name = re.sub(r"\s+", "", str(data_name).strip())
                source_section_key = f"{canon_id}/{clean_name}"
            elif art_id and str(art_id).strip():
                source_section_key = f"{canon_id}/{str(art_id).strip()}"
            else:
                source_section_key = f"{canon_id}/§{idx}"

            if source_section_key in seen_section_keys:
                continue
            seen_section_keys.add(source_section_key)

            heading_elem = article.find(["h1", "h2", "h3", "h4", "header", "span"], class_=["heading", "title", "caption"])
            section_title = heading_elem.get_text(separator=" ", strip=True) if heading_elem else None
            
            section_number = data_name or f"§ {idx}"
            if not str(section_number).startswith("§"):
                section_number = f"§ {section_number}"

            chapter_elem = article.find_parent("section", class_="kapittel") or article.find_previous("section", class_="kapittel")
            chapter_number = None
            chapter_title = None
            if chapter_elem:
                c_heading = chapter_elem.find(["h1", "h2", "h3", "header"])
                if c_heading:
                    chapter_title = c_heading.get_text(strip=True)

            article_text = article.get_text()
            is_repealed = bool(
                "(opphevet)" in article_text.lower()
                or "(oppheva)" in article_text.lower()
                or "opphevet ved" in article_text.lower()
            )
            is_active = not is_repealed

            raw_html = str(article)
            structured_blocks = parse_legal_blocks(raw_html)
            source_text = "\n\n".join(b.text for b in structured_blocks if b.text).strip()

            candidate_domains = list(regulation_dict.get("candidate_domain_ids") or [])
            clean_sec = section_number.replace(" ", "") if section_number else ""
            source_url = cls._get_source_url(regulation_dict, canon_id, clean_sec)
            version_date = cls._get_version_date(regulation_dict)

            section_obj = NormalizedLegalSection(
                legal_document_id=canon_id,
                canonical_document_id=canon_id,
                document_type="REGULATION",
                document_title=doc_title,
                section_type="REGULATION_PROVISION",
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
            sections.append(section_obj)

        logger.info("Regulation %s parsed %d provisions from structured legalArticle HTML.", canon_id, len(sections))
        return sections

    @classmethod
    def _adapt_discovered_headers(
        cls,
        regulation_dict: Dict[str, Any],
        soup: BeautifulSoup,
        canon_id: str,
        doc_title: str,
        headers: List[Tag],
    ) -> List[NormalizedLegalSection]:
        provisions: List[NormalizedLegalSection] = []
        candidate_domains = list(regulation_dict.get("candidate_domain_ids") or [])
        version_date = cls._get_version_date(regulation_dict)

        for idx, h in enumerate(headers, 1):
            header_text = h.get_text(strip=True)
            m = re.search(r'§\s*([\d\w\-]+)', header_text) or re.search(r'paragraf\s*([\d\w\-]+)', header_text, re.IGNORECASE)
            p_nr = f"§ {m.group(1)}" if m else f"§ {idx}"
            clean_sec = p_nr.replace(" ", "")

            container = h.parent if h.name in ("b", "strong") and h.parent and h.parent.name in ("p", "div", "article") else h
            content_parts: List[str] = []

            if h.name in ("b", "strong"):
                p_text = container.get_text(separator=" ", strip=True)
                if p_text.startswith(header_text):
                    body_after = p_text[len(header_text):].strip()
                    if body_after:
                        content_parts.append(body_after)

            curr = container.next_sibling
            next_header = headers[idx] if idx < len(headers) else None
            next_container = next_header.parent if next_header and next_header.name in ("b", "strong") and next_header.parent and next_header.parent.name in ("p", "div", "article") else next_header

            while curr:
                if curr == next_container or curr == next_header:
                    break
                if isinstance(curr, Tag):
                    if curr in headers or any(hdr in curr.descendants for hdr in headers):
                        break
                    t = curr.get_text(separator=" ", strip=True)
                    if t and t not in content_parts:
                        content_parts.append(t)
                elif isinstance(curr, NavigableString):
                    t = str(curr).strip()
                    if t and len(t) > 2 and t not in content_parts:
                        content_parts.append(t)
                curr = curr.next_sibling

            blocks: List[LegalBlock] = [
                LegalBlock(block_type="LEDD", text=line, order=i)
                for i, line in enumerate(content_parts, 1) if line.strip()
            ]
            if not blocks:
                blocks = [LegalBlock(block_type="LEDD", text=header_text, order=1)]

            source_text = "\n\n".join(b.text for b in blocks if b.text).strip()
            source_sec_key = f"{canon_id}/{clean_sec}"
            source_url = cls._get_source_url(regulation_dict, canon_id, clean_sec)

            section_obj = NormalizedLegalSection(
                legal_document_id=canon_id,
                canonical_document_id=canon_id,
                document_type="REGULATION",
                document_title=doc_title,
                section_type="REGULATION_PROVISION",
                source_section_key=source_sec_key,
                section_number=p_nr,
                section_title=header_text,
                chapter_number=None,
                chapter_title=None,
                raw_html=f"<h3>{header_text}</h3><p>{source_text}</p>",
                source_text=source_text,
                structured_blocks=blocks,
                source_url=source_url,
                candidate_domain_ids=candidate_domains,
                is_active=True,
                is_repealed=False,
                version_date=version_date,
                taxonomy_version="v1",
            )
            provisions.append(section_obj)

        logger.info("Stage 2A Header Discovery: Extracted %d provisions for %s", len(provisions), canon_id)
        return provisions
    @classmethod
    def _extract_unstructured_sections(
        cls,
        regulation_dict: Dict[str, Any],
        soup: BeautifulSoup,
        canon_id: str,
        doc_title: str,
    ) -> List[NormalizedLegalSection]:
        """
        Classifies unstructured HTML into one of 4 types and extracts NormalizedLegalSection provisions.
        """
        raw_text = soup.get_text(separator="\n\n").strip()
        if not raw_text:
            logger.debug("Regulation %s has empty text after HTML cleaning.", canon_id)
            return []

        # 1. Check Type 1: Exactly 2 Sections with § symbols
        sec_header_tags = soup.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "b", "strong"],
            string=re.compile(r"§\s*\d+", re.IGNORECASE)
        )
        if len(sec_header_tags) == 2:
            return cls._adapt_discovered_headers(regulation_dict, soup, canon_id, doc_title, sec_header_tags)

        # 2. Check Type 2: Roman Numeral Headers (I., II., III., etc.)
        roman_header_tags = soup.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "b", "strong"],
            string=re.compile(r"^(?:Kapittel\s+)?([IVXLCDM]+)\.?(?:\s|$)", re.IGNORECASE)
        )
        if len(roman_header_tags) >= 2:
            return cls._handle_type_2_roman_numerals(regulation_dict, soup, roman_header_tags, canon_id, doc_title)

        # 3. Check Type 4: Complex HTML / Tables / Multi-tier Bullet Lists / Long Text
        has_tables = bool(soup.find("table"))
        has_lists = len(soup.find_all(["ul", "ol"])) >= 2

        # OVERSIZED TOKEN SAFEGUARD:
        # If raw_text > 20,000 chars (~5,000 tokens), sub-chunk via section_splitter
        # to guarantee Azure OpenAI 8,192 token limit is NEVER exceeded.
        if len(raw_text) > 20000:
            return cls._handle_oversized_unstructured(regulation_dict, raw_text, canon_id, doc_title)

        if has_tables or has_lists or len(raw_text) > 3000:
            return [cls._handle_type_4_complex_unstructured(regulation_dict, soup, raw_text, canon_id, doc_title)]

        # 4. Default Type 3: Single Paragraph / Short Decrees
        return [cls._handle_type_3_single_paragraph(regulation_dict, soup, raw_text, canon_id, doc_title)]

    @classmethod
    def _handle_type_2_roman_numerals(
        cls,
        regulation_dict: Dict[str, Any],
        soup: BeautifulSoup,
        header_tags: List[Tag],
        canon_id: str,
        doc_title: str,
    ) -> List[NormalizedLegalSection]:
        sections: List[NormalizedLegalSection] = []
        candidate_domains = list(regulation_dict.get("candidate_domain_ids") or [])
        version_date = cls._get_version_date(regulation_dict)

        for idx, htag in enumerate(header_tags, start=1):
            h_text = htag.get_text(strip=True)
            match = re.search(r"^(?:Kapittel\s+)?([IVXLCDM]+)", h_text, re.IGNORECASE)
            roman_str = match.group(1).upper() if match else f"SEC-{idx}"

            parent = htag.parent if htag.parent and htag.parent.name in ["p", "div", "article"] else htag
            text_lines: List[str] = []

            p_text = parent.get_text(separator=" ", strip=True)
            if p_text:
                text_lines.append(p_text)

            curr = parent.next_sibling
            next_header_parent = header_tags[idx].parent if idx < len(header_tags) else None
            while curr and curr != next_header_parent and (idx == len(header_tags) or curr not in header_tags):
                if isinstance(curr, Tag):
                    t = curr.get_text(separator=" ", strip=True)
                    if t and t not in text_lines:
                        text_lines.append(t)
                elif isinstance(curr, NavigableString):
                    t = str(curr).strip()
                    if t and len(t) > 2 and t not in text_lines:
                        text_lines.append(t)
                curr = curr.next_sibling

            blocks: List[LegalBlock] = [
                LegalBlock(block_type="LEDD", text=line, order=i)
                for i, line in enumerate(text_lines, start=1) if line.strip()
            ]
            if not blocks:
                blocks = [LegalBlock(block_type="LEDD", text=h_text, order=1)]

            source_text = "\n\n".join(b.text for b in blocks if b.text).strip()
            source_sec_key = f"{canon_id}/sec-{roman_str}"
            source_url = cls._get_source_url(regulation_dict, canon_id, f"sec-{roman_str}")

            sec_obj = NormalizedLegalSection(
                legal_document_id=canon_id,
                canonical_document_id=canon_id,
                document_type="REGULATION",
                document_title=doc_title,
                section_type="REGULATION_PROVISION",
                source_section_key=source_sec_key,
                section_number=f"Kap. {roman_str}" if "kapittel" in h_text.lower() else f"Del {roman_str}",
                section_title=h_text,
                raw_html=str(parent),
                source_text=source_text,
                structured_blocks=blocks,
                source_url=source_url,
                candidate_domain_ids=candidate_domains,
                is_active=True,
                is_repealed=False,
                version_date=version_date,
                taxonomy_version="v1",
            )
            sections.append(sec_obj)

        logger.info("Unstructured Type 2: Extracted %d Roman numeral sections for %s", len(sections), canon_id)
        return sections


    @classmethod
    def _handle_oversized_unstructured(
        cls,
        regulation_dict: Dict[str, Any],
        raw_text: str,
        canon_id: str,
        doc_title: str,
    ) -> List[NormalizedLegalSection]:
        candidate_domains = list(regulation_dict.get("candidate_domain_ids") or [])
        version_date = cls._get_version_date(regulation_dict)
        chunks = section_splitter(raw_text, max_tokens=1500)
        sections: List[NormalizedLegalSection] = []

        for idx, chunk_text in enumerate(chunks, 1):
            source_sec_key = f"{canon_id}/sec-{idx}"
            source_url = cls._get_source_url(regulation_dict, canon_id, f"sec-{idx}")
            blocks = [LegalBlock(block_type="LEDD", text=chunk_text, order=1)]

            sections.append(
                NormalizedLegalSection(
                    legal_document_id=canon_id,
                    canonical_document_id=canon_id,
                    document_type="REGULATION",
                    document_title=doc_title,
                    section_type="REGULATION_PROVISION",
                    source_section_key=source_sec_key,
                    section_number=f"sec-{idx}",
                    section_title=f"{doc_title} (Del {idx})",
                    raw_html=f"<p>{chunk_text}</p>",
                    source_text=chunk_text,
                    structured_blocks=blocks,
                    source_url=source_url,
                    candidate_domain_ids=candidate_domains,
                    is_active=True,
                    is_repealed=False,
                    version_date=version_date,
                    taxonomy_version="v1",
                )
            )

        logger.info("Oversized Safeguard: Partitioned %s (>20k chars) into %d sections < 1500 tokens", canon_id, len(sections))
        return sections

    # -------------------------------------------------------------------------
    # Type 4 Handler: Complex HTML / Tables / Multi-tier Bullet Lists
    # -------------------------------------------------------------------------
    @classmethod
    def _handle_type_4_complex_unstructured(
        cls,
        regulation_dict: Dict[str, Any],
        soup: BeautifulSoup,
        raw_text: str,
        canon_id: str,
        doc_title: str,
    ) -> NormalizedLegalSection:
        candidate_domains = list(regulation_dict.get("candidate_domain_ids") or [])
        version_date = cls._get_version_date(regulation_dict)
        source_url = cls._get_source_url(regulation_dict, canon_id, "sec-1")

        blocks: List[LegalBlock] = []
        order_idx = 0

        tables = soup.find_all("table")
        for tbl in tables:
            rows = []
            for tr in tbl.find_all("tr"):
                cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                order_idx += 1
                table_text = "\n".join(rows)
                blocks.append(LegalBlock(block_type="TABLE", text=table_text, order=order_idx))

        list_items = soup.find_all("li")
        for li in list_items:
            li_text = li.get_text(separator=" ", strip=True)
            if li_text:
                order_idx += 1
                blocks.append(LegalBlock(block_type="LIST_ITEM", text=li_text, order=order_idx))

        if not blocks:
            paragraphs = [p.get_text(separator=" ", strip=True) for p in soup.find_all(["p", "div", "article"]) if p.get_text(strip=True)]
            if paragraphs:
                for p_text in paragraphs:
                    order_idx += 1
                    blocks.append(LegalBlock(block_type="LEDD", text=p_text, order=order_idx))
            else:
                order_idx += 1
                blocks.append(LegalBlock(block_type="LEDD", text=raw_text, order=order_idx))

        source_text = "\n\n".join(b.text for b in blocks if b.text).strip()
        source_sec_key = f"{canon_id}/sec-1"

        logger.info("Unstructured Type 4: Extracted complex table/list section (%d blocks) for %s", len(blocks), canon_id)
        return NormalizedLegalSection(
            legal_document_id=canon_id,
            canonical_document_id=canon_id,
            document_type="REGULATION",
            document_title=doc_title,
            section_type="REGULATION_PROVISION",
            source_section_key=source_sec_key,
            section_number="sec-1",
            section_title=doc_title,
            raw_html=str(soup),
            source_text=source_text,
            structured_blocks=blocks,
            source_url=source_url,
            candidate_domain_ids=candidate_domains,
            is_active=True,
            is_repealed=False,
            version_date=version_date,
            taxonomy_version="v1",
        )

    @classmethod
    def _handle_type_3_single_paragraph(
        cls,
        regulation_dict: Dict[str, Any],
        soup: BeautifulSoup,
        raw_text: str,
        canon_id: str,
        doc_title: str,
    ) -> NormalizedLegalSection:
        candidate_domains = list(regulation_dict.get("candidate_domain_ids") or [])
        version_date = cls._get_version_date(regulation_dict)
        source_url = cls._get_source_url(regulation_dict, canon_id, "sec-1")

        blocks: List[LegalBlock] = []
        p_tags = soup.find_all(["p", "article", "div"])
        extracted_paras = [p.get_text(separator=" ", strip=True) for p in p_tags if p.get_text(strip=True)]

        if extracted_paras:
            for idx, p_text in enumerate(extracted_paras, start=1):
                blocks.append(LegalBlock(block_type="LEDD", text=p_text, order=idx))
        else:
            blocks.append(LegalBlock(block_type="LEDD", text=raw_text, order=1))

        source_text = "\n\n".join(b.text for b in blocks if b.text).strip()
        source_sec_key = f"{canon_id}/sec-1"

        logger.info("Unstructured Type 3: Extracted single-paragraph section (%d blocks) for %s", len(blocks), canon_id)
        return NormalizedLegalSection(
            legal_document_id=canon_id,
            canonical_document_id=canon_id,
            document_type="REGULATION",
            document_title=doc_title,
            section_type="REGULATION_PROVISION",
            source_section_key=source_sec_key,
            section_number="sec-1",
            section_title=doc_title,
            raw_html=str(soup),
            source_text=source_text,
            structured_blocks=blocks,
            source_url=source_url,
            candidate_domain_ids=candidate_domains,
            is_active=True,
            is_repealed=False,
            version_date=version_date,
            taxonomy_version="v1",
        )
    @staticmethod
    def _get_version_date(regulation_dict: Dict[str, Any]) -> str:
        return str(
            regulation_dict.get("sist_endret_dato")
            or regulation_dict.get("last_amended_date")
            or regulation_dict.get("kunngjort_dato")
            or regulation_dict.get("announced_date")
            or regulation_dict.get("ikrafttredelse_dato")
            or regulation_dict.get("dato")
            or regulation_dict.get("version_date")
            or ""
        ).strip()

    @staticmethod
    def _get_source_url(regulation_dict: Dict[str, Any], canon_id: str, sec_suffix: str = "") -> str:
        base_url = str(
            regulation_dict.get("lovdata_url")
            or regulation_dict.get("source_doc_url")
            or regulation_dict.get("url")
            or (f"https://lovdata.no/dokument/{canon_id}" if canon_id else "")
        ).strip()
        if sec_suffix and not base_url.endswith(sec_suffix):
            return f"{base_url}/{sec_suffix}"
        return base_url
