from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

try:
    import tiktoken

    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False

from ingestion.src.config import MAX_CHUNK_SIZE_CHARS, MILVUS_TEXT_LIMIT


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SectionInput:
    document_id: str
    file_name: str
    text: str
    source_id: str
    source_doc_url: str
    source_ref: str
    section_ref: str
    domain: str
    subdomain: str
    b2b_b2c: str
    tier: str
    jurisdiction: str
    doc_title: str
    version_date: str
    language: str = "nb"
    chapter_context: str = ""


class TokenCounter:
    _CHARS_PER_TOKEN = 4

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self.encoding = None
        self.method = "estimate"

        if _TIKTOKEN_AVAILABLE:
            try:
                self.encoding = tiktoken.get_encoding(encoding_name)
                self.method = "tiktoken"
            except Exception:
                self.encoding = None

    def count(self, text: str) -> int:
        if not text:
            return 0

        if self.encoding is not None:
            try:
                return len(self.encoding.encode(text))
            except Exception:
                pass

        return max(1, len(text) // self._CHARS_PER_TOKEN)


class ChunkEnricher:
    @staticmethod
    def build(
        raw_text: str,
        doc_title: str,
        citation_anchor: str,
        chapter_context: str = "",
    ) -> str:
        parts: List[str] = []

        if doc_title:
            parts.append(f"[Lov: {doc_title}]")

        if chapter_context and chapter_context.lower() not in citation_anchor.lower():
            parts.append(f"[{chapter_context}]")

        if citation_anchor:
            parts.append(f"[{citation_anchor}]")

        prefix = " ".join(parts).strip()

        return f"{prefix} {raw_text}".strip() if prefix else raw_text.strip()


class SectionSplitter:
    MAX_TOKENS = 2000
    MAX_CHARS = MAX_CHUNK_SIZE_CHARS
    EMBED_HARD_CAP = 8000

    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
    _NUMBERED_LEDD = re.compile(r"(?m)^\s*\((\d+)\)\s")
    _ENUM_SPLIT = re.compile(
        r"(?=\b[a-z]\)\s|\bførste punktum\b|\bannet punktum\b)",
        re.IGNORECASE,
    )
    _EXCEPTION_MARKERS = re.compile(
        r"\b(med\s+mindre|likevel|unntak|dog|bortsett\s+fra)\b",
        re.IGNORECASE,
    )

    def __init__(self, token_counter: Optional[TokenCounter] = None) -> None:
        self.tc = token_counter or TokenCounter()

    def split(self, section_text: str) -> List[str]:
        full = section_text.strip()

        if not full:
            return []

        tokens = self.tc.count(full)
        chars = len(full)

        if tokens <= self.MAX_TOKENS and chars <= self.MAX_CHARS:
            return [full]

        ledd_blocks = self._split_by_ledd(full)

        if len(ledd_blocks) > 1:
            merged = self._merge_short_blocks(ledd_blocks)
            merged = self._merge_exception_ledd(merged)
            return self._enforce_hard_cap(merged)

        enum_blocks = self._split_by_enumeration(full)

        if len(enum_blocks) > 1:
            return self._enforce_hard_cap(
                self._merge_short_blocks(enum_blocks)
            )

        return self._enforce_hard_cap(self._split_by_sentences(full))

    def _split_by_ledd(self, text: str) -> List[str]:
        lines = [l.rstrip() for l in text.splitlines() if l.strip()]

        if not lines:
            return []

        groups: List[List[str]] = []
        current: List[str] = []

        for idx, line in enumerate(lines):
            if idx == 0:
                current.append(line)
                continue

            if self._NUMBERED_LEDD.match(line):
                groups.append(current)
                current = [line]
            else:
                current.append(line)

        if current:
            groups.append(current)

        if len(groups) <= 1:
            return [text]

        result: List[str] = []
        prev_last_sentence = ""

        for i, group in enumerate(groups):
            block = "\n".join(group)

            if i > 0 and prev_last_sentence:
                block = prev_last_sentence + "\n" + block

            result.append(block)
            prev_last_sentence = self._last_sentence("\n".join(group))

        return result

    def _last_sentence(self, text: str) -> str:
        sentences = self._SENTENCE_BOUNDARY.split(text.strip())
        return sentences[-1].strip() if sentences else ""

    def _split_by_enumeration(self, text: str) -> List[str]:
        parts = self._ENUM_SPLIT.split(text)
        return [p.strip() for p in parts if p.strip()]

    def _split_by_sentences(self, text: str) -> List[str]:
        sentences = [
            s.strip()
            for s in self._SENTENCE_BOUNDARY.split(text)
            if s.strip()
        ]

        if not sentences:
            return [text]

        blocks: List[str] = []
        current: List[str] = []
        current_tokens = 0

        for sentence in sentences:
            s_tok = self.tc.count(sentence)

            if current and current_tokens + s_tok > self.MAX_TOKENS:
                blocks.append(" ".join(current).strip())
                current = [sentence]
                current_tokens = s_tok
            else:
                current.append(sentence)
                current_tokens += s_tok

        if current:
            blocks.append(" ".join(current).strip())

        return blocks

    def _merge_short_blocks(self, blocks: List[str]) -> List[str]:
        merged: List[str] = []
        buf = ""
        buf_tokens = 0

        for block in blocks:
            b_tok = self.tc.count(block)

            if buf and buf_tokens + b_tok > self.MAX_TOKENS:
                merged.append(buf)
                buf = block
                buf_tokens = b_tok
            else:
                buf = (buf + "\n" + block).strip() if buf else block
                buf_tokens += b_tok

        if buf:
            merged.append(buf)

        return merged if merged else blocks

    def _merge_exception_ledd(self, blocks: List[str]) -> List[str]:
        if len(blocks) <= 1:
            return blocks

        merged: List[str] = []

        for block in blocks:
            if (
                merged
                and self._EXCEPTION_MARKERS.search(block[:200])
                and len(merged[-1]) + len(block) <= self.MAX_CHARS
            ):
                merged[-1] = merged[-1].rstrip() + "\n\n" + block.lstrip()
            else:
                merged.append(block)

        return merged

    def _enforce_hard_cap(self, blocks: List[str]) -> List[str]:
        result: List[str] = []

        for block in blocks:
            if self.tc.count(block) <= self.EMBED_HARD_CAP:
                result.append(block)
                continue

            words = block.split()
            cur_words: List[str] = []
            cur_tokens = 0

            for word in words:
                w_tok = self.tc.count(word)

                if cur_words and cur_tokens + w_tok > self.EMBED_HARD_CAP:
                    result.append(" ".join(cur_words))
                    cur_words = [word]
                    cur_tokens = w_tok
                else:
                    cur_words.append(word)
                    cur_tokens += w_tok

            if cur_words:
                result.append(" ".join(cur_words))

        return result


class SectionAwareChunker:
    def __init__(self) -> None:
        self.tc = TokenCounter()
        self.splitter = SectionSplitter(token_counter=self.tc)

    def chunk_section(self, section: SectionInput) -> List[Dict[str, Any]]:
        raw_section_text = section.text.strip()

        if not raw_section_text:
            return []

        blocks = self.splitter.split(raw_section_text)

        if not blocks:
            return []

        chunk_dicts: List[Dict[str, Any]] = []
        total_blocks = len(blocks)

        for idx, raw_text in enumerate(blocks, start=1):
            clean_base = section.source_doc_url.split("::")[0].split("#")[0].rstrip("/")
            chunk_id = self._build_chunk_id(
                source_id=section.source_id,
                anchor=section.section_ref,
                version_date=section.version_date,
                part=None if total_blocks == 1 else f"p{idx}",
            )

            enriched_text = ChunkEnricher.build(
                raw_text=raw_text,
                doc_title=section.doc_title,
                citation_anchor=section.section_ref,
                chapter_context=section.chapter_context,
            )

            token_count = self.tc.count(enriched_text)

            chunk_dicts.append(
                {
                    "chunk_id": chunk_id,
                    "chunk_hash": hashlib.sha256(
                        raw_text.encode("utf-8")
                    ).hexdigest()[:16],
                    "chunk_seq": idx,
                    "document_id": section.document_id,
                    "file_name": section.file_name,
                    "text": raw_text,
                    "enriched_text": enriched_text,
                    "source_id": section.source_id,
                    "source_doc_url": clean_base,
                    "section_url": f"{clean_base}#{quote(section.section_ref.replace(' ', ''), safe='-_.')}",
                    "source_ref": section.source_ref,
                    "citation_anchor": section.section_ref,
                    "section_ref": section.section_ref,
                    "doc_title": section.doc_title,
                    "version_date": section.version_date,
                    "language": section.language,
                    "domain": section.domain,
                    "subdomain": section.subdomain,
                    "b2b_b2c": section.b2b_b2c,
                    "tier": section.tier,
                    "jurisdiction": section.jurisdiction,
                    "cross_refs": self._extract_cross_refs(raw_text),
                    "is_definition": self._is_definition(raw_text),
                    "token_count": token_count,
                    "is_split": total_blocks > 1,
                }
            )

        return chunk_dicts

    def _build_chunk_id(
        self,
        source_id: str,
        anchor: str,
        version_date: str,
        part: Optional[str],
    ) -> str:
        anchor_clean = re.sub(
            r"[^A-Za-z0-9\-]+",
            "-",
            anchor.replace("§", "par"),
        ).strip("-")

        if part:
            return f"{source_id}__{anchor_clean}__{version_date}__{part}"

        return f"{source_id}__{anchor_clean}__{version_date}__full"

    def _extract_cross_refs(self, text: str) -> List[str]:
        pattern = re.compile(
            r"(?:jf\.|se|etter|i medhold av)\s+§+\s*(\d+[a-z]?(?:-\d+)?)",
            re.IGNORECASE,
        )

        return [f"§ {m}" for m in pattern.findall(text)]

    def _is_definition(self, text: str) -> bool:
        text_lower = text.lower()

        keywords = [
            "definisjon",
            "menes",
            "betyr",
            "forstås som",
            "med dette menes",
            "definisjoner",
        ]

        return any(kw in text_lower for kw in keywords)


def validate_chunk_dict(chunk: Dict[str, Any]) -> tuple[bool, str]:
    if not chunk.get("text", "").strip():
        return False, "Empty text"

    if len(chunk.get("text", "")) > MILVUS_TEXT_LIMIT:
        return False, f"text too large: {len(chunk['text'])}"

    if len(chunk.get("enriched_text", "")) > MILVUS_TEXT_LIMIT:
        return False, f"enriched_text too large: {len(chunk['enriched_text'])}"

    if not chunk.get("source_id"):
        return False, "Missing source_id"

    if not chunk.get("source_doc_url"):
        return False, "Missing source_doc_url"

    if not chunk.get("source_ref"):
        return False, "Missing source_ref"

    if not chunk.get("section_ref"):
        return False, "Missing section_ref"

    return True, "ok"


# ---------------------------------------------------------------------------
# Aliases used by main.py
# ---------------------------------------------------------------------------

_SECTION_PATTERN = re.compile(
    r"(§\s*\d+[a-z]?(?:-\d+)?[^\n]*(?:\n(?!§\s*\d).*)*)",
    re.IGNORECASE,
)


class DigiRettChunker(SectionAwareChunker):
    """
    Top-level chunker called by main.py via::

        chunker.chunk(text=..., source_id=..., source_url=..., ...)

    Splits the full document text into § sections, then delegates each
    section to SectionAwareChunker.chunk_section().  The returned chunk
    dicts include a ``citation_anchor`` key so main.py can group them.
    """

    def chunk(
        self,
        *,
        text: str,
        source_id: str,
        source_url: str,
        doc_title: str,
        domain: str,
        subdomain: str,
        source_type: str,
        tier: int,
        version_date: str,
        language: str = "nb",
    ) -> List[Dict[str, Any]]:
        sections = self._split_into_sections(text)

        all_chunks: List[Dict[str, Any]] = []

        for section_ref, section_text in sections:
            section = SectionInput(
                document_id="",
                file_name="",
                text=section_text,
                source_id=source_id,
                source_doc_url=source_url,
                source_ref=source_type,
                section_ref=section_ref,
                domain=domain,
                subdomain=subdomain,
                b2b_b2c="BOTH",
                tier=str(tier),
                jurisdiction="NO",
                doc_title=doc_title,
                version_date=version_date,
                language=language,
            )
            all_chunks.extend(self.chunk_section(section))

        return all_chunks

    def _split_into_sections(self, text: str) -> List[tuple[str, str]]:
        """
        Returns a list of (section_ref, section_text) tuples.
        Falls back to a single pseudo-section if no § markers are found.
        """
        matches = list(_SECTION_PATTERN.finditer(text))

        if not matches:
            return [("§1", text.strip())]

        sections: List[tuple[str, str]] = []

        for match in matches:
            block = match.group(0).strip()
            first_line = block.splitlines()[0].strip()
            ref_match = re.match(r"(§\s*\d+[a-z]?(?:-\d+)?)", first_line, re.IGNORECASE)
            section_ref = ref_match.group(1).replace(" ", "") if ref_match else first_line[:40]
            sections.append((section_ref, block))

        return sections


validate_chunk = validate_chunk_dict