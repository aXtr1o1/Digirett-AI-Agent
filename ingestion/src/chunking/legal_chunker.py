from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False

from ingestion.models.legal_section import (
    LegalBlock,
    NormalizedLegalSection,
    StructuralChunk,
)
from ingestion.src.config import (
    LEGAL_CHUNK_MAX_TOKENS,
    LEGAL_CHUNK_OVERLAP_TOKENS,
    LEGAL_CHUNK_CHARS_PER_TOKEN,
)

logger = logging.getLogger(__name__)


class TokenCounter:
    """Calculates token length using tiktoken cl100k_base or character approximation."""

    def __init__(self, encoding_name: str = "cl100k_base", chars_per_token: int = LEGAL_CHUNK_CHARS_PER_TOKEN) -> None:
        self.encoding = None
        self.chars_per_token = chars_per_token
        if _TIKTOKEN_AVAILABLE:
            try:
                self.encoding = tiktoken.get_encoding(encoding_name)
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
        return max(1, len(text) // self.chars_per_token)


class LegalSectionChunker:
    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
    _CROSS_REF_PATTERN = re.compile(r"(?:jf\.|se|etter|i medhold av)\s+§+\s*(\d+[a-z]?(?:-\d+)?)", re.IGNORECASE)
    _DEFINITION_KEYWORDS = (
        "definisjon",
        "menes",
        "betyr",
        "forstås som",
        "med dette menes",
        "definisjoner",
    )

    def __init__(
        self,
        max_tokens: int = LEGAL_CHUNK_MAX_TOKENS,
        overlap_tokens: int = LEGAL_CHUNK_OVERLAP_TOKENS,
        token_counter: Optional[TokenCounter] = None,
    ) -> None:
        self.max_tokens = max(10, max_tokens)
        self.overlap_tokens = max(0, min(overlap_tokens, self.max_tokens - 1))
        self.tc = token_counter or TokenCounter()

    def chunk_section(self, section: NormalizedLegalSection) -> List[StructuralChunk]:
        """
        Chunks a single NormalizedLegalSection into one or more StructuralChunks
        with sliding overlap when exceeding max_tokens.
        """
        raw_blocks = section.structured_blocks
        if not raw_blocks:
            # Fallback if structured_blocks is empty but source_text exists
            if section.source_text.strip():
                raw_blocks = [
                    LegalBlock(block_type="TEXT", text=section.source_text.strip(), order=0)
                ]
            else:
                return []

        # Filter non-empty blocks while preserving their original indices
        blocks_with_idx = [
            (idx, b.text.strip())
            for idx, b in enumerate(raw_blocks)
            if b.text and b.text.strip()
        ]
        if not blocks_with_idx:
            return []

        # Level 0 Check: Entire § within token limit
        total_tokens = self.tc.count(section.source_text)
        if total_tokens <= self.max_tokens:
            return [
                StructuralChunk(
                    source_section_key=section.source_section_key,
                    chunk_index=1,
                    source_text=section.source_text,
                    token_count=total_tokens,
                    source_block_start=0,
                    source_block_end=len(raw_blocks) - 1,
                    is_definition=self._is_definition(section.source_text),
                    cross_refs=self._extract_cross_refs(section.source_text),
                    section_ref=section.section_number,
                )
            ]

        # Hierarchical Splitting across structured blocks with sliding overlap
        chunks: List[StructuralChunk] = []
        chunk_idx = 1
        num_blocks = len(blocks_with_idx)
        block_tokens = [(idx, text, self.tc.count(text)) for idx, text in blocks_with_idx]

        i = 0
        while i < num_blocks:
            orig_idx_i, text_i, tok_i = block_tokens[i]

            # If a single block itself exceeds max_tokens, split it internally
            if tok_i > self.max_tokens:
                sub_chunks = self._split_oversized_text(text_i)
                for sc in sub_chunks:
                    chunks.append(
                        StructuralChunk(
                            source_section_key=section.source_section_key,
                            chunk_index=chunk_idx,
                            source_text=sc,
                            token_count=self.tc.count(sc),
                            source_block_start=orig_idx_i,
                            source_block_end=orig_idx_i,
                            is_definition=self._is_definition(sc),
                            cross_refs=self._extract_cross_refs(sc),
                            section_ref=section.section_number,
                        )
                    )
                    chunk_idx += 1
                i += 1
                continue

            # Accumulate blocks until max_tokens is reached
            current_texts: List[str] = [text_i]
            cur_tokens = tok_i
            j = i + 1

            while j < num_blocks:
                orig_idx_j, text_j, tok_j = block_tokens[j]
                if tok_j > self.max_tokens:
                    break
                if cur_tokens + tok_j > self.max_tokens:
                    break
                current_texts.append(text_j)
                cur_tokens += tok_j
                j += 1

            combined = "\n\n".join(current_texts)
            start_block_orig = block_tokens[i][0]
            end_block_orig = block_tokens[j - 1][0]

            chunks.append(
                StructuralChunk(
                    source_section_key=section.source_section_key,
                    chunk_index=chunk_idx,
                    source_text=combined,
                    token_count=self.tc.count(combined),
                    source_block_start=start_block_orig,
                    source_block_end=end_block_orig,
                    is_definition=self._is_definition(combined),
                    cross_refs=self._extract_cross_refs(combined),
                    section_ref=section.section_number,
                )
            )
            chunk_idx += 1

            if j >= num_blocks:
                break

            # Calculate next start index with overlap
            if self.overlap_tokens > 0:
                overlap_accum = 0
                next_start = j
                for k in range(j - 1, i, -1):
                    _, _, tok_k = block_tokens[k]
                    if overlap_accum + tok_k <= self.overlap_tokens:
                        overlap_accum += tok_k
                        next_start = k
                    else:
                        break
                i = next_start
            else:
                i = j

        return chunks

    def _split_oversized_text(self, text: str) -> List[str]:
        """Splits an oversized block by sentence boundaries with sliding overlap."""
        sentences = [s.strip() for s in self._SENTENCE_BOUNDARY.split(text) if s.strip()]
        if not sentences:
            return [text]

        sent_infos = [(s, self.tc.count(s)) for s in sentences]
        sub_chunks: List[str] = []
        num_sents = len(sent_infos)

        i = 0
        while i < num_sents:
            s_text, s_tok = sent_infos[i]
            if s_tok > self.max_tokens:
                sub_chunks.extend(self._hard_token_split(s_text))
                i += 1
                continue

            current_sents = [s_text]
            cur_tokens = s_tok
            j = i + 1

            while j < num_sents:
                next_text, next_tok = sent_infos[j]
                if next_tok > self.max_tokens:
                    break
                if cur_tokens + next_tok > self.max_tokens:
                    break
                current_sents.append(next_text)
                cur_tokens += next_tok
                j += 1

            sub_chunks.append(" ".join(current_sents))
            if j >= num_sents:
                break

            # Calculate overlap for the next sentence window
            if self.overlap_tokens > 0:
                overlap_accum = 0
                next_start = j
                for k in range(j - 1, i, -1):
                    _, tok_k = sent_infos[k]
                    if overlap_accum + tok_k <= self.overlap_tokens:
                        overlap_accum += tok_k
                        next_start = k
                    else:
                        break
                i = next_start
            else:
                i = j

        return sub_chunks

    def _hard_token_split(self, text: str) -> List[str]:
        """Hard fallback word boundary split for sentences exceeding max tokens with sliding overlap."""
        words = text.split()
        if not words:
            return []

        word_tokens = [(w, self.tc.count(w)) for w in words]
        chunks: List[str] = []
        num_words = len(word_tokens)

        i = 0
        while i < num_words:
            current_words: List[str] = []
            cur_tokens = 0
            j = i

            while j < num_words:
                w_text, w_tok = word_tokens[j]
                if current_words and cur_tokens + w_tok > self.max_tokens:
                    break
                current_words.append(w_text)
                cur_tokens += w_tok
                j += 1

            if not current_words:
                current_words.append(word_tokens[i][0])
                j = i + 1

            chunks.append(" ".join(current_words))
            if j >= num_words:
                break

            if self.overlap_tokens > 0:
                overlap_accum = 0
                next_start = j
                for k in range(j - 1, i, -1):
                    _, tok_k = word_tokens[k]
                    if overlap_accum + tok_k <= self.overlap_tokens:
                        overlap_accum += tok_k
                        next_start = k
                    else:
                        break
                i = next_start
            else:
                i = j

        return chunks

    def _extract_cross_refs(self, text: str) -> List[str]:
        return [f"§ {m}" for m in self._CROSS_REF_PATTERN.findall(text)]

    def _is_definition(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in self._DEFINITION_KEYWORDS)
