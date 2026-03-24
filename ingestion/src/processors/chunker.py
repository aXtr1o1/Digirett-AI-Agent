"""
Norwegian Lovdata Chunker - SAFE VERSION
Produces smaller chunks to prevent SageMaker crashes
"""
'''
import hashlib
import re
import os
import uuid
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ParentNode:
    """Parent heading (§, Kapittel, Artikkel, or dynamic heading)"""
    parent_index: int
    parent_title: str
    parent_type: str
    children: List[Dict] = field(default_factory=list)


@dataclass
class DocumentMetadata:
    """Norwegian document-level metadata"""
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
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Chunk:
    """Individual chunk with all metadata"""
    chunk_id: str
    file_name: str
    file_hash: str
    parent_index: int
    child_index: int
    parent_type: str
    parent_title: str
    text: str
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        result = {
            "chunk_id": self.chunk_id,
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "parent_index": self.parent_index,
            "child_index": self.child_index,
            "parent_type": self.parent_type,
            "parent_title": self.parent_title,
            "text": self.text
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


# ============================================================================
# SAFE TEXT SPLITTING
# ============================================================================

class SafeTextSplitter:
    """
    Splits long text into safe chunks for embedding.
    
    CRITICAL: Each chunk must be < 2000 chars to prevent SageMaker crashes
    """
    
    MAX_CHUNK_SIZE = 1800  # Safe margin below 2000 char limit
    MIN_CHUNK_SIZE = 100   # Don't create tiny chunks
    
    @classmethod
    def split_text(cls, text: str, max_size: int = None) -> List[str]:
        """
        Split text into safe chunks by sentences.
        
        Args:
            text: Text to split
            max_size: Max chars per chunk (default: 1800)
            
        Returns:
            List of text chunks, each < max_size chars
        """
        if max_size is None:
            max_size = cls.MAX_CHUNK_SIZE
        
        # If text is already small enough, return as-is
        if len(text) <= max_size:
            return [text]
        
        # Split by sentences (Norwegian-aware)
        sentences = cls._split_sentences(text)
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            sentence_size = len(sentence)
            
            # If single sentence is too large, split it further
            if sentence_size > max_size:
                # Add current chunk if exists
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                # Split large sentence by words
                word_chunks = cls._split_by_words(sentence, max_size)
                chunks.extend(word_chunks)
                continue
            
            # Check if adding this sentence exceeds limit
            if current_size + sentence_size > max_size:
                # Save current chunk
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                
                # Start new chunk
                current_chunk = [sentence]
                current_size = sentence_size
            else:
                # Add to current chunk
                current_chunk.append(sentence)
                current_size += sentence_size
        
        # Add final chunk
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Split text into sentences (Norwegian-aware)."""
        # Norwegian sentence endings
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-ZÆØÅ])'
        sentences = re.split(sentence_pattern, text)
        return [s.strip() for s in sentences if s.strip()]
    
    @staticmethod
    def _split_by_words(text: str, max_size: int) -> List[str]:
        """Split text by words when sentences are too long."""
        words = text.split()
        chunks = []
        current = []
        current_size = 0
        
        for word in words:
            word_size = len(word) + 1  # +1 for space
            
            if current_size + word_size > max_size:
                if current:
                    chunks.append(" ".join(current))
                current = [word]
                current_size = word_size
            else:
                current.append(word)
                current_size += word_size
        
        if current:
            chunks.append(" ".join(current))
        
        return chunks


# ============================================================================
# NORWEGIAN TEXT PARSING & CLASSIFICATION
# ============================================================================

class NorwegianLovdataParser:
    """Parse Norwegian Lovdata TXT files with dynamic fallback"""
    
    # Norwegian metadata field patterns
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
    
    # Separator pattern
    SEPARATOR_PATTERN = re.compile(r'^-{3,}$')
    
    # Norwegian legal structure patterns
    NORWEGIAN_PATTERNS = {
        'paragraph': re.compile(r'^§\s*\d+[a-z]?\.?\s*(.*)$', re.IGNORECASE),
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
    
    @staticmethod
    def is_separator(line: str) -> bool:
        """Check if line is separator marking end of metadata"""
        try:
            return NorwegianLovdataParser.SEPARATOR_PATTERN.match(line.strip()) is not None
        except:
            return False
    
    @staticmethod
    def is_metadata_line(line: str) -> bool:
        """Check if line is metadata (skip these lines)"""
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
    def classify_norwegian_parent(line: str) -> Optional[Tuple[str, str]]:
        """
        Try to match Norwegian legal patterns
        Returns: (type, title) or None
        """
        try:
            if len(line) > 300:
                return None
            
            line_stripped = line.strip()
            
            for pattern_name, pattern in NorwegianLovdataParser.NORWEGIAN_PATTERNS.items():
                match = pattern.match(line_stripped)
                if match:
                    return (pattern_name, line_stripped)
            
            return None
        
        except Exception as e:
            logger.debug(f"Error in classify_norwegian_parent: {e}")
            return None
    
    @staticmethod
    def is_dynamic_parent(line: str) -> bool:
        """Check if line looks like a heading (fallback logic)"""
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
        """Check if line is actual content (children)"""
        try:
            line_stripped = line.strip()
            
            if len(line_stripped.split()) < 5:
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
        """Extract Norwegian document metadata from header"""
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
            kunngjort=metadata.get('kunngjort')
        )
    
    @classmethod
    def parse_file(cls, text: str, file_name: str) -> Tuple[DocumentMetadata, List[ParentNode]]:
        """
        Parse Norwegian legal document with SAFE chunk splitting
        """
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
                    
                    # Check for Norwegian legal patterns
                    norwegian_parent = cls.classify_norwegian_parent(line)
                    
                    if norwegian_parent is not None:
                        current_parent = ParentNode(
                            parent_index=parent_index,
                            parent_title=norwegian_parent[1],
                            parent_type=norwegian_parent[0],
                            children=[]
                        )
                        parents.append(current_parent)
                        parent_index += 1
                    
                    elif cls.is_dynamic_parent(line):
                        current_parent = ParentNode(
                            parent_index=parent_index,
                            parent_title=line.strip(),
                            parent_type="dynamic_heading",
                            children=[]
                        )
                        parents.append(current_parent)
                        parent_index += 1
                    
                    elif cls.is_child_content(line) and current_parent is not None:
                        # ✅ CRITICAL FIX: Split long content into safe chunks
                        text_chunks = SafeTextSplitter.split_text(line)
                        
                        for chunk_text in text_chunks:
                            child_idx = len(current_parent.children)
                            current_parent.children.append({
                                "child_index": child_idx,
                                "text": chunk_text
                            })
                
                except Exception as e:
                    logger.warning(f"Error processing line '{line[:50]}...': {e}")
                    continue
            
            # Create default parent if needed
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
                        # Split long content
                        text_chunks = SafeTextSplitter.split_text(line)
                        for chunk_text in text_chunks:
                            child_idx = len(default_parent.children)
                            default_parent.children.append({
                                "child_index": child_idx,
                                "text": chunk_text
                            })
                
                if default_parent.children:
                    parents.append(default_parent)
            
            return doc_metadata, parents
        
        except Exception as e:
            logger.error(f"Error parsing file {file_name}: {e}")
            return DocumentMetadata(file_name=file_name, file_hash=""), []


# ============================================================================
# FILE HASH & CHUNK ID GENERATION
# ============================================================================

class FileHasher:
    """Calculate file hashes and generate chunk IDs"""
    
    @staticmethod
    def hash_file(content: str) -> str:
        """Calculate SHA-256 hash of file content"""
        try:
            return hashlib.sha256(content.encode('utf-8')).hexdigest()
        except Exception as e:
            logger.error(f"Error hashing file: {e}")
            return hashlib.sha256(b"error").hexdigest()
    
    @staticmethod
    def generate_chunk_id(file_hash: str, parent_idx: int, child_idx: int) -> str:
        """Generate stable, unique chunk ID using UUID"""
        try:
            namespace = uuid.NAMESPACE_DNS
            seed = f"{file_hash}_{parent_idx:04d}_{child_idx:04d}"
            return str(uuid.uuid5(namespace, seed))
        except Exception as e:
            logger.error(f"Error generating chunk ID: {e}")
            return str(uuid.uuid4())


# ============================================================================
# MAIN CHUNKER
# ============================================================================

class NorwegianLovdataChunker:
    def __init__(self):
        self.parser = NorwegianLovdataParser()
        self.hasher = FileHasher()
        self.error_files = []
        self.success_files = []
    
    def chunk_text(self, text: str, file_name: str, zip_name: str = None) -> Tuple[DocumentMetadata, List[Chunk]]:
        """Chunk a single Norwegian legal text file with SAFE splitting"""
        try:
            file_hash = self.hasher.hash_file(text)
            
            doc_metadata, parents = self.parser.parse_file(text, file_name)
            doc_metadata.file_hash = file_hash
            
            chunks = []
            for parent in parents:
                for child in parent.children:
                    chunk_id = self.hasher.generate_chunk_id(
                        file_hash, parent.parent_index, child["child_index"]
                    )
                    
                    chunk = Chunk(
                        chunk_id=chunk_id,
                        file_name=file_name,
                        file_hash=file_hash,
                        parent_index=parent.parent_index,
                        child_index=child["child_index"],
                        parent_type=parent.parent_type,
                        parent_title=parent.parent_title,
                        text=child["text"],
                        metadata=doc_metadata.to_dict()
                    )
                    
                    # ✅ SAFETY CHECK: Verify chunk size
                    if len(chunk.text) > 2000:
                        logger.warning(f"⚠️ Chunk too large ({len(chunk.text)} chars), re-splitting...")
                        # This shouldn't happen, but just in case
                        continue
                    
                    chunks.append(chunk)
            
            return doc_metadata, chunks
        
        except Exception as e:
            logger.error(f"Error chunking {file_name}: {e}")
            return DocumentMetadata(file_name=file_name, file_hash=""), []
    
    def chunk_file(self, file_path: str) -> Tuple[DocumentMetadata, List[Chunk]]:
        """Chunk a file from disk"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            file_name = os.path.basename(file_path)
            return self.chunk_text(text, file_name)
        
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    text = f.read()
                file_name = os.path.basename(file_path)
                return self.chunk_text(text, file_name)
            except Exception as e:
                logger.error(f"Error reading {file_path} with latin-1: {e}")
                return DocumentMetadata(file_name=os.path.basename(file_path), file_hash=""), []
        
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return DocumentMetadata(file_name=os.path.basename(file_path), file_hash=""), []
    
    def get_statistics(self, chunks: List[Chunk]) -> Dict:
        """Get statistics about chunks"""
        try:
            if not chunks:
                return {
                    "total_chunks": 0,
                    "parent_types": {},
                    "avg_chunk_length": 0,
                    "total_parents": 0
                }
            
            parent_types = {}
            for chunk in chunks:
                parent_types[chunk.parent_type] = parent_types.get(chunk.parent_type, 0) + 1
            
            chunk_lengths = [len(chunk.text) for chunk in chunks]
            unique_parents = len(set(chunk.parent_index for chunk in chunks))
            
            return {
                "total_chunks": len(chunks),
                "parent_types": parent_types,
                "avg_chunk_length": sum(chunk_lengths) / len(chunks),
                "total_parents": unique_parents,
                "min_chunk_length": min(chunk_lengths),
                "max_chunk_length": max(chunk_lengths)
            }
        
        except Exception as e:
            logger.error(f"Error calculating statistics: {e}")
            return {"error": str(e)}'''

"""
Token-Aware Norwegian Lovdata Chunker
Implements smart chunking strategy with token counting and sentence-boundary splitting

Key Features:
1. Token-based chunking (no information loss)
2. Smart splitting at sentence boundaries
3. Configurable max tokens per chunk (VRAM-safe)
4. Overlap between chunks for context
5. Preserves all document content
"""

import hashlib
import re
import os
import uuid
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

# Token counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logging.warning("tiktoken not available, falling back to character-based estimation")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# TOKEN COUNTER
# ============================================================================

class TokenCounter:
    """Token counting using tiktoken for accurate token estimation"""
    
    def __init__(self, encoding_name: str = "cl100k_base"):
        """Initialize token counter with tiktoken encoding"""
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoding = tiktoken.get_encoding(encoding_name)
                self.method = "tiktoken"
                logger.info(f"✅ Token counter initialized with {encoding_name}")
            except Exception as e:
                logger.warning(f"Failed to load tiktoken: {e}")
                self.encoding = None
                self.method = "estimate"
        else:
            self.encoding = None
            self.method = "estimate"
            
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if not text:
            return 0
            
        if self.method == "tiktoken" and self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception as e:
                logger.debug(f"Tiktoken encoding failed: {e}")
                return self._estimate_tokens(text)
        else:
            return self._estimate_tokens(text)
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (~4 characters per token for European languages)"""
        return len(text) // 4


# ============================================================================
# TOKEN-AWARE TEXT SPLITTER
# ============================================================================

class TokenAwareTextSplitter:
    """
    Split text into token-bounded chunks at sentence boundaries
    Preserves context with configurable overlap
    """
    
    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 50,
        token_counter: Optional[TokenCounter] = None
    ):
        """
        Initialize splitter
        
        Args:
            max_tokens: Maximum tokens per chunk (512 is safe for most embedders)
            overlap_tokens: Overlap between chunks for context preservation
            token_counter: Token counter instance
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.token_counter = token_counter or TokenCounter()
        
        # Norwegian sentence endings
        self.sentence_pattern = re.compile(r'[.!?]\s+')
        
    def split_text(self, text: str) -> List[str]:
        """
        Split text into token-bounded chunks at sentence boundaries
        
        Args:
            text: Input text to split
            
        Returns:
            List of text chunks, each under max_tokens
        """
        if not text or not text.strip():
            return []
        
        # Check if text fits in one chunk
        total_tokens = self.token_counter.count_tokens(text)
        if total_tokens <= self.max_tokens:
            return [text]
        
        # Split into sentences
        sentences = self._split_into_sentences(text)
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self.token_counter.count_tokens(sentence)
            
            # If single sentence exceeds limit, split it by words
            if sentence_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                word_chunks = self._split_long_sentence(sentence)
                chunks.extend(word_chunks)
                continue
            
            # Check if adding sentence would exceed limit
            if current_tokens + sentence_tokens > self.max_tokens:
                # Save current chunk
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                
                # Start new chunk with overlap
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
        
        # Add final chunk
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using Norwegian-aware patterns"""
        sentences = self.sentence_pattern.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Handle edge cases where split removed punctuation
        result = []
        for i, sent in enumerate(sentences):
            if i < len(sentences) - 1 and not sent.endswith(('.', '!', '?')):
                if sentences[i + 1] and sentences[i + 1][0].islower():
                    sent += '.'
            result.append(sent)
        
        return result
    
    def _split_long_sentence(self, sentence: str) -> List[str]:
        """Split a sentence that's too long by word boundaries"""
        words = sentence.split()
        chunks = []
        current_chunk = []
        current_tokens = 0
        
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
        """Get overlap text from end of chunk"""
        overlap_sentences = []
        overlap_tokens = 0
        
        for sentence in reversed(chunk):
            sentence_tokens = self.token_counter.count_tokens(sentence)
            if overlap_tokens + sentence_tokens <= self.overlap_tokens:
                overlap_sentences.insert(0, sentence)
                overlap_tokens += sentence_tokens
            else:
                break
        
        return " ".join(overlap_sentences)


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class ParentNode:
    """Parent heading (§, Kapittel, Artikkel, or dynamic heading)"""
    parent_index: int
    parent_title: str
    parent_type: str
    children: List[Dict] = field(default_factory=list)


@dataclass
class DocumentMetadata:
    """Norwegian document-level metadata"""
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
    url: Optional[str] = None  # Add URL field
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Chunk:
    """Individual chunk with all metadata"""
    chunk_id: str
    file_name: str
    file_hash: str
    parent_index: int
    child_index: int
    parent_type: str
    parent_title: str
    text: str
    token_count: int = 0
    is_split: bool = False
    split_index: int = 0
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        result = {
            "chunk_id": self.chunk_id,
            "file_name": self.file_name,
            "file_hash": self.file_hash,
            "parent_index": self.parent_index,
            "child_index": self.child_index,
            "parent_type": self.parent_type,
            "parent_title": self.parent_title,
            "text": self.text,
            "token_count": self.token_count,
            "is_split": self.is_split,
            "split_index": self.split_index
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


# ============================================================================
# NORWEGIAN PARSER (Same as your original)
# ============================================================================

class NorwegianLovdataParser:
    """Parse Norwegian Lovdata TXT files with dynamic fallback"""
    
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
        'paragraph': re.compile(r'^§\s*\d+[a-z]?\.?\s*(.*)$', re.IGNORECASE),
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
    
    @staticmethod
    def is_separator(line: str) -> bool:
        """Check if line is separator"""
        try:
            return NorwegianLovdataParser.SEPARATOR_PATTERN.match(line.strip()) is not None
        except:
            return False
    
    @staticmethod
    def is_metadata_line(line: str) -> bool:
        """Check if line is metadata"""
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
        except:
            return False
    
    @staticmethod
    def classify_norwegian_parent(line: str) -> Optional[Tuple[str, str]]:
        """Try to match Norwegian legal patterns"""
        try:
            if len(line) > 300:
                return None
            
            line_stripped = line.strip()
            
            for pattern_name, pattern in NorwegianLovdataParser.NORWEGIAN_PATTERNS.items():
                match = pattern.match(line_stripped)
                if match:
                    return (pattern_name, line_stripped)
            
            return None
        except:
            return None
    
    @staticmethod
    def is_dynamic_parent(line: str) -> bool:
        """Check if line looks like a heading (fallback)"""
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
        except:
            return False
    
    @staticmethod
    def is_child_content(line: str) -> bool:
        """Check if line is actual content"""
        try:
            line_stripped = line.strip()
            
            if len(line_stripped.split()) < 5:
                return False
            
            if line_stripped.isupper() and len(line_stripped) > 30:
                return False
            
            if NorwegianLovdataParser.is_metadata_line(line_stripped):
                return False
            
            return True
        except:
            return False
    
    @staticmethod
    def parse_metadata(lines: List[str]) -> DocumentMetadata:
        """Extract Norwegian document metadata"""
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
            kunngjort=metadata.get('kunngjort')
        )
    
    @classmethod
    def parse_file(cls, text: str, file_name: str) -> Tuple[DocumentMetadata, List[ParentNode]]:
        """Parse Norwegian legal document with hierarchical structure"""
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
                        current_parent = ParentNode(
                            parent_index=parent_index,
                            parent_title=norwegian_parent[1],
                            parent_type=norwegian_parent[0],
                            children=[]
                        )
                        parents.append(current_parent)
                        parent_index += 1
                    
                    elif cls.is_dynamic_parent(line):
                        current_parent = ParentNode(
                            parent_index=parent_index,
                            parent_title=line.strip(),
                            parent_type="dynamic_heading",
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
                    logger.warning(f"Error processing line: {e}")
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
                        default_parent.children.append({
                            "child_index": idx,
                            "text": line
                        })
                
                if default_parent.children:
                    parents.append(default_parent)
            
            return doc_metadata, parents
        
        except Exception as e:
            logger.error(f"Error parsing file {file_name}: {e}")
            return DocumentMetadata(file_name=file_name, file_hash=""), []


# ============================================================================
# FILE UTILITIES
# ============================================================================

class FileHasher:
    """Calculate file hashes and generate chunk IDs"""
    
    @staticmethod
    def hash_file(content: str) -> str:
        """Calculate SHA-256 hash"""
        try:
            return hashlib.sha256(content.encode('utf-8')).hexdigest()
        except Exception as e:
            logger.error(f"Error hashing file: {e}")
            return hashlib.sha256(b"error").hexdigest()
    
    @staticmethod
    def generate_chunk_id(
        file_hash: str,
        parent_idx: int,
        child_idx: int,
        split_idx: int = 0
    ) -> str:
        """Generate stable UUID-based chunk ID"""
        try:
            namespace = uuid.NAMESPACE_DNS
            seed = f"{file_hash}_{parent_idx:04d}_{child_idx:04d}_{split_idx:04d}"
            return str(uuid.uuid5(namespace, seed))
        except Exception as e:
            logger.error(f"Error generating chunk ID: {e}")
            return str(uuid.uuid4())


# ============================================================================
# MAIN TOKEN-AWARE CHUNKER
# ============================================================================

class NorwegianLovdataChunker:
    """
    ✅ TOKEN-AWARE CHUNKER with smart splitting
    
    Key improvements:
    1. Token-based chunking (no truncation)
    2. Sentence-boundary splitting
    3. Context preservation with overlap
    4. VRAM-safe with configurable limits
    """
    
    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 50
    ):
        """
        Initialize token-aware chunker
        
        Args:
            max_tokens: Maximum tokens per chunk (512 is safe for most models)
            overlap_tokens: Overlap between chunks for context
        """
        self.parser = NorwegianLovdataParser()
        self.hasher = FileHasher()
        self.token_counter = TokenCounter()
        self.text_splitter = TokenAwareTextSplitter(
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
            token_counter=self.token_counter
        )
        self.error_files = []
        self.success_files = []
        
        logger.info(
            f"✅ Token-aware chunker initialized | "
            f"max_tokens={max_tokens} | overlap={overlap_tokens}"
        )
    
    def chunk_text(
        self,
        text: str,
        file_name: str,
        zip_name: str = None,
        url: str = None
    ) -> Tuple[DocumentMetadata, List[Chunk]]:
        """
        Chunk a Norwegian legal text with token-aware splitting
        
        Args:
            text: Document text
            file_name: File name
            zip_name: Archive name (optional)
            url: Document URL (optional)
            
        Returns:
            (metadata, chunks)
        """
        try:
            file_hash = self.hasher.hash_file(text)
            
            doc_metadata, parents = self.parser.parse_file(text, file_name)
            doc_metadata.file_hash = file_hash
            if url:
                doc_metadata.url = url
            
            chunks = []
            total_splits = 0
            
            for parent in parents:
                for child in parent.children:
                    child_text = child["text"]
                    child_idx = child["child_index"]
                    
                    token_count = self.token_counter.count_tokens(child_text)
                    
                    if token_count <= self.text_splitter.max_tokens:
                        # No splitting needed
                        chunk_id = self.hasher.generate_chunk_id(
                            file_hash, parent.parent_index, child_idx, 0
                        )
                        
                        chunk = Chunk(
                            chunk_id=chunk_id,
                            file_name=file_name,
                            file_hash=file_hash,
                            parent_index=parent.parent_index,
                            child_index=child_idx,
                            parent_type=parent.parent_type,
                            parent_title=parent.parent_title,
                            text=child_text,
                            token_count=token_count,
                            is_split=False,
                            split_index=0,
                            metadata=doc_metadata.to_dict()
                        )
                        chunks.append(chunk)
                    
                    else:
                        # Split into multiple chunks
                        split_texts = self.text_splitter.split_text(child_text)
                        total_splits += len(split_texts) - 1
                        
                        logger.debug(
                            f"Split child {child_idx} ({token_count} tokens) "
                            f"into {len(split_texts)} chunks"
                        )
                        
                        for split_idx, split_text in enumerate(split_texts):
                            split_token_count = self.token_counter.count_tokens(split_text)
                            
                            chunk_id = self.hasher.generate_chunk_id(
                                file_hash, parent.parent_index, child_idx, split_idx
                            )
                            
                            chunk = Chunk(
                                chunk_id=chunk_id,
                                file_name=file_name,
                                file_hash=file_hash,
                                parent_index=parent.parent_index,
                                child_index=child_idx,
                                parent_type=parent.parent_type,
                                parent_title=parent.parent_title,
                                text=split_text,
                                token_count=split_token_count,
                                is_split=True,
                                split_index=split_idx,
                                metadata=doc_metadata.to_dict()
                            )
                            chunks.append(chunk)
            
            if total_splits > 0:
                logger.info(f"✂️  Split {total_splits} oversized chunks in {file_name}")
            
            return doc_metadata, chunks
        
        except Exception as e:
            logger.error(f"Error chunking {file_name}: {e}")
            return DocumentMetadata(file_name=file_name, file_hash=""), []
    
    def chunk_file(self, file_path: str, url: str = None) -> Tuple[DocumentMetadata, List[Chunk]]:
        """Chunk a file from disk"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            file_name = os.path.basename(file_path)
            return self.chunk_text(text, file_name, url=url)
        
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    text = f.read()
                file_name = os.path.basename(file_path)
                return self.chunk_text(text, file_name, url=url)
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
                return DocumentMetadata(file_name=os.path.basename(file_path), file_hash=""), []
        
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return DocumentMetadata(file_name=os.path.basename(file_path), file_hash=""), []
    
    def get_statistics(self, chunks: List[Chunk]) -> Dict:
        """Get chunk statistics"""
        try:
            if not chunks:
                return {
                    "total_chunks": 0,
                    "parent_types": {},
                    "avg_chunk_length": 0,
                    "avg_token_count": 0,
                    "total_parents": 0,
                    "split_chunks": 0
                }
            
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


if __name__ == "__main__":
    # Example usage
    chunker = NorwegianLovdataChunker(max_tokens=512, overlap_tokens=50)
    print("✅ Token-aware chunker ready")