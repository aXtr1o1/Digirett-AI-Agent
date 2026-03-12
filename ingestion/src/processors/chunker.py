"""
processors/chunker.py
======================
Norwegian Lovdata Hierarchical Chunking System — section-first strategy.

Chunking rules (from spec):
  1. Default unit  = one § (section), including its heading + all ledd.
  2. Sub-split by ledd only when § exceeds max tokens OR contains multiple
     logically independent rules.
  3. Never split a rule from its exception / enumeration mid-sentence.
  4. Keep rule + exceptions in the same chunk.
  5. Target: 800-2 000 tokens | Min: 200 | Max: ~10 000 chars.
  6. One chunk = one subdomain (no multi-domain tagging per chunk).

Metadata stored per chunk:
  statute_id, domain_name, sub_domain_name, jurisdiction, source_type,
  tier, paragraph_number, kapittel, law_short_name
"""

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logging.warning("tiktoken not available — falling back to character-based estimation")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token counter
# ---------------------------------------------------------------------------

class TokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        if _TIKTOKEN_AVAILABLE:
            try:
                self.encoding = tiktoken.get_encoding(encoding_name)
                self.method   = "tiktoken"
                logger.info(f"Token counter initialised with {encoding_name}")
            except Exception as exc:
                logger.warning(f"Failed to load tiktoken encoding: {exc}")
                self.encoding = None
                self.method   = "estimate"
        else:
            self.encoding = None
            self.method   = "estimate"

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if self.method == "tiktoken" and self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception:
                return self._estimate(text)
        return self._estimate(text)

    @staticmethod
    def _estimate(text: str) -> int:
        return len(text) // 4


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DocumentMetadata:
    file_name:       str
    file_hash:       str
    datokode:        Optional[str] = None
    dokument_id:     Optional[str] = None
    departement:     Optional[str] = None
    tittel:          Optional[str] = None
    korttittel:      Optional[str] = None
    year:            Optional[int] = None
    i_kraft_fra:     Optional[str] = None
    rettsomrade:     Optional[str] = None
    publisert_i:     Optional[str] = None
    kunngjort:       Optional[str] = None
    lovdata_url:     Optional[str] = None
    law_short_name:  Optional[str] = None
    is_amendment:    bool          = False
    tags:            List[str]     = field(default_factory=list)
    statute_id:      Optional[str] = None
    tier:            Optional[str] = None
    source_type:     Optional[str] = None
    domain_name:     Optional[str] = None
    sub_domain_name: Optional[str] = None
    jurisdiction:    Optional[str] = None

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Chunk:
    chunk_id:         str
    file_name:        str
    file_hash:        str
    parent_index:     int
    child_index:      int
    parent_type:      str
    parent_title:     str
    text:             str
    enriched_text:    str           = ""
    token_count:      int           = 0
    is_split:         bool          = False
    split_index:      int           = 0
    paragraph_number: Optional[str] = None
    kapittel:         Optional[str] = None
    law_short_name:   Optional[str] = None
    lovdata_url:      Optional[str] = None
    is_amendment:     bool          = False
    metadata:         Optional[Dict] = None
    article_title:    Optional[str] = None

    def to_dict(self) -> Dict:
        result = {
            "chunk_id":         self.chunk_id,
            "chunk_index":      self.child_index,
            "file_name":        self.file_name,
            "file_hash":        self.file_hash,
            "parent_index":     self.parent_index,
            "child_index":      self.child_index,
            "parent_type":      self.parent_type,
            "parent_title":     self.parent_title,
            "text":             self.text,
            "enriched_text":    self.enriched_text,
            "token_count":      self.token_count,
            "is_split":         self.is_split,
            "split_index":      self.split_index,
            "paragraph_number": self.paragraph_number,
            "kapittel":         self.kapittel,
            "law_short_name":   self.law_short_name,
            "lovdata_url":      self.lovdata_url,
            "is_amendment":     self.is_amendment,
            "article_title":    self.article_title,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


# ---------------------------------------------------------------------------
# Law name & URL mapper
# ---------------------------------------------------------------------------

class LawNameMapper:
    """Maps file stems / korttittel to canonical law names and Lovdata URLs."""

    _FILE_MAP: Dict[str, Tuple[str, str]] = {
        "nl-19970613-0044": ("aksjeloven",             "https://lovdata.no/lov/1997-06-13-44"),
        "nl-19970613-0045": ("allmennaksjeloven",       "https://lovdata.no/lov/1997-06-13-45"),
        "nl-19850621-0080": ("prokuraloven",            "https://lovdata.no/lov/1985-06-21-80"),
        "nl-19850621-0078": ("foretaksregisterloven",   "https://lovdata.no/lov/1985-06-21-78"),
        "nl-19850621-0083": ("selskapsloven",           "https://lovdata.no/lov/1985-06-21-83"),
        "nl-19980717-0056": ("regnskapsloven",          "https://lovdata.no/lov/1998-07-17-56"),
        "nl-20041119-0073": ("bokføringsloven",         "https://lovdata.no/lov/2004-11-19-73"),
        "nl-20201120-0128": ("revisorloven",            "https://lovdata.no/lov/2020-11-20-128"),
        "nl-20160527-0014": ("skatteforvaltningsloven", "https://lovdata.no/lov/2016-05-27-14"),
        "nl-19990326-0014": ("skatteloven",             "https://lovdata.no/lov/1999-03-26-14"),
        "nl-20090619-0058": ("merverdiavgiftsloven",    "https://lovdata.no/lov/2009-06-19-58"),
        "nl-19840608-0058": ("konkursloven",            "https://lovdata.no/lov/1984-06-08-58"),
        "nl-19840608-0059": ("dekningsloven",           "https://lovdata.no/lov/1984-06-08-59"),
        "nl-19800208-0002": ("panteloven",              "https://lovdata.no/lov/1980-02-08-2"),
        "nl-20050617-0062": ("arbeidsmiljøloven",       "https://lovdata.no/lov/2005-06-17-62"),
        "nl-19990326-0017": ("husleieloven",            "https://lovdata.no/lov/1999-03-26-17"),
        "nl-20050520-0028": ("straffeloven",            "https://lovdata.no/lov/2005-05-20-28"),
        "nl-20050617-0090": ("tvisteloven",             "https://lovdata.no/lov/2005-06-17-90"),
        "nl-20180601-0024": ("personopplysningsloven",  "https://lovdata.no/lov/2018-06-01-24"),
        "nl-20190301-0002": ("åpenhetsloven",           "https://lovdata.no/lov/2019-03-01-2"),
    }

    _KORTTITTEL_MAP: Dict[str, Tuple[str, str]] = {
        "aksjeloven":             ("aksjeloven",             "https://lovdata.no/lov/1997-06-13-44"),
        "allmennaksjeloven":      ("allmennaksjeloven",      "https://lovdata.no/lov/1997-06-13-45"),
        "merverdiavgiftsloven":   ("merverdiavgiftsloven",   "https://lovdata.no/lov/2009-06-19-58"),
        "skatteforvaltningsloven":("skatteforvaltningsloven","https://lovdata.no/lov/2016-05-27-14"),
        "skatteloven":            ("skatteloven",            "https://lovdata.no/lov/1999-03-26-14"),
        "arbeidsmiljøloven":      ("arbeidsmiljøloven",      "https://lovdata.no/lov/2005-06-17-62"),
        "regnskapsloven":         ("regnskapsloven",         "https://lovdata.no/lov/1998-07-17-56"),
        "bokføringsloven":        ("bokføringsloven",        "https://lovdata.no/lov/2004-11-19-73"),
        "foretaksregisterloven":  ("foretaksregisterloven",  "https://lovdata.no/lov/1985-06-21-78"),
        "selskapsloven":          ("selskapsloven",          "https://lovdata.no/lov/1985-06-21-83"),
        "prokuraloven":           ("prokuraloven",           "https://lovdata.no/lov/1985-06-21-80"),
        "revisorloven":           ("revisorloven",           "https://lovdata.no/lov/2020-11-20-128"),
        "panteloven":             ("panteloven",             "https://lovdata.no/lov/1980-02-08-2"),
        "konkursloven":           ("konkursloven",           "https://lovdata.no/lov/1984-06-08-58"),
        "dekningsloven":          ("dekningsloven",          "https://lovdata.no/lov/1984-06-08-59"),
        "husleieloven":           ("husleieloven",           "https://lovdata.no/lov/1999-03-26-17"),
        "tvisteloven":            ("tvisteloven",            "https://lovdata.no/lov/2005-06-17-90"),
        "straffeloven":           ("straffeloven",           "https://lovdata.no/lov/2005-05-20-28"),
        "personopplysningsloven": ("personopplysningsloven", "https://lovdata.no/lov/2018-06-01-24"),
        "åpenhetsloven":          ("åpenhetsloven",          "https://lovdata.no/lov/2019-03-01-2"),
    }

    @classmethod
    def resolve(
        cls,
        file_name:  str,
        korttittel: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str], bool]:
        """Returns (law_short_name, lovdata_url, is_amendment)."""
        stem         = file_name.lower().replace(".txt", "").replace(".xml", "")
        is_amendment = "lti" in stem or stem.startswith("lti-")

        for prefix, (name, url) in cls._FILE_MAP.items():
            if stem == prefix.lower() or stem.startswith(prefix.lower()):
                return name, url, is_amendment

        if korttittel:
            kt = korttittel.lower().strip()
            if kt in cls._KORTTITTEL_MAP:
                name, url = cls._KORTTITTEL_MAP[kt]
                return name, url, is_amendment

        return None, None, is_amendment


# ---------------------------------------------------------------------------
# Contextual enricher
# ---------------------------------------------------------------------------

class ChunkEnricher:
    """Prepends law name + paragraph context to the text before embedding."""

    @staticmethod
    def build_enriched_text(
        chunk_text:     str,
        law_short_name: Optional[str],
        parent_title:   str,
        paragraph_number: Optional[str],
        kapittel:       Optional[str],
    ) -> str:
        parts = []
        if law_short_name:
            parts.append(f"[Lov: {law_short_name}]")
        if kapittel and kapittel.lower() not in parent_title.lower():
            parts.append(f"[{kapittel}]")
        if parent_title:
            parts.append(f"[{parent_title}]")
        prefix = " ".join(parts)
        return f"{prefix} {chunk_text}" if prefix else chunk_text


# ---------------------------------------------------------------------------
# Norwegian text parser
# ---------------------------------------------------------------------------

class NorwegianLovdataParser:

    _METADATA_FIELDS = {
        "datokode":    r'^\s*[-•]?\s*Datokode\s*[:\-]\s*(.+)$',
        "dokument_id": r'^\s*[-•]?\s*DokumentID\s*[:\-]\s*(.+)$',
        "departement": r'^\s*[-•]?\s*Departement\s*[:\-]\s*(.+)$',
        "tittel":      r'^\s*[-•]?\s*Tittel\s*[:\-]\s*(.+)$',
        "korttittel":  r'^\s*[-•]?\s*Korttittel\s*[:\-]\s*(.+)$',
        "i_kraft_fra": r'^\s*[-•]?\s*I kraft fra\s*[:\-]\s*(.+)$',
        "rettsomrade": r'^\s*[-•]?\s*Rettsområde\s*[:\-]\s*(.+)$',
        "publisert_i": r'^\s*[-•]?\s*Publisert i\s*[:\-]\s*(.+)$',
        "kunngjort":   r'^\s*[-•]?\s*Kunngjort\s*[:\-]\s*(.+)$',
        "year":        r'^\s*YEAR:\s*(\d{4})\s*$',
    }

    SEPARATOR_PATTERN      = re.compile(r'^-{3,}$')
    PARAGRAPH_PATTERN      = re.compile(
        r'^(§\s*\d+[a-z]?(?:[-–]\d+)?[a-z]?\.?)\s*(.*)$', re.IGNORECASE
    )
    LEDD_PATTERN           = re.compile(r'^\((\d+)\)\s+(.+)$')
    SECTION_BOUNDARY_TYPES = frozenset({"paragraph", "kapittel", "del", "avdeling", "artikkel"})

    NORWEGIAN_PATTERNS = {
        "paragraph":      PARAGRAPH_PATTERN,
        "kapittel":       re.compile(r'^(Kapittel|Kap\.?)\s+([IVXLCDM\d]+)\.?\s*(.*)$', re.IGNORECASE),
        "del":            re.compile(r'^Del\s+([IVXLCDM\d]+)\.?\s*(.*)$',               re.IGNORECASE),
        "avdeling":       re.compile(r'^Avdeling\s+([IVXLCDM\d]+)\.?\s*(.*)$',          re.IGNORECASE),
        "artikkel":       re.compile(r'^(\d+)\s*(Art\.|Artikkel)\.?\s*(.*)$',            re.IGNORECASE),
        "numbered_paren": LEDD_PATTERN,
        "lettered":       re.compile(r'^([a-z])\)\s+(.+)$',                              re.IGNORECASE),
    }

    _AMENDMENT_PATTERNS = [
        re.compile(r'skal lyde\s*:', re.IGNORECASE),
        re.compile(r'ny\s+§',        re.IGNORECASE),
        re.compile(r'oppheves',      re.IGNORECASE),
        re.compile(r'endres til',    re.IGNORECASE),
        re.compile(r'tilføyes',      re.IGNORECASE),
    ]

    @classmethod
    def is_separator(cls, line: str) -> bool:
        return cls.SEPARATOR_PATTERN.match(line.strip()) is not None

    @classmethod
    def is_metadata_line(cls, line: str) -> bool:
        if not line or len(line) > 300:
            return False
        for pattern in cls._METADATA_FIELDS.values():
            if re.match(pattern, line, re.IGNORECASE):
                return True
        if line.strip().startswith(("-", "•")):
            if ":" in line and len(line) < 200:
                return True
        if re.match(r'^\s*[-•]?\s*Innhold\s*$', line, re.IGNORECASE):
            return True
        return False

    @classmethod
    def classify_line(cls, line: str) -> Optional[Tuple[str, str]]:
        """Returns (type, title) or None for non-structural lines."""
        if len(line) > 300:
            return None
        stripped = line.strip()
        for pat in cls._AMENDMENT_PATTERNS:
            if pat.search(stripped):
                return None
        for ptype, pattern in cls.NORWEGIAN_PATTERNS.items():
            if pattern.match(stripped):
                return ptype, stripped
        return None

    @staticmethod
    def extract_paragraph_number(line: str) -> Optional[str]:
        m = re.match(r'^(§\s*[\d]+[a-z]?(?:-\d+)?)', line.strip(), re.IGNORECASE)
        return m.group(1).strip() if m else None

    @classmethod
    def parse_metadata(cls, lines: List[str]) -> "DocumentMetadata":
        metadata      = {}
        separator_idx = None

        for i, line in enumerate(lines[:100]):
            if cls.is_separator(line):
                separator_idx = i
                break

        if separator_idx:
            for line in lines[:separator_idx]:
                for field_name, pattern in cls._METADATA_FIELDS.items():
                    m = re.match(pattern, line, re.IGNORECASE)
                    if m:
                        metadata[field_name] = m.group(1).strip()
                        break

        year = None
        if "year" in metadata:
            try:
                year = int(metadata["year"])
            except Exception:
                pass
        if not year and "datokode" in metadata:
            ym = re.search(r'(\d{4})', metadata["datokode"])
            if ym:
                year = int(ym.group(1))

        return DocumentMetadata(
            file_name="", file_hash="",
            datokode=metadata.get("datokode"),
            dokument_id=metadata.get("dokument_id"),
            departement=metadata.get("departement"),
            tittel=metadata.get("tittel"),
            korttittel=metadata.get("korttittel"),
            year=year,
            i_kraft_fra=metadata.get("i_kraft_fra"),
            rettsomrade=metadata.get("rettsomrade"),
            publisert_i=metadata.get("publisert_i"),
            kunngjort=metadata.get("kunngjort"),
        )


# ---------------------------------------------------------------------------
# Section model
# ---------------------------------------------------------------------------

@dataclass
class LegalSection:
    """One § (or chapter/del heading) with all its ledd collected."""

    section_title:    str
    section_type:     str
    paragraph_number: Optional[str]
    kapittel:         Optional[str]
    parent_index:     int
    lines:            List[str] = field(default_factory=list)

    def full_text(self) -> str:
        return "\n".join([self.section_title] + self.lines)

    def char_count(self) -> int:
        return len(self.full_text())


# ---------------------------------------------------------------------------
# Section-first parser
# ---------------------------------------------------------------------------

class SectionFirstParser:
    """Parses a document into LegalSection objects — one per §."""

    def __init__(self) -> None:
        self._parser = NorwegianLovdataParser()

    def parse(
        self, lines: List[str]
    ) -> Tuple[DocumentMetadata, List[LegalSection]]:

        doc_metadata = self._parser.parse_metadata(lines)

        content_start = 0
        for i, line in enumerate(lines):
            if self._parser.is_separator(line):
                content_start = i + 1
                break

        sections:         List[LegalSection]    = []
        current_section:  Optional[LegalSection] = None
        current_kapittel: Optional[str]          = None
        parent_index      = 0
        in_innhold        = False

        for raw_line in lines[content_start:]:
            line = raw_line.strip()
            if len(line) < 2:
                continue

            if re.match(r'^\s*[-•]?\s*Innhold\s*$', line, re.IGNORECASE):
                in_innhold = True
                continue
            if in_innhold:
                if self._parser.is_separator(line):
                    in_innhold = False
                continue

            classified = self._parser.classify_line(line)

            if classified is not None:
                ptype, ptitle = classified

                # Ledd / enumeration lines → content, not a new section boundary
                if ptype not in NorwegianLovdataParser.SECTION_BOUNDARY_TYPES:
                    if current_section is not None:
                        current_section.lines.append(line)
                    continue

                # Kapittel is context only — does not start a new section
                if ptype == "kapittel":
                    current_kapittel = ptitle
                    continue

                # § or del/avdeling → flush and start new section
                para_num = (
                    self._parser.extract_paragraph_number(line)
                    if ptype == "paragraph"
                    else None
                )
                if current_section is not None:
                    sections.append(current_section)
                current_section = LegalSection(
                    section_title=ptitle,
                    section_type=ptype,
                    paragraph_number=para_num,
                    kapittel=current_kapittel,
                    parent_index=parent_index,
                )
                parent_index += 1

            else:
                # Plain content line
                if current_section is not None and line:
                    current_section.lines.append(line)
                elif line and not self._parser.is_metadata_line(line):
                    if current_section is None:
                        current_section = LegalSection(
                            section_title="Innledning",
                            section_type="preamble",
                            paragraph_number=None,
                            kapittel=None,
                            parent_index=parent_index,
                        )
                        parent_index += 1
                    current_section.lines.append(line)

        if current_section is not None:
            sections.append(current_section)

        return doc_metadata, sections


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------

class SectionSplitter:
    """
    Splits a LegalSection into chunks according to spec constraints.

    - Default: whole § = one chunk.
    - Sub-split only when § exceeds MAX_TOKENS / MAX_CHARS.
    - Sub-split order: ledd → enumeration → sentences.
    - Never splits mid-sentence.
    """

    MAX_CHARS      = 10_000
    MAX_TOKENS     = 2_000
    MIN_TOKENS     = 200
    EMBED_HARD_CAP = 8_000

    def __init__(self, token_counter: Optional[TokenCounter] = None) -> None:
        self.tc = token_counter or TokenCounter()

    def split(self, section: LegalSection) -> List[str]:
        full   = section.full_text()
        tokens = self.tc.count_tokens(full)
        chars  = len(full)

        if tokens <= self.MAX_TOKENS and chars <= self.MAX_CHARS:
            return [full]

        ledd_blocks = self._split_by_ledd(section)
        if len(ledd_blocks) > 1:
            return self._enforce_hard_cap(
                self._merge_short_blocks(ledd_blocks)
            )

        enum_blocks = self._split_by_enumeration(full)
        if len(enum_blocks) > 1:
            return self._enforce_hard_cap(
                self._merge_short_blocks(enum_blocks)
            )

        return self._enforce_hard_cap(self._split_by_sentences(full))

    def _enforce_hard_cap(self, blocks: List[str]) -> List[str]:
        result = []
        for block in blocks:
            if self.tc.count_tokens(block) <= self.EMBED_HARD_CAP:
                result.append(block)
                continue
            words = block.split()
            current_words: List[str] = []
            current_tokens = 0
            for word in words:
                w_tokens = self.tc.count_tokens(word)
                if current_tokens + w_tokens > self.EMBED_HARD_CAP and current_words:
                    result.append(" ".join(current_words))
                    current_words  = [word]
                    current_tokens = w_tokens
                else:
                    current_words.append(word)
                    current_tokens += w_tokens
            if current_words:
                result.append(" ".join(current_words))
        return result

    def _split_by_ledd(self, section: LegalSection) -> List[str]:
        if not section.lines:
            return [section.full_text()]
        groups: List[List[str]] = []
        current: List[str]      = [section.section_title]
        for line in section.lines:
            if re.match(r'^\(\d+\)\s+', line):
                if current:
                    groups.append(current)
                current = [line]
            else:
                current.append(line)
        if current:
            groups.append(current)
        return ["\n".join(g) for g in groups if g]

    def _split_by_enumeration(self, text: str) -> List[str]:
        pattern = r'(?=\b[a-z]\)\s|\bførste punktum\b|\bannet punktum\b)'
        parts   = re.split(pattern, text)
        return [p.strip() for p in parts if p.strip()]

    def _split_by_sentences(self, text: str) -> List[str]:
        sentences = re.split(r'(?<=\.)\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        blocks: List[str] = []
        current_parts: List[str] = []
        current_tokens = 0
        for s in sentences:
            s_tokens = self.tc.count_tokens(s)
            if current_tokens + s_tokens > self.MAX_TOKENS and current_parts:
                blocks.append(" ".join(current_parts))
                current_parts  = [s]
                current_tokens = s_tokens
            else:
                current_parts.append(s)
                current_tokens += s_tokens
        if current_parts:
            blocks.append(" ".join(current_parts))
        return self._enforce_hard_cap(blocks) if blocks else [text]

    def _merge_short_blocks(self, blocks: List[str]) -> List[str]:
        merged: List[str] = []
        buffer = ""
        buffer_tokens = 0
        for block in blocks:
            block_tokens = self.tc.count_tokens(block)
            if buffer_tokens + block_tokens <= self.MAX_TOKENS:
                buffer        = (buffer + "\n" + block).strip() if buffer else block
                buffer_tokens += block_tokens
            else:
                if buffer:
                    merged.append(buffer)
                buffer        = block
                buffer_tokens = block_tokens
        if buffer:
            merged.append(buffer)
        return merged if merged else blocks


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class FileHasher:
    @staticmethod
    def hash_file(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_chunk_id(file_hash: str, parent_idx: int, split_idx: int = 0) -> str:
        seed = f"{file_hash}_{parent_idx:04d}_{split_idx:04d}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


# ---------------------------------------------------------------------------
# Main chunker
# ---------------------------------------------------------------------------

class NorwegianLovdataChunker:
    """
    Section-first chunker.
    Parses the document into LegalSection objects (one per §),
    sub-splits only when § exceeds MAX_TOKENS / MAX_CHARS, and
    attaches all citation metadata per chunk.

    domain_name / sub_domain_name / jurisdiction are set by orchestrator.py
    from the XL map, not here.
    """

    def __init__(
        self,
        max_tokens:     int = 2_000,
        overlap_tokens: int = 0,
    ) -> None:
        self.hasher      = FileHasher()
        self.tc          = TokenCounter()
        self.enricher    = ChunkEnricher()
        self.law_mapper  = LawNameMapper()
        self.sec_parser  = SectionFirstParser()
        self.splitter    = SectionSplitter(token_counter=self.tc)
        self.max_tokens  = max_tokens
        logger.info(f"Section-first chunker initialised | max_tokens={max_tokens}")

    def chunk_text(
        self,
        text:          str,
        file_name:     str,
        article_title: Optional[str] = None,
    ) -> Tuple[DocumentMetadata, List[Chunk]]:
        try:
            file_hash = self.hasher.hash_file(text)
            lines     = [l.strip() for l in text.splitlines() if l.strip()]

            doc_metadata, sections = self.sec_parser.parse(lines)
            doc_metadata.file_name = file_name
            doc_metadata.file_hash = file_hash
            if article_title:
                doc_metadata.tittel = article_title

            law_short_name, lovdata_url, is_amendment = self.law_mapper.resolve(
                file_name, korttittel=doc_metadata.korttittel
            )
            doc_metadata.law_short_name = law_short_name
            doc_metadata.lovdata_url    = lovdata_url
            doc_metadata.is_amendment   = is_amendment

            chunks:   List[Chunk] = []
            seen_ids: set         = set()

            for section in sections:
                blocks   = self.splitter.split(section)
                is_split = len(blocks) > 1

                for split_idx, block_text in enumerate(blocks):
                    block_text = block_text.strip()
                    if not block_text:
                        continue

                    enriched = self.enricher.build_enriched_text(
                        chunk_text=block_text,
                        law_short_name=law_short_name,
                        parent_title=section.section_title,
                        paragraph_number=section.paragraph_number,
                        kapittel=section.kapittel,
                    )

                    chunk_id = self.hasher.generate_chunk_id(
                        file_hash, section.parent_index, split_idx
                    )
                    if chunk_id in seen_ids:
                        continue
                    seen_ids.add(chunk_id)

                    token_count = self.tc.count_tokens(enriched)

                    # Enforce embedding API hard cap
                    if token_count > SectionSplitter.EMBED_HARD_CAP:
                        logger.warning(
                            f"Enriched text exceeds EMBED_HARD_CAP: "
                            f"{token_count} > {SectionSplitter.EMBED_HARD_CAP} "
                            f"({file_name} | {section.section_title}) — hard split applied"
                        )
                        for enforced_idx, enforced_text in enumerate(
                            self.splitter._enforce_hard_cap([enriched])
                        ):
                            enforced_text = (enforced_text or "").strip()
                            if not enforced_text:
                                continue
                            cid = self.hasher.generate_chunk_id(
                                file_hash,
                                section.parent_index,
                                split_idx * 100 + enforced_idx,
                            )
                            if cid in seen_ids:
                                continue
                            seen_ids.add(cid)
                            chunks.append(Chunk(
                                chunk_id=cid,
                                file_name=file_name,
                                file_hash=file_hash,
                                parent_index=section.parent_index,
                                child_index=split_idx * 100 + enforced_idx,
                                parent_type=section.section_type,
                                parent_title=section.section_title,
                                text=block_text,
                                enriched_text=enforced_text,
                                token_count=self.tc.count_tokens(enforced_text),
                                is_split=True,
                                split_index=split_idx,
                                paragraph_number=section.paragraph_number,
                                kapittel=section.kapittel,
                                law_short_name=law_short_name,
                                lovdata_url=lovdata_url,
                                is_amendment=is_amendment,
                                metadata=doc_metadata.to_dict(),
                                article_title=doc_metadata.tittel,
                            ))
                        continue

                    chunks.append(Chunk(
                        chunk_id=chunk_id,
                        file_name=file_name,
                        file_hash=file_hash,
                        parent_index=section.parent_index,
                        child_index=split_idx,
                        parent_type=section.section_type,
                        parent_title=section.section_title,
                        text=block_text,
                        enriched_text=enriched,
                        token_count=token_count,
                        is_split=is_split,
                        split_index=split_idx,
                        paragraph_number=section.paragraph_number,
                        kapittel=section.kapittel,
                        law_short_name=law_short_name,
                        lovdata_url=lovdata_url,
                        is_amendment=is_amendment,
                        metadata=doc_metadata.to_dict(),
                        article_title=doc_metadata.tittel,
                    ))

                    logger.info(
                        f"CHUNK | "
                        f"§={section.paragraph_number or section.section_title[:30]!r} | "
                        f"law={law_short_name} | tokens={token_count} | "
                        f"split={is_split}({split_idx + 1}/{len(blocks)})"
                    )

            # Fallback — if parsing produced nothing
            if not chunks:
                logger.warning(f"No sections parsed for {file_name} — creating fallback chunk")
                fallback_text = text[:10_000]
                enriched = self.enricher.build_enriched_text(
                    chunk_text=fallback_text,
                    law_short_name=law_short_name,
                    parent_title="Document",
                    paragraph_number=None,
                    kapittel=None,
                )
                cid = self.hasher.generate_chunk_id(file_hash, 0, 0)
                chunks.append(Chunk(
                    chunk_id=cid,
                    file_name=file_name,
                    file_hash=file_hash,
                    parent_index=0,
                    child_index=0,
                    parent_type="fallback",
                    parent_title="Document",
                    text=fallback_text,
                    enriched_text=enriched,
                    token_count=self.tc.count_tokens(enriched),
                    is_split=False,
                    split_index=0,
                    law_short_name=law_short_name,
                    lovdata_url=lovdata_url,
                    is_amendment=is_amendment,
                    metadata=doc_metadata.to_dict(),
                    article_title=doc_metadata.tittel,
                ))

            return doc_metadata, chunks

        except Exception as exc:
            logger.error(f"Chunking failed for {file_name}: {exc}", exc_info=True)
            return DocumentMetadata(file_name=file_name, file_hash=""), []

    def get_statistics(self, chunks: List[Chunk]) -> Dict:
        if not chunks:
            return {"total_chunks": 0}
        token_counts   = [c.token_count for c in chunks]
        unique_parents = len(set(c.parent_index for c in chunks))
        split_chunks   = sum(1 for c in chunks if c.is_split)
        return {
            "total_chunks":   len(chunks),
            "total_sections": unique_parents,
            "split_chunks":   split_chunks,
            "avg_tokens":     sum(token_counts) / len(token_counts),
            "min_tokens":     min(token_counts),
            "max_tokens":     max(token_counts),
            "parent_types":   {
                pt: sum(1 for c in chunks if c.parent_type == pt)
                for pt in set(c.parent_type for c in chunks)
            },
        }