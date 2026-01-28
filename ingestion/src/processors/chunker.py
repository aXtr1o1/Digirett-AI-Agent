"""
Dynamic Norwegian Lovdata Hierarchical Chunking System - FIXED VERSION
Handles Norwegian legal documents with intelligent pattern recognition

FIXES APPLIED:
1. ✅ Text content now stored properly in chunks
2. ✅ UUID-based chunk IDs (no more "unknown" duplicates)
3. ✅ Sequential parent indices (starts at 0, proper incrementation)
4. ✅ Sequential child indices (resets to 0 for each parent)
5. ✅ Proper parent title extraction

- Recognizes Norwegian legal terminology (§, Kapittel, Artikkel, Lov, etc.)
- Dynamic fallback for any document structure
- Extracts Norwegian metadata fields (Datokode, DokumentID, Departement, etc.)
- Error-resistant with comprehensive handling
"""

import hashlib
import re
import os
import uuid
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

# Setup logging
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
            "text": self.text  # ✅ FIX #1: Text explicitly included
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


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
    
    # Norwegian legal structure patterns (priority order)
    NORWEGIAN_PATTERNS = {
        # § paragraphs (highest priority for Norwegian law)
        'paragraph': re.compile(r'^§\s*\d+[a-z]?\.?\s*(.*)$', re.IGNORECASE),
        
        # Kapittel (Chapter)
        'kapittel': re.compile(r'^(Kapittel|Kap\.?)\s+([IVXLCDM\d]+)\.?\s*(.*)$', re.IGNORECASE),
        
        # Del (Part)
        'del': re.compile(r'^Del\s+([IVXLCDM\d]+)\.?\s*(.*)$', re.IGNORECASE),
        
        # Avdeling (Division)
        'avdeling': re.compile(r'^Avdeling\s+([IVXLCDM\d]+)\.?\s*(.*)$', re.IGNORECASE),
        
        # Article patterns
        'artikkel': re.compile(r'^(\d+)\s*(Art\.|Artikkel)\.?\s*(.*)$', re.IGNORECASE),
        
        # Lov (Law title)
        'lov_title': re.compile(r'^Lov\s+om\s+(.+)$', re.IGNORECASE),
        
        # Numbered sections with parentheses
        'numbered_paren': re.compile(r'^\((\d+)\)\s+(.+)$'),
        
        # Lettered sections
        'lettered': re.compile(r'^([a-z])\)\s+(.+)$', re.IGNORECASE),
        
        # Roman numeral headings
        'roman': re.compile(r'^([IVXLCDM]+)\.?\s+(.+)$'),
        
        # Numbered headings (1., 2., etc)
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
            
            # Check against known metadata patterns
            for pattern in NorwegianLovdataParser.METADATA_FIELDS.values():
                if re.match(pattern, line, re.IGNORECASE):
                    return True
            
            # Generic metadata patterns
            if line.strip().startswith(('-', '•', '    -')):
                if ':' in line and len(line) < 200:
                    return True
            
            # "Innhold" section
            if re.match(r'^\s*[-•]?\s*Innhold\s*$', line, re.IGNORECASE):
                return True
                
            return False
        except Exception as e:
            logger.debug(f"Error in is_metadata_line: {e}")
            return False
    
    @staticmethod
    def classify_norwegian_parent(line: str) -> Optional[Tuple[str, str]]:
        """
        IF BLOCK: Try to match Norwegian legal patterns
        Returns: (type, title) or None
        """
        try:
            if len(line) > 300:
                return None
            
            line_stripped = line.strip()
            
            # Try each Norwegian pattern in priority order
            for pattern_name, pattern in NorwegianLovdataParser.NORWEGIAN_PATTERNS.items():
                match = pattern.match(line_stripped)
                if match:
                    # ✅ FIX #5: Return the actual matched line as title
                    return (pattern_name, line_stripped)
            
            return None
        
        except Exception as e:
            logger.debug(f"Error in classify_norwegian_parent: {e}")
            return None
    
    @staticmethod
    def is_dynamic_parent(line: str) -> bool:
        """
        ELSE BLOCK: Check if line looks like a heading (fallback logic)
        
        Criteria for dynamic parent:
        - Short (2-20 words)
        - Not metadata
        - Capitalized or ends with : or .
        - Not a full sentence
        """
        try:
            if not line or len(line) < 3:
                return False
            
            line_stripped = line.strip()
            
            # Skip metadata
            if NorwegianLovdataParser.is_metadata_line(line_stripped):
                return False
            
            word_count = len(line_stripped.split())
            
            # Too long to be a heading
            if word_count > 20 or len(line_stripped) > 200:
                return False
            
            # Too short
            if word_count < 2:
                return False
            
            # Check heading indicators
            is_capitalized = line_stripped[0].isupper()
            ends_with_colon = line_stripped.endswith(':')
            ends_with_period = line_stripped.endswith('.')
            is_all_caps = line_stripped.isupper()
            
            # Strong heading indicators
            if ends_with_colon:
                return True
            
            if is_all_caps and word_count <= 10:
                return True
            
            if ends_with_period and 2 <= word_count <= 12 and is_capitalized:
                # Avoid sentences with verbs
                common_verbs = ['er', 'skal', 'kan', 'må', 'blir', 'har', 'vil']
                if not any(verb in line_stripped.lower().split() for verb in common_verbs):
                    return True
            
            # Numbered headings
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
            
            # Must have at least 5 words
            if len(line_stripped.split()) < 5:
                return False
            
            # Not all uppercase (headers)
            if line_stripped.isupper() and len(line_stripped) > 30:
                return False
            
            # Not metadata
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
            # Find separator line
            separator_idx = None
            for i, line in enumerate(lines[:100]):
                if NorwegianLovdataParser.is_separator(line):
                    separator_idx = i
                    break
            
            # Parse metadata before separator
            if separator_idx:
                for line in lines[:separator_idx]:
                    # Try each metadata pattern
                    for field_name, pattern in NorwegianLovdataParser.METADATA_FIELDS.items():
                        match = re.match(pattern, line, re.IGNORECASE)
                        if match:
                            metadata[field_name] = match.group(1).strip()
                            break
            
            # Extract year
            year = None
            if 'year' in metadata:
                try:
                    year = int(metadata['year'])
                except:
                    pass
            
            # Try to extract year from datokode if not found
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
        Parse entire Norwegian legal document with IF-ELSE fallback logic
        
        Workflow:
        1. Extract Norwegian metadata
        2. For each line:
           IF → matches Norwegian legal pattern (§, Kapittel, etc.)
               → Use as parent
           ELSE IF → looks like heading (short, capitalized, etc.)
               → Use as dynamic parent
           ELSE → treat as child content
        
        Returns: (metadata, parent_nodes)
        """
        try:
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            
            # Extract metadata
            doc_metadata = cls.parse_metadata(lines)
            doc_metadata.file_name = file_name
            
            # Find where content starts (after separator)
            content_start = 0
            for i, line in enumerate(lines):
                if cls.is_separator(line):
                    content_start = i + 1
                    break
            
            # Parse hierarchical structure
            parents = []
            current_parent = None
            parent_index = 0  # ✅ FIX #3: Start at 0, not -1
            
            # Skip "Innhold" section if present
            in_innhold = False
            
            for line in lines[content_start:]:
                try:
                    # Skip empty or very short lines
                    if len(line) < 3:
                        continue
                    
                    # Check for "Innhold" section start
                    if re.match(r'^\s*[-•]?\s*Innhold\s*$', line, re.IGNORECASE):
                        in_innhold = True
                        continue
                    
                    # Skip lines in Innhold section until separator or content
                    if in_innhold:
                        if cls.is_separator(line):
                            in_innhold = False
                        continue
                    
                    # ========================================
                    # IF BLOCK: Try Norwegian legal patterns first
                    # ========================================
                    norwegian_parent = cls.classify_norwegian_parent(line)
                    
                    if norwegian_parent is not None:
                        # FOUND NORWEGIAN LEGAL PARENT
                        # ✅ FIX #3: Use current parent_index, then increment
                        current_parent = ParentNode(
                            parent_index=parent_index,
                            parent_title=norwegian_parent[1],  # ✅ FIX #5: Actual title
                            parent_type=norwegian_parent[0],
                            children=[]
                        )
                        parents.append(current_parent)
                        parent_index += 1  # ✅ FIX #3: Increment AFTER adding
                        
                        logger.debug(f"Norwegian parent found: {norwegian_parent[0]} - {norwegian_parent[1][:50]}")
                    
                    # ========================================
                    # ELSE BLOCK: Fallback to dynamic headings
                    # ========================================
                    elif cls.is_dynamic_parent(line):
                        # FOUND DYNAMIC PARENT
                        current_parent = ParentNode(
                            parent_index=parent_index,
                            parent_title=line.strip(),  # ✅ FIX #5: Actual title
                            parent_type="dynamic_heading",
                            children=[]
                        )
                        parents.append(current_parent)
                        parent_index += 1  # ✅ FIX #3: Increment AFTER adding
                        
                        logger.debug(f"Dynamic parent found: {line[:50]}")
                    
                    # ========================================
                    # Content under current parent
                    # ========================================
                    elif cls.is_child_content(line) and current_parent is not None:
                        # ✅ FIX #4: child_index is managed per parent
                        child_idx = len(current_parent.children)
                        current_parent.children.append({
                            "child_index": child_idx,
                            "text": line  # ✅ FIX #1: Store actual text
                        })
                
                except Exception as e:
                    logger.warning(f"Error processing line '{line[:50]}...': {e}")
                    continue
            
            # If no parents found, create one default parent
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
        """
        Generate stable, unique chunk ID using UUID
        ✅ FIX #2: Use UUID instead of hash-based approach to guarantee uniqueness
        """
        try:
            # Generate deterministic UUID from file_hash, parent_idx, and child_idx
            # This ensures same input always produces same UUID
            namespace = uuid.NAMESPACE_DNS
            seed = f"{file_hash}_{parent_idx:04d}_{child_idx:04d}"
            return str(uuid.uuid5(namespace, seed))
        except Exception as e:
            logger.error(f"Error generating chunk ID: {e}")
            # Fallback to random UUID if deterministic fails
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
        """Chunk a single Norwegian legal text file"""
        try:
            # Calculate file hash
            file_hash = self.hasher.hash_file(text)
            
            # Parse hierarchical structure
            doc_metadata, parents = self.parser.parse_file(text, file_name)
            doc_metadata.file_hash = file_hash
            
            chunks = []
            for parent in parents:
                for child in parent.children:
                    # ✅ FIX #2: Use UUID-based chunk ID
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
                        parent_title=parent.parent_title,  # ✅ FIX #5: Has actual title
                        text=child["text"],  # ✅ FIX #1: Has actual text
                        metadata=doc_metadata.to_dict()
                    )
                    chunks.append(chunk)
            
            return doc_metadata, chunks
        
        except Exception as e:
            logger.error(f"Error chunking {file_name}: {e}")
            return DocumentMetadata(file_name=file_name, file_hash=""), []

    def log_file_summary(self, metadata: DocumentMetadata, chunks: List[Chunk]):
        """Logs a detailed summary of a processed file to the console."""
        stats = self.get_statistics(chunks)
        print(f"\n" + "="*50)
        print(f"📄 FILE: {metadata.file_name}")
        print(f"📊 Stats: {stats['total_chunks']} chunks | {stats['total_parents']} parents")
        print(f"🧬 Hash: {metadata.file_hash[:16]}...")
        if chunks:
            print(f"📝 Preview: {chunks[0].text[:100]}...")
        print("="*50 + "\n")    

    def chunk_file(self, file_path: str) -> Tuple[DocumentMetadata, List[Chunk]]:
        """Chunk a file from disk"""
        try:
            # Try UTF-8 first
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            file_name = os.path.basename(file_path)
            return self.chunk_text(text, file_name)
        
        except UnicodeDecodeError:
            try:
                # Try latin-1 encoding
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
    
    def chunk_directory(self, directory: str, limit: int = None) -> Dict[str, Tuple[DocumentMetadata, List[Chunk]]]:
        """
        Chunk all TXT files in a directory
        
        Args:
            directory: Path to directory
            limit: Max number of files to process (None = all)
        """
        try:
            txt_files = list(Path(directory).glob("*.txt"))
            
            if not txt_files:
                logger.warning(f"No TXT files found in {directory}")
                return {}
            
            # Apply limit if specified
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
                        logger.info(f"[{idx}/{total}] ✅ {txt_file.name}: {len(chunks)} chunks")
                    else:
                        self.error_files.append((txt_file.name, "No chunks created"))
                        logger.warning(f"[{idx}/{total}] ⚠️  {txt_file.name}: No chunks created")
                
                except Exception as e:
                    self.error_files.append((txt_file.name, str(e)))
                    logger.error(f"[{idx}/{total}] ❌ {txt_file.name}: {e}")
            
            # Print summary
            self.print_summary(total)
            
            return results
        
        except Exception as e:
            logger.error(f"Error processing directory {directory}: {e}")
            return {}
    
    def print_summary(self, total: int):
        """Print processing summary"""
        print("\n" + "="*70)
        print("NORWEGIAN LOVDATA PROCESSING SUMMARY")
        print("="*70)
        print(f"Total files: {total}")
        print(f"✅ Successful: {len(self.success_files)}")
        print(f"❌ Errors: {len(self.error_files)}")
        
        if self.error_files:
            print("\n" + "-"*70)
            print("FILES WITH ERRORS:")
            print("-"-70)
            for file_name, error in self.error_files[:10]:
                print(f"  • {file_name}: {error[:50]}")
            if len(self.error_files) > 10:
                print(f"  ... and {len(self.error_files) - 10} more")
        
        print("="*70 + "\n")
    
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
            return {"error": str(e)}


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys
    
    chunker = NorwegianLovdataChunker()
    
    if len(sys.argv) > 1:
        path = sys.argv[1]
        
        if os.path.isdir(path):
            # Process directory
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
            
            print(f"\n🔄 Processing Norwegian legal directory: {path}")
            if limit:
                print(f"   Limit: {limit} files")
            
            results = chunker.chunk_directory(path, limit=limit)
            
            # Show detailed stats for first file
            if results:
                first_file = list(results.keys())[0]
                metadata, chunks = results[first_file]
                
                print(f"\n{'='*70}")
                print(f"EXAMPLE FILE: {first_file}")
                print(f"{'='*70}")
                print(f"\nMetadata:")
                print(f"  Datokode: {metadata.datokode}")
                print(f"  Tittel: {metadata.tittel}")
                print(f"  Departement: {metadata.departement}")
                print(f"  Year: {metadata.year}")
                
                stats = chunker.get_statistics(chunks)
                print(f"\nStatistics:")
                print(f"  Total Chunks: {stats['total_chunks']}")
                print(f"  Total Parents: {stats['total_parents']}")
                print(f"  Avg Chunk Length: {stats['avg_chunk_length']:.0f} chars")
                print(f"\n  Parent Types:")
                for ptype, count in stats["parent_types"].items():
                    print(f"    {ptype}: {count}")
                
                # Show first 3 chunks with full details
                print(f"\n{'='*70}")
                print(f"First 3 Chunks (with text preview):")
                print(f"{'='*70}")
                for i, chunk in enumerate(chunks[:3], 1):
                    print(f"\n--- Chunk {i} ---")
                    print(f"ID: {chunk.chunk_id}")
                    print(f"Parent [{chunk.parent_index}]: {chunk.parent_title}")
                    print(f"Child Index: {chunk.child_index}")
                    print(f"Type: {chunk.parent_type}")
                    print(f"Text: {chunk.text[:150]}...")
        
        else:
            # Process single file
            metadata, chunks = chunker.chunk_file(path)
            
            print(f"\n{'='*70}")
            print(f"File: {metadata.file_name}")
            print(f"{'='*70}")
            print(f"\nMetadata:")
            for key, value in metadata.to_dict().items():
                if value:
                    print(f"  {key}: {value}")
            
            print(f"\nTotal Chunks: {len(chunks)}")
            
            stats = chunker.get_statistics(chunks)
            print(f"\nParent Types:")
            for ptype, count in stats["parent_types"].items():
                print(f"  {ptype}: {count}")
            
            if chunks:
                print(f"\nFirst 3 chunks:")
                for i, chunk in enumerate(chunks[:3], 1):
                    print(f"\n--- Chunk {i} ---")
                    print(f"  ID: {chunk.chunk_id}")
                    print(f"  Parent: {chunk.parent_title}")
                    print(f"  Type: {chunk.parent_type}")
                    print(f"  Text: {chunk.text[:150]}...")
    
    else:
        print("Usage:")
        print("  Single file:  python chunker_fixed.py <file.txt>")
        print("  Directory:    python chunker_fixed.py <directory> [limit]")
        print("")
        print("Examples:")
        print("  python chunker_fixed.py nl-18981210-001.txt")
        print("  python chunker_fixed.py ./lovdata/")
        print("  python chunker_fixed.py ./lovdata/ 50  # Process first 50 files")