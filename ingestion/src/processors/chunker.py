"""
Dynamic Norwegian Lovdata Hierarchical Chunking System - TOKEN-BASED VERSION v2
KEY IMPROVEMENTS FOR RETRIEVAL ACCURACY (0.6 → 0.8+):

1. ✅ Contextual chunk enrichment (prepend parent title + law name to each chunk text)
2. ✅ Filter amendment laws (LTI) from primary law retrieval
3. ✅ Paragraph-level grouping (merge tiny child lines into coherent § blocks)
4. ✅ Richer metadata per chunk (law_name, url, paragraph_number, kapittel)
5. ✅ Smarter parent detection — avoid splitting § into too-small fragments
6. ✅ Token-based chunking preserved
7. ✅ Overlap carries parent context, not random sentence
"""

import hashlib
import re
import os
import uuid
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logging.warning("tiktoken not available, falling back to character-based estimation")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# TOKEN COUNTER (unchanged)
# ============================================================================

class TokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base"):
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoding = tiktoken.get_encoding(encoding_name)
                self.method = "tiktoken"
                logger.info(f"✅ Token counter initialized with {encoding_name}")
            except Exception as e:
                logger.warning(f"Failed to load tiktoken encoding: {e}")
                self.encoding = None
                self.method = "estimate"
        else:
            self.encoding = None
            self.method = "estimate"

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self.method == "tiktoken" and self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception:
                return self._estimate_tokens(text)
        return self._estimate_tokens(text)

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ParentNode:
    parent_index: int
    parent_title: str
    parent_type: str
    paragraph_number: Optional[str] = None   # ✅ NEW: "§ 3-4", "Kapittel 2" etc.
    kapittel: Optional[str] = None           # ✅ NEW: current chapter heading
    children: List[Dict] = field(default_factory=list)


@dataclass
class DocumentMetadata:
    file_name: str
    file_hash: str
    datokode: Optional[str] = None
    dokument_id: Optional[str] = None
    departement: Optional[str] = None
    tittel: Optional[str] = None
    korttittel: Optional[str] = None
    year: Optional[int] = None
    i_kraft_fra: Optional[str] = None
    rettsomrade: Optional[str] = None
    publisert_i: Optional[str] = None
    kunngjort: Optional[str] = None
    lovdata_url: Optional[str] = None        # ✅ NEW: canonical URL
    law_short_name: Optional[str] = None     # ✅ NEW: "aksjeloven", "merverdiavgiftsloven"
    is_amendment: bool = False               # ✅ NEW: True for LTI/amendment laws

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Chunk:
    chunk_id: str
    file_name: str
    file_hash: str
    parent_index: int
    child_index: int
    parent_type: str
    parent_title: str
    text: str
    enriched_text: str = ""          # ✅ NEW: text with context prefix for embedding
    token_count: int = 0
    is_split: bool = False
    split_index: int = 0
    paragraph_number: Optional[str] = None   # ✅ NEW
    kapittel: Optional[str] = None           # ✅ NEW
    law_short_name: Optional[str] = None     # ✅ NEW
    lovdata_url: Optional[str] = None        # ✅ NEW
    is_amendment: bool = False               # ✅ NEW
    metadata: Optional[Dict] = None
    article_title: Optional[str] = None


    def to_dict(self) -> Dict:
        result = {
            "chunk_id": self.chunk_id,
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "parent_index": self.parent_index,
            "child_index": self.child_index,
            "parent_type": self.parent_type,
            "parent_title": self.parent_title,
            "text": self.text,
            "enriched_text": self.enriched_text,
            "token_count": self.token_count,
            "is_split": self.is_split,
            "split_index": self.split_index,
            "paragraph_number": self.paragraph_number,
            "kapittel": self.kapittel,
            "law_short_name": self.law_short_name,
            "lovdata_url": self.lovdata_url,
            "is_amendment": self.is_amendment,
            "article_title": self.article_title,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


# ============================================================================
# TEXT SPLITTER (TOKEN-AWARE, unchanged core logic)
# ============================================================================

class TokenBoundTextSplitter:
    def __init__(self, max_tokens: int = 400, overlap_tokens: int = 50,
                 token_counter: Optional[TokenCounter] = None):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.token_counter = token_counter or TokenCounter()
        self.sentence_endings = re.compile(r'[.!?]\s+')

    def split_text(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []
        total_tokens = self.token_counter.count_tokens(text)
        if total_tokens <= self.max_tokens:
            return [text]
        sentences = self._split_into_sentences(text)
        chunks, current_chunk, current_tokens = [], [], 0
        for sentence in sentences:
            sentence_tokens = self.token_counter.count_tokens(sentence)
            if sentence_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk, current_tokens = [], 0
                chunks.extend(self._split_long_sentence(sentence))
                continue
            if current_tokens + sentence_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                if self.overlap_tokens > 0 and current_chunk:
                    overlap_text = self._get_overlap_text(current_chunk)
                    current_chunk = [overlap_text, sentence]
                    current_tokens = self.token_counter.count_tokens(" ".join(current_chunk))
                else:
                    current_chunk = [sentence]
                    current_tokens = sentence_tokens
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        sentences = self.sentence_endings.split(text)
        return [s.strip() for s in sentences if s.strip()]

    def _split_long_sentence(self, sentence: str) -> List[str]:
        words = sentence.split()
        chunks, current_chunk, current_tokens = [], [], 0
        for word in words:
            word_tokens = self.token_counter.count_tokens(word)
            if current_tokens + word_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_tokens = word_tokens
            else:
                current_chunk.append(word)
                current_tokens += word_tokens
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        return chunks

    def _get_overlap_text(self, chunk: List[str]) -> str:
        overlap_sentences, overlap_tokens = [], 0
        for sentence in reversed(chunk):
            sentence_tokens = self.token_counter.count_tokens(sentence)
            if overlap_tokens + sentence_tokens <= self.overlap_tokens:
                overlap_sentences.insert(0, sentence)
                overlap_tokens += sentence_tokens
            else:
                break
        return " ".join(overlap_sentences)


# ============================================================================
# ✅ NEW: LAW NAME & URL MAPPER
# ============================================================================

class LawNameMapper:
    """
    Maps file names to canonical law names and Lovdata URLs.
    Add more entries as your corpus grows.
    """

    # Pattern: file prefix → (short_name, lovdata_url)
    FILE_TO_LAW = {
        "nl-19970613-044": ("aksjeloven", "https://lovdata.no/dokument/NL/lov/1997-06-13-44"),
        "nl-19970613-045": ("allmennaksjeloven", "https://lovdata.no/dokument/NL/lov/1997-06-13-45"),
        "nl-19850621-080": ("prokuraloven", "https://lovdata.no/dokument/NL/lov/1985-06-21-80"),
        "nl-19940621-015": ("foretaksregisterloven", "https://lovdata.no/dokument/NL/lov/1994-06-21-15"),
        "nl-19940603-015": ("enhetsregisterloven", "https://lovdata.no/dokument/NL/lov/1994-06-03-15"),
        "nl-19850621-079": ("foretaksnavneloven", "https://lovdata.no/dokument/NL/lov/1985-06-21-79"),
        "nl-19980717-056": ("regnskapsloven", "https://lovdata.no/dokument/NL/lov/1998-07-17-56"),
        "nl-20041119-073": ("bokføringsloven", "https://lovdata.no/dokument/NL/lov/2004-11-19-73"),
        "nl-20200117-004": ("revisorloven", "https://lovdata.no/dokument/NL/lov/2020-01-17-4"),
        "nl-20160527-014": ("skatteforvaltningsloven", "https://lovdata.no/dokument/NL/lov/2016-05-27-14"),
        "nl-19990326-014": ("skatteloven", "https://lovdata.no/dokument/NL/lov/1999-03-26-14"),
        "nl-20090619-058": ("merverdiavgiftsloven", "https://lovdata.no/dokument/NL/lov/2009-06-19-58"),
        "nl-19840608-058": ("konkursloven", "https://lovdata.no/dokument/NL/lov/1984-06-08-58"),
        "nl-19840608-059": ("dekningsloven", "https://lovdata.no/dokument/NL/lov/1984-06-08-59"),
        "nl-19800208-002": ("panteloven", "https://lovdata.no/dokument/NL/lov/1980-02-08-2"),
        "nl-20050617-062": ("arbeidsmiljøloven", "https://lovdata.no/dokument/NL/lov/2005-06-17-62"),
        # Forskrifter
        "nl-20241117-2804": ("innsynsforskriften_aksjeeierbok", "https://lovdata.no/forskrift/2024-11-17-2804"),
        "nl-20071130-1336": ("forskrift_unntak_8_10", "https://lovdata.no/forskrift/2007-11-30-1336"),
    }

    # Korttittel → (short_name, url) — extracted from metadata
    KORTTITTEL_MAP = {
        "aksjeloven": ("aksjeloven", "https://lovdata.no/dokument/NL/lov/1997-06-13-44"),
        "allmennaksjeloven": ("allmennaksjeloven", "https://lovdata.no/dokument/NL/lov/1997-06-13-45"),
        "merverdiavgiftsloven": ("merverdiavgiftsloven", "https://lovdata.no/dokument/NL/lov/2009-06-19-58"),
        "skatteforvaltningsloven": ("skatteforvaltningsloven", "https://lovdata.no/dokument/NL/lov/2016-05-27-14"),
        "skatteloven": ("skatteloven", "https://lovdata.no/dokument/NL/lov/1999-03-26-14"),
        "arbeidsmiljøloven": ("arbeidsmiljøloven", "https://lovdata.no/dokument/NL/lov/2005-06-17-62"),
        "regnskapsloven": ("regnskapsloven", "https://lovdata.no/dokument/NL/lov/1998-07-17-56"),
        "bokføringsloven": ("bokføringsloven", "https://lovdata.no/dokument/NL/lov/2004-11-19-73"),
        "foretaksregisterloven": ("foretaksregisterloven", "https://lovdata.no/dokument/NL/lov/1994-06-21-15"),
        "enhetsregisterloven": ("enhetsregisterloven", "https://lovdata.no/dokument/NL/lov/1994-06-03-15"),
        "prokuraloven": ("prokuraloven", "https://lovdata.no/dokument/NL/lov/1985-06-21-80"),
        "revisorloven": ("revisorloven", "https://lovdata.no/dokument/NL/lov/2020-01-17-4"),
        "panteloven": ("panteloven", "https://lovdata.no/dokument/NL/lov/1980-02-08-2"),
        "konkursloven": ("konkursloven", "https://lovdata.no/dokument/NL/lov/1984-06-08-58"),
        "dekningsloven": ("dekningsloven", "https://lovdata.no/dokument/NL/lov/1984-06-08-59"),
        "foretaksnavneloven": ("foretaksnavneloven", "https://lovdata.no/dokument/NL/lov/1985-06-21-79"),
    }

    @classmethod
    def resolve(cls, file_name: str, korttittel: str = None) -> Tuple[Optional[str], Optional[str], bool]:
        """
        Returns (law_short_name, lovdata_url, is_amendment)
        Amendment laws (LTI) are flagged so they can be deprioritized.
        """
        stem = file_name.lower().replace(".txt", "")

        # ✅ Detect amendment laws (LTI prefix in file or metadata)
        is_amendment = "lti" in stem or stem.startswith("lti-")

        # Try file-based lookup
        for prefix, (name, url) in cls.FILE_TO_LAW.items():
            if stem.startswith(prefix.lower()) or stem == prefix.lower():
                return name, url, is_amendment

        # Try korttittel-based lookup
        if korttittel:
            kt = korttittel.lower().strip()
            if kt in cls.KORTTITTEL_MAP:
                name, url = cls.KORTTITTEL_MAP[kt]
                return name, url, is_amendment

        return None, None, is_amendment


# ============================================================================
# ✅ NEW: CONTEXTUAL ENRICHER
# ============================================================================

class ChunkEnricher:
    """
    Builds enriched_text by prepending law name + paragraph context.
    This is the TEXT that gets embedded — richer context = higher similarity.

    Format:
        [Lov: aksjeloven] [§ 3-4 Erstatning] Tekst her...
    """

    @staticmethod
    def build_enriched_text(
        chunk_text: str,
        law_short_name: Optional[str],
        parent_title: str,
        paragraph_number: Optional[str],
        kapittel: Optional[str],
    ) -> str:
        parts = []

        # Add law name
        if law_short_name:
            parts.append(f"[Lov: {law_short_name}]")

        # Add kapittel if present
        if kapittel and kapittel.lower() not in parent_title.lower():
            parts.append(f"[{kapittel}]")

        # Add paragraph/section heading
        if parent_title:
            parts.append(f"[{parent_title}]")

        prefix = " ".join(parts)
        if prefix:
            return f"{prefix} {chunk_text}"
        return chunk_text


# ============================================================================
# ✅ IMPROVED: PARAGRAPH GROUPER
# ============================================================================

class ParagraphGrouper:
    """
    Groups consecutive child lines under the same § into a single text block.
    Prevents fragments like "(1) Den som..." being a standalone tiny chunk.
    Improves semantic coherence per chunk.
    """

    def __init__(self, max_tokens: int = 400, token_counter: Optional[TokenCounter] = None):
        self.max_tokens = max_tokens
        self.token_counter = token_counter or TokenCounter()

    def group_children(self, children: List[Dict]) -> List[Dict]:
        # 🔒 Remove identical child lines
        seen_lines = set()
        filtered_children = []

        for child in children:
            text = child["text"].strip()
            if text and text not in seen_lines:
                seen_lines.add(text)
                filtered_children.append(child)

        children = filtered_children
        """
        Merge children into grouped blocks.
        Each group is a single coherent text block under the parent.
        """
        if not children:
            return []

        grouped = []
        current_text_parts = []
        current_tokens = 0
        base_child_idx = children[0]["child_index"] if children else 0

        for child in children:
            text = child["text"].strip()
            if not text:
                continue

            child_tokens = self.token_counter.count_tokens(text)

            # If adding this line would exceed the limit, flush current group
            if current_tokens + child_tokens > self.max_tokens and current_text_parts:
                grouped.append({
                    "child_index": base_child_idx,
                    "text": " ".join(current_text_parts)
                })
                base_child_idx = child["child_index"]
                current_text_parts = [text]
                current_tokens = child_tokens
            else:
                current_text_parts.append(text)
                current_tokens += child_tokens

        # Flush last group
        if current_text_parts:
            grouped.append({
                "child_index": base_child_idx,
                "text": " ".join(current_text_parts)
            })

        return grouped


# ============================================================================
# NORWEGIAN TEXT PARSING & CLASSIFICATION (improved)
# ============================================================================

class NorwegianLovdataParser:
    METADATA_FIELDS = {
        'datokode': r'^\s*[-•]?\s*Datokode\s*[:\-]\s*(.+)$',
        'dokument_id': r'^\s*[-•]?\s*DokumentID\s*[:\-]\s*(.+)$',
        'departement': r'^\s*[-•]?\s*Departement\s*[:\-]\s*(.+)$',
        'tittel': r'^\s*[-•]?\s*Tittel\s*[:\-]\s*(.+)$',
        'korttittel': r'^\s*[-•]?\s*Korttittel\s*[:\-]\s*(.+)$',
        'i_kraft_fra': r'^\s*[-•]?\s*I kraft fra\s*[:\-]\s*(.+)$',
        'rettsomrade': r'^\s*[-•]?\s*Rettsområde\s*[:\-]\s*(.+)$',
        'publisert_i': r'^\s*[-•]?\s*Publisert i\s*[:\-]\s*(.+)$',
        'kunngjort': r'^\s*[-•]?\s*Kunngjort\s*[:\-]\s*(.+)$',
        'year': r'^\s*YEAR:\s*(\d{4})\s*$'
    }

    SEPARATOR_PATTERN = re.compile(r'^-{3,}$')

    NORWEGIAN_PATTERNS = {
        'paragraph': re.compile(r'^(§\s*\d+[a-z]?(?:-\d+)?\.?)\s*(.*)$', re.IGNORECASE),
        'kapittel': re.compile(r'^(Kapittel|Kap\.?)\s+([IVXLCDM\d]+)\.?\s*(.*)$', re.IGNORECASE),
        'del': re.compile(r'^Del\s+([IVXLCDM\d]+)\.?\s*(.*)$', re.IGNORECASE),
        'avdeling': re.compile(r'^Avdeling\s+([IVXLCDM\d]+)\.?\s*(.*)$', re.IGNORECASE),
        'artikkel': re.compile(r'^(\d+)\s*(Art\.|Artikkel)\.?\s*(.*)$', re.IGNORECASE),
        'lov_title': re.compile(r'^Lov\s+om\s+(.+)$', re.IGNORECASE),
        'numbered_paren': re.compile(r'^\((\d+)\)\s+(.+)$'),
        'lettered': re.compile(r'^([a-z])\)\s+(.+)$', re.IGNORECASE),
        'roman': re.compile(r'^([IVXLCDM]+)\.?\s+(.+)$'),
        'numbered_dot': re.compile(r'^(\d+)\.?\s+([A-ZÆØÅ].+)$'),
    }

    # ✅ NEW: Patterns that are NOT real parents (amendment markers, table of contents)
    AMENDMENT_LINE_PATTERNS = [
        re.compile(r'skal lyde\s*:', re.IGNORECASE),
        re.compile(r'ny\s+§', re.IGNORECASE),
        re.compile(r'oppheves', re.IGNORECASE),
        re.compile(r'endres til', re.IGNORECASE),
        re.compile(r'tilføyes', re.IGNORECASE),
    ]

    @staticmethod
    def is_separator(line: str) -> bool:
        try:
            return NorwegianLovdataParser.SEPARATOR_PATTERN.match(line.strip()) is not None
        except:
            return False

    @staticmethod
    def is_metadata_line(line: str) -> bool:
        try:
            if not line or len(line) > 300:
                return False
            for pattern in NorwegianLovdataParser.METADATA_FIELDS.values():
                if re.match(pattern, line, re.IGNORECASE):
                    return True
            if line.strip().startswith(('-', '•', '    -')):
                if ':' in line and len(line) < 200:
                    return True
            if re.match(r'^\s*[-•]?\s*Innhold\s*$', line, re.IGNORECASE):
                return True
            return False
        except Exception as e:
            logger.debug(f"Error in is_metadata_line: {e}")
            return False

    @staticmethod
    def extract_paragraph_number(line: str) -> Optional[str]:
        """Extract § number from a line like '§ 3-4. Erstatning'"""
        match = re.match(r'^(§\s*[\d]+[a-z]?(?:-\d+)?)', line.strip(), re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @classmethod
    def classify_norwegian_parent(cls, line: str) -> Optional[Tuple[str, str]]:
        try:
            if len(line) > 300:
                return None
            line_stripped = line.strip()

            # ✅ Skip amendment markers — these are not real structural parents
            for pat in cls.AMENDMENT_LINE_PATTERNS:
                if pat.search(line_stripped):
                    return None

            for pattern_name, pattern in cls.NORWEGIAN_PATTERNS.items():
                match = pattern.match(line_stripped)
                if match:
                    return (pattern_name, line_stripped)
            return None
        except Exception as e:
            logger.debug(f"Error in classify_norwegian_parent: {e}")
            return None

    @staticmethod
    def is_dynamic_parent(line: str) -> bool:
        try:
            if not line or len(line) < 3:
                return False
            line_stripped = line.strip()
            if NorwegianLovdataParser.is_metadata_line(line_stripped):
                return False
            word_count = len(line_stripped.split())
            if word_count > 20 or len(line_stripped) > 200:
                return False
            if word_count < 2:
                return False
            is_capitalized = line_stripped[0].isupper()
            ends_with_colon = line_stripped.endswith(':')
            ends_with_period = line_stripped.endswith('.')
            is_all_caps = line_stripped.isupper()
            if ends_with_colon:
                return True
            if is_all_caps and word_count <= 10:
                return True
            if ends_with_period and 2 <= word_count <= 12 and is_capitalized:
                common_verbs = ['er', 'skal', 'kan', 'må', 'blir', 'har', 'vil']
                if not any(verb in line_stripped.lower().split() for verb in common_verbs):
                    return True
            if re.match(r'^([A-ZÆØÅ]|\d+)\.?\s+[A-ZÆØÅ]', line_stripped):
                return True
            return False
        except Exception as e:
            logger.debug(f"Error in is_dynamic_parent: {e}")
            return False

    @staticmethod
    def is_child_content(line: str) -> bool:
        try:
            line_stripped = line.strip()
            word_count = len(line_stripped.split())
            if word_count < 3:
                if not re.search(r'[0-9§]', line_stripped):
                    return False
            if line_stripped.isupper() and len(line_stripped) > 30:
                return False
            if NorwegianLovdataParser.is_metadata_line(line_stripped):
                return False
            return True
        except Exception as e:
            logger.debug(f"Error in is_child_content: {e}")
            return False

    @staticmethod
    def parse_metadata(lines: List[str]) -> DocumentMetadata:
        metadata = {}
        try:
            separator_idx = None
            for i, line in enumerate(lines[:100]):
                if NorwegianLovdataParser.is_separator(line):
                    separator_idx = i
                    break
            if separator_idx:
                for line in lines[:separator_idx]:
                    for field_name, pattern in NorwegianLovdataParser.METADATA_FIELDS.items():
                        match = re.match(pattern, line, re.IGNORECASE)
                        if match:
                            metadata[field_name] = match.group(1).strip()
                            break
            year = None
            if 'year' in metadata:
                try:
                    year = int(metadata['year'])
                except:
                    pass
            if not year and 'datokode' in metadata:
                year_match = re.search(r'(\d{4})', metadata['datokode'])
                if year_match:
                    year = int(year_match.group(1))
        except Exception as e:
            logger.warning(f"Error parsing metadata: {e}")

        return DocumentMetadata(
            file_name="",
            file_hash="",
            datokode=metadata.get('datokode'),
            dokument_id=metadata.get('dokument_id'),
            departement=metadata.get('departement'),
            tittel=metadata.get('tittel'),
            korttittel=metadata.get('korttittel'),
            year=year,
            i_kraft_fra=metadata.get('i_kraft_fra'),
            rettsomrade=metadata.get('rettsomrade'),
            publisert_i=metadata.get('publisert_i'),
            kunngjort=metadata.get('kunngjort'),
        )

    @classmethod
    def parse_file(cls, text: str, file_name: str) -> Tuple[DocumentMetadata, List[ParentNode]]:
        try:
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            doc_metadata = cls.parse_metadata(lines)
            doc_metadata.file_name = file_name

            content_start = 0
            for i, line in enumerate(lines):
                if cls.is_separator(line):
                    content_start = i + 1
                    break

            parents = []
            current_parent = None
            parent_index = 0
            in_innhold = False
            current_kapittel = None   # ✅ Track current chapter

            for line in lines[content_start:]:
                try:
                    if len(line) < 3:
                        continue
                    if re.match(r'^\s*[-•]?\s*Innhold\s*$', line, re.IGNORECASE):
                        in_innhold = True
                        continue
                    if in_innhold:
                        if cls.is_separator(line):
                            in_innhold = False
                        continue

                    norwegian_parent = cls.classify_norwegian_parent(line)

                    if norwegian_parent is not None:
                        ptype, ptitle = norwegian_parent

                        # ✅ Track kapittel separately — don't reset current_parent
                        if ptype == 'kapittel':
                            current_kapittel = ptitle

                        # Extract paragraph number
                        paragraph_number = cls.extract_paragraph_number(line) if ptype == 'paragraph' else None

                        current_parent = ParentNode(
                            parent_index=parent_index,
                            parent_title=ptitle,
                            parent_type=ptype,
                            paragraph_number=paragraph_number,
                            kapittel=current_kapittel,
                            children=[]
                        )
                        parents.append(current_parent)
                        parent_index += 1

                    elif cls.is_dynamic_parent(line):
                        current_parent = ParentNode(
                            parent_index=parent_index,
                            parent_title=line.strip(),
                            parent_type="dynamic_heading",
                            paragraph_number=None,
                            kapittel=current_kapittel,
                            children=[]
                        )
                        parents.append(current_parent)
                        parent_index += 1

                    elif cls.is_child_content(line) and current_parent is not None:
                        child_idx = len(current_parent.children)
                        current_parent.children.append({
                            "child_index": child_idx,
                            "text": line
                        })

                except Exception as e:
                    logger.warning(f"Error processing line '{line[:50]}': {e}")
                    continue

            if not parents and lines[content_start:]:
                logger.warning(f"No parents found in {file_name}, creating default parent")
                default_parent = ParentNode(
                    parent_index=0,
                    parent_title="Dokumentinnhold",
                    parent_type="default",
                    children=[]
                )
                for idx, line in enumerate(lines[content_start:]):
                    if cls.is_child_content(line):
                        default_parent.children.append({"child_index": idx, "text": line})
                if default_parent.children:
                    parents.append(default_parent)

            return doc_metadata, parents

        except Exception as e:
            logger.error(f"Error parsing file {file_name}: {e}")
            return DocumentMetadata(file_name=file_name, file_hash=""), []


# ============================================================================
# FILE HASH & CHUNK ID GENERATION (unchanged)
# ============================================================================

class FileHasher:
    @staticmethod
    def hash_file(content: str) -> str:
        try:
            return hashlib.sha256(content.encode('utf-8')).hexdigest()
        except Exception as e:
            logger.error(f"Error hashing file: {e}")
            return hashlib.sha256(b"error").hexdigest()

    @staticmethod
    def generate_chunk_id(file_hash: str, parent_idx: int, child_idx: int, split_idx: int = 0) -> str:
        try:
            namespace = uuid.NAMESPACE_DNS
            seed = f"{file_hash}_{parent_idx:04d}_{child_idx:04d}_{split_idx:04d}"
            return str(uuid.uuid5(namespace, seed))
        except Exception as e:
            logger.error(f"Error generating chunk ID: {e}")
            return str(uuid.uuid4())


# ============================================================================
# MAIN CHUNKER (TOKEN-BASED v2 with enrichment)
# ============================================================================

class NorwegianLovdataChunker:
    """
    ✅ v2: Token-based + Contextual Enrichment + Paragraph Grouping

    Accuracy improvements:
    - enriched_text carries law name + paragraph title → embed this, not raw text
    - Paragraph grouper merges fragmented child lines → coherent semantic units
    - Amendment detection → flag LTI files for deprioritization at retrieval time
    - Kapittel tracking → chunk knows which chapter it's in
    - Richer chunk metadata → allows post-retrieval filtering by law name/URL
    """

    def __init__(self, max_tokens: int = 400, overlap_tokens: int = 50):
        self.parser = NorwegianLovdataParser()
        self.hasher = FileHasher()
        self.token_counter = TokenCounter()
        self.text_splitter = TokenBoundTextSplitter(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            token_counter=self.token_counter
        )
        self.paragraph_grouper = ParagraphGrouper(        # ✅ NEW
            max_tokens=max_tokens,
            token_counter=self.token_counter
        )
        self.enricher = ChunkEnricher()                   # ✅ NEW
        self.law_mapper = LawNameMapper()                 # ✅ NEW
        self.error_files = []
        self.success_files = []

        logger.info(
            f"✅ Token-based chunker v2 initialized | "
            f"max_tokens={max_tokens} | overlap={overlap_tokens}"
        )

    def semantic_split(self, text: str) -> List[str]:
        pattern = r'(?=\(\d+\)|\b\d+\.\s|\b[a-z]\)\s|§\s*\d+)'
        parts = re.split(pattern, text)
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            return [text]
        return parts

    def chunk_text(self, text: str, file_name: str, article_title: str = None) -> Tuple[DocumentMetadata, List[Chunk]]:
        try:
            file_hash = self.hasher.hash_file(text)
            # 🔒 GLOBAL DEDUP PROTECTION
            seen_chunk_hashes = set()
            doc_metadata, parents = self.parser.parse_file(text, file_name)
            doc_metadata.file_hash = file_hash

            # 🔥 Inject XML article title into metadata
            if article_title:
                doc_metadata.tittel = article_title

            # ✅ Resolve law name and URL
            law_short_name, lovdata_url, is_amendment = self.law_mapper.resolve(
                file_name,
                korttittel=doc_metadata.korttittel
            )
            doc_metadata.law_short_name = law_short_name
            doc_metadata.lovdata_url = lovdata_url
            doc_metadata.is_amendment = is_amendment

            chunks = []
            total_splits = 0

            for parent in parents:
                # ✅ Group child lines into coherent blocks before chunking
                grouped_children = self.paragraph_grouper.group_children(parent.children)

                for child in grouped_children:
                    child_text = child["text"]
                    child_idx = child["child_index"]

                    semantic_blocks = list(dict.fromkeys(
                    self.semantic_split(child_text)
                    ))

                    for block_index, block_text in enumerate(semantic_blocks):
                        semantic_child_idx = child_idx * 10000 + block_index
                        token_count = self.token_counter.count_tokens(block_text)

                        # ✅ Build enriched text for embedding
                        enriched = self.enricher.build_enriched_text(
                            chunk_text=block_text,
                            law_short_name=law_short_name,
                            parent_title=parent.parent_title,
                            paragraph_number=parent.paragraph_number,
                            kapittel=parent.kapittel,
                        )

                        if token_count <= self.text_splitter.max_tokens:
                            chunk_id = self.hasher.generate_chunk_id(
                                file_hash, parent.parent_index, semantic_child_idx, 0
                            )
                            chunk = Chunk(
                                chunk_id=chunk_id,
                                file_name=file_name,
                                file_hash=file_hash,
                                parent_index=parent.parent_index,
                                child_index=semantic_child_idx,
                                parent_type=parent.parent_type,
                                parent_title=parent.parent_title,
                                text=block_text,
                                enriched_text=enriched,
                                token_count=token_count,
                                is_split=False,
                                split_index=0,
                                paragraph_number=parent.paragraph_number,
                                kapittel=parent.kapittel,
                                law_short_name=law_short_name,
                                lovdata_url=lovdata_url,
                                is_amendment=is_amendment,
                                metadata=doc_metadata.to_dict(),
                                article_title=doc_metadata.tittel,
                            )
                            # 🔒 Strong text-level fingerprint dedup (NON-SPLIT CASE)
                            fingerprint = hashlib.sha256(
                                (file_hash + block_text.strip()).encode("utf-8")
                            ).hexdigest()

                            if fingerprint in seen_chunk_hashes:
                                continue

                            seen_chunk_hashes.add(fingerprint)
                            chunks.append(chunk)

                        else:
                            split_texts = self.text_splitter.split_text(block_text)
                            total_splits += len(split_texts) - 1

                            for split_idx, split_text in enumerate(split_texts):
                                split_token_count = self.token_counter.count_tokens(split_text)

                                # ✅ Each split still carries the parent context prefix
                                split_enriched = self.enricher.build_enriched_text(
                                    chunk_text=split_text,
                                    law_short_name=law_short_name,
                                    parent_title=parent.parent_title,
                                    paragraph_number=parent.paragraph_number,
                                    kapittel=parent.kapittel,
                                )

                                chunk_id = self.hasher.generate_chunk_id(
                                    file_hash, parent.parent_index, semantic_child_idx, split_idx
                                )
                                chunk = Chunk(
                                    chunk_id=chunk_id,
                                    file_name=file_name,
                                    file_hash=file_hash,
                                    parent_index=parent.parent_index,
                                    child_index=semantic_child_idx,
                                    parent_type=parent.parent_type,
                                    parent_title=parent.parent_title,
                                    text=split_text,
                                    enriched_text=split_enriched,
                                    token_count=split_token_count,
                                    is_split=True,
                                    split_index=split_idx,
                                    paragraph_number=parent.paragraph_number,
                                    kapittel=parent.kapittel,
                                    law_short_name=law_short_name,
                                    lovdata_url=lovdata_url,
                                    is_amendment=is_amendment,
                                    metadata=doc_metadata.to_dict(),
                                    article_title=doc_metadata.tittel,
                                )
                                # 🔒 Strong text-level fingerprint dedup (SPLIT CASE)
                                fingerprint = hashlib.sha256(
                                    (file_hash + split_text.strip()).encode("utf-8")
                                ).hexdigest()

                                if fingerprint in seen_chunk_hashes:
                                    continue

                                seen_chunk_hashes.add(fingerprint)
                                chunks.append(chunk)

            if total_splits > 0:
                logger.info(f"✂️  Split {total_splits} oversized chunks in {file_name}")

            # Fallback
            if not chunks and text.strip():
                logger.warning(f"No structured chunks found in {file_name}, creating fallback chunks")
                fallback_splits = self.text_splitter.split_text(text)
                for split_idx, split_text in enumerate(fallback_splits):
                    token_count = self.token_counter.count_tokens(split_text)
                    chunk_id = self.hasher.generate_chunk_id(file_hash, 0, 0, split_idx)
                    enriched = self.enricher.build_enriched_text(
                        chunk_text=split_text,
                        law_short_name=law_short_name,
                        parent_title="Full Document",
                        paragraph_number=None,
                        kapittel=None,
                    )
                    chunk = Chunk(
                        chunk_id=chunk_id,
                        file_name=file_name,
                        file_hash=file_hash,
                        parent_index=0,
                        child_index=0,
                        parent_type="fallback",
                        parent_title="Full Document",
                        text=split_text,
                        enriched_text=enriched,
                        token_count=token_count,
                        is_split=True,
                        split_index=split_idx,
                        law_short_name=law_short_name,
                        lovdata_url=lovdata_url,
                        is_amendment=is_amendment,
                        metadata=doc_metadata.to_dict(),
                        article_title=doc_metadata.tittel,
                    )
                    fingerprint = hashlib.sha256(
                    (file_hash + split_text.strip()).encode("utf-8")
                    ).hexdigest()

                    if fingerprint in seen_chunk_hashes:
                        continue

                    seen_chunk_hashes.add(fingerprint)
                    chunks.append(chunk)

            return doc_metadata, chunks

        except Exception as e:
            logger.error(f"Error chunking {file_name}: {e}")
            return DocumentMetadata(file_name=file_name, file_hash=""), []

    def log_file_summary(self, metadata: DocumentMetadata, chunks: List[Chunk]):
        stats = self.get_statistics(chunks)
        print(f"\n{'='*50}")
        print(f"📄 FILE: {metadata.file_name}")
        print(f"⚖️  Law: {metadata.law_short_name or 'unknown'} | Amendment: {metadata.is_amendment}")
        print(f"📊 Stats: {stats['total_chunks']} chunks | {stats['total_parents']} parents")
        print(f"✂️  Splits: {stats['split_chunks']} chunks were split")
        print(f"🧬 Hash: {metadata.file_hash[:16]}...")
        if chunks:
            print(f"📝 Enriched preview: {chunks[0].enriched_text[:150]}...")
        print("="*50 + "\n")

    def chunk_file(self, file_path: str) -> Tuple[DocumentMetadata, List[Chunk]]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            return self.chunk_text(text, os.path.basename(file_path))
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    text = f.read()
                return self.chunk_text(text, os.path.basename(file_path))
            except Exception as e:
                logger.error(f"Error reading {file_path} with latin-1: {e}")
                return DocumentMetadata(file_name=os.path.basename(file_path), file_hash=""), []
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return DocumentMetadata(file_name=os.path.basename(file_path), file_hash=""), []

    def chunk_directory(self, directory: str, limit: int = None) -> Dict[str, Tuple[DocumentMetadata, List[Chunk]]]:
        try:
            txt_files = list(Path(directory).glob("*.txt"))
            if not txt_files:
                logger.warning(f"No TXT files found in {directory}")
                return {}
            if limit:
                txt_files = txt_files[:limit]
            results = {}
            total = len(txt_files)
            logger.info(f"Starting to process {total} Norwegian legal files...")
            for idx, txt_file in enumerate(txt_files, 1):
                try:
                    metadata, chunks = self.chunk_file(str(txt_file))
                    if chunks:
                        results[txt_file.name] = (metadata, chunks)
                        self.success_files.append(txt_file.name)
                        split_count = sum(1 for c in chunks if c.is_split)
                        logger.info(
                            f"[{idx}/{total}] ✅ {txt_file.name}: "
                            f"{len(chunks)} chunks ({split_count} split) "
                            f"| law={metadata.law_short_name} | amendment={metadata.is_amendment}"
                        )
                    else:
                        self.error_files.append((txt_file.name, "No chunks created"))
                        logger.warning(f"[{idx}/{total}] ⚠️  {txt_file.name}: No chunks created")
                except Exception as e:
                    self.error_files.append((txt_file.name, str(e)))
                    logger.error(f"[{idx}/{total}] ❌ {txt_file.name}: {e}")
            self.print_summary(total)
            return results
        except Exception as e:
            logger.error(f"Error processing directory {directory}: {e}")
            return {}

    def print_summary(self, total: int):
        print("\n" + "="*70)
        print("NORWEGIAN LOVDATA PROCESSING SUMMARY v2")
        print("="*70)
        print(f"Total files: {total}")
        print(f"✅ Successful: {len(self.success_files)}")
        print(f"❌ Errors: {len(self.error_files)}")
        if self.error_files:
            print("\n" + "-"*70)
            print("FILES WITH ERRORS:")
            for file_name, error in self.error_files[:10]:
                print(f"  • {file_name}: {error[:50]}")
            if len(self.error_files) > 10:
                print(f"  ... and {len(self.error_files) - 10} more")
        print("="*70 + "\n")

    def get_statistics(self, chunks: List[Chunk]) -> Dict:
        try:
            if not chunks:
                return {"total_chunks": 0, "parent_types": {}, "avg_chunk_length": 0,
                        "avg_token_count": 0, "total_parents": 0, "split_chunks": 0}
            parent_types = {}
            for chunk in chunks:
                parent_types[chunk.parent_type] = parent_types.get(chunk.parent_type, 0) + 1
            chunk_lengths = [len(chunk.text) for chunk in chunks]
            token_counts = [chunk.token_count for chunk in chunks]
            unique_parents = len(set(chunk.parent_index for chunk in chunks))
            split_chunks = sum(1 for chunk in chunks if chunk.is_split)
            return {
                "total_chunks": len(chunks),
                "parent_types": parent_types,
                "avg_chunk_length": sum(chunk_lengths) / len(chunks),
                "avg_token_count": sum(token_counts) / len(chunks),
                "total_parents": unique_parents,
                "min_chunk_length": min(chunk_lengths),
                "max_chunk_length": max(chunk_lengths),
                "min_token_count": min(token_counts),
                "max_token_count": max(token_counts),
                "split_chunks": split_chunks
            }
        except Exception as e:
            logger.error(f"Error calculating statistics: {e}")
            return {"error": str(e)}


# ============================================================================
# RETRIEVAL SIDE: Amendment Filter (add to your retrieval_evaluator)
# ============================================================================

def filter_amendment_results(results: List[Dict], allowed_laws: List[str] = None) -> List[Dict]:
    """
    ✅ POST-RETRIEVAL FILTER: Use this in retrieval_evaluator.py
    
    Deprioritize amendment laws (LTI) when primary laws are available.
    Optionally filter by allowed_laws list.

    Usage in retrieval_evaluator:
        results = filter_amendment_results(raw_results, allowed_laws=["merverdiavgiftsloven"])
    """
    if allowed_laws:
        # Keep only chunks whose law_short_name matches allowed_laws
        filtered = [r for r in results if r.get("law_short_name") in allowed_laws]
        if filtered:
            return filtered
        # Fallback: if no match, return non-amendment results
        return [r for r in results if not r.get("is_amendment", False)]

    # No filter: just deprioritize amendments
    primary = [r for r in results if not r.get("is_amendment", False)]
    amendments = [r for r in results if r.get("is_amendment", False)]
    return primary + amendments


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys

    chunker = NorwegianLovdataChunker(max_tokens=400, overlap_tokens=50)

    if len(sys.argv) > 1:
        path = sys.argv[1]

        if os.path.isdir(path):
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
            print(f"\n🔄 Processing Norwegian legal directory: {path}")
            results = chunker.chunk_directory(path, limit=limit)

            if results:
                first_file = list(results.keys())[0]
                metadata, chunks = results[first_file]
                chunker.log_file_summary(metadata, chunks)

                stats = chunker.get_statistics(chunks)
                print(f"Parent Types: {stats['parent_types']}")
                print(f"Avg Token Count: {stats['avg_token_count']:.0f}")

                print(f"\nFirst 3 Chunks (enriched_text for embedding):")
                for i, chunk in enumerate(chunks[:3], 1):
                    print(f"\n--- Chunk {i} ---")
                    print(f"  law: {chunk.law_short_name} | amendment: {chunk.is_amendment}")
                    print(f"  paragraph: {chunk.paragraph_number} | kapittel: {chunk.kapittel}")
                    print(f"  enriched_text: {chunk.enriched_text[:200]}...")
        else:
            metadata, chunks = chunker.chunk_file(path)
            chunker.log_file_summary(metadata, chunks)
            stats = chunker.get_statistics(chunks)
            print(f"Total Chunks: {stats['total_chunks']} | Splits: {stats['split_chunks']}")
            print(f"Law: {metadata.law_short_name} | Amendment: {metadata.is_amendment}")
            if chunks:
                print(f"\nFirst 3 Chunks:")
                for i, chunk in enumerate(chunks[:3], 1):
                    print(f"\n--- Chunk {i} ---")
                    print(f"  enriched: {chunk.enriched_text[:200]}...")
    else:
        print("Usage:")
        print("  Single file:  python chunker_token_based_v2.py <file.txt>")
        print("  Directory:    python chunker_token_based_v2.py <directory> [limit]")