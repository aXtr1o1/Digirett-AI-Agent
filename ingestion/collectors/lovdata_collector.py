import os
import tarfile
import requests
import logging
import xml.etree.ElementTree as ET
from ingestion.src.storage.supabase_store import SupabaseStore
from pathlib import Path
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger("lovdata-collector")

from ingestion.src.config import LOVDATA_API_URL, RAW_XML_DIR, ARCHIVE_DIR

BASE_URL = LOVDATA_API_URL

# --------------------------------------------------
# Small helpers
# --------------------------------------------------
def _is_safe_path(name: str) -> bool:
    return ".." not in Path(name).parts


def _is_valid_xml(data: bytes) -> bool:
    try:
        ET.fromstring(data)
        return True
    except ET.ParseError:
        return False


# --------------------------------------------------
# NEW: Fetch ALL archives from API
# --------------------------------------------------
def _fetch_all_archives() -> List[Dict]:
    """
    Fetch ALL available archives from Lovdata API.
    
    Returns:
        List of dicts with archive info:
        [
            {"filename": "lovtidend-avd1-2001-2025.tar.bz2", ...},
            {"filename": "lovtidend-avd1-2026.tar.bz2", ...},
            {"filename": "gjeldende-lover.tar.bz2", ...},
        ]
    """
    try:
        logger.info("📡 Fetching ALL archives from Lovdata API...")
        
        resp = requests.get(f"{LOVDATA_API_URL}/list", timeout=30)
        resp.raise_for_status()
        
        archives = resp.json()
        
        if not archives:
            logger.error("❌ No archives returned from API")
            return []
        
        logger.info(f"✅ Found {len(archives)} archives:")
        for archive in archives:
            size_gb = archive.get('size', 0) / (1024**3)
            logger.info(f"   📦 {archive['filename']}")
        
        return archives
    
    except Exception as e:
        logger.error(f"❌ API call failed: {e}")
        # Fallback to known archives
        logger.warning("⚠️  Using fallback archive list")
        return [
            {"filename": "lovtidend-avd1-2001-2025.tar.bz2"},
            {"filename": "lovtidend-avd1-2026.tar.bz2"},
            {"filename": "gjeldende-lover.tar.bz2"},
        ]


# --------------------------------------------------
# Download archive
# --------------------------------------------------
def _download_archive(archive_name: str) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    archive_path = ARCHIVE_DIR / archive_name

    if archive_path.exists():
        logger.info(f"✅ Using cached: {archive_name}")
        return archive_path

    # ✅ Correct Lovdata download URL
    url = f"{LOVDATA_API_URL}/get/{archive_name}"

    logger.info(f"⬇️  Downloading: {archive_name}")
    logger.info(f"   URL: {url}")

    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(archive_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

    logger.info(f"✅ Downloaded: {archive_name}")
    return archive_path

# --------------------------------------------------
# Extract XML files
# --------------------------------------------------
def _extract_xml_files(
    archive_path: Path,
    limit: Optional[int] = None
) -> List[Path]:
    """
    Extract XML files from archive.
    
    Args:
        archive_path: Path to archive
        limit: Max files to extract (None = extract all)
    """
    if limit is not None and limit == 0:
        return []
    
    RAW_XML_DIR.mkdir(parents=True, exist_ok=True)
    extracted: List[Path] = []
    db = SupabaseStore()
    existing_files = db.get_all_file_names()

    
    try:
        tar = tarfile.open(archive_path, "r:bz2")
        try:
            for member in tar.getmembers():
                
                if not _is_safe_path(member.name):
                    raise ValueError(f"Unsafe path: {member.name}")
                
                if not member.isfile() or not member.name.endswith(".xml"):
                    continue
                
                # Check limit
                if limit is not None and len(extracted) >= limit:
                    break
                
                original_name = os.path.basename(member.name)      # nl-20010105-001.xml
                clean_name = os.path.splitext(original_name)[0]    # nl-20010105-001

                target = RAW_XML_DIR / original_name              # ✅ keep .xml locally

                # Check DB using name WITHOUT extension
                if existing_files and clean_name in existing_files:
                    logger.info(f"⏭️ Already processed, skipping: {clean_name}")
                    continue

                file_obj = tar.extractfile(member)
                if not file_obj:
                    continue
                
                data = file_obj.read()
                if not _is_valid_xml(data):
                    continue
                
                with open(target, "wb") as f:
                    f.write(data)
                
                extracted.append(target)
        
        finally:
            tar.close()
        
        return extracted
    
    except Exception as e:
        logger.error(f"❌ Extraction failed: {e}")
        raise


# --------------------------------------------------
# Public API - NEW VERSION (processes ALL archives)
# --------------------------------------------------
def fetch_lovdata_files(
    limit: Optional[int] = 50
) -> Tuple[List[str], List[str]]:
    """
    Fetch XML files from ALL Lovdata archives.
    
    ✅ CHANGES:
    - Fetches from ALL archives (not just one)
    - No default limit (processes everything)
    - Returns list of processed archive names
    
    Args:
        limit: Total files across ALL archives (None = unlimited)
        
    Returns:
        Tuple of:
        - List of XML file paths
        - List of archive names processed
    
    Examples:
        # Process ALL files from ALL archives
        files, archives = fetch_lovdata_files()
        
        # Process first 500 files total
        files, archives = fetch_lovdata_files(limit=500)
    """
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0 or None")
    
    # Fetch ALL available archives
    archive_list = _fetch_all_archives()
    
    if not archive_list:
        logger.error("❌ No archives available")
        return [], []
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📦 MULTI-ARCHIVE COLLECTION")
    logger.info(f"{'='*70}")
    logger.info(f"Archives available: {len(archive_list)}")
    logger.info(f"File limit: {'UNLIMITED' if limit is None else limit}")
    logger.info(f"{'='*70}\n")
    
    all_files: List[Path] = []
    processed_archives: List[str] = []
    remaining = limit
    
    # Process each archive
    for i, archive_info in enumerate(archive_list, 1):
        archive_name = archive_info['filename']
        
        logger.info(f"[{i}/{len(archive_list)}] {archive_name}")
        
        try:
            # Download
            archive_path = _download_archive(archive_name)
            
            # Calculate per-archive limit
            if remaining is not None:
                if remaining <= 0:
                    logger.info(f"⏭️  Limit reached ({limit} files), stopping")
                    break
                per_archive_limit = remaining
            else:
                per_archive_limit = None
            
            # Extract
            files = _extract_xml_files(archive_path, per_archive_limit)
            
            if files:
                all_files.extend(files)
                processed_archives.append(archive_name)
                
                logger.info(f"   ✅ {len(files)} files | Total: {len(all_files)}")
                
                if remaining is not None:
                    remaining -= len(files)
            else:
                logger.warning(f"   ⚠️  No files extracted")
        
        except Exception as e:
            logger.error(f"   ❌ Failed: {e}")
            continue
    
    # Summary
    logger.info(f"\n{'='*70}")
    logger.info(f"✅ COLLECTION COMPLETE")
    logger.info(f"{'='*70}")
    logger.info(f"Archives processed: {len(processed_archives)}/{len(archive_list)}")
    logger.info(f"Total files: {len(all_files)}")
    for archive_name in processed_archives:
        logger.info(f"   ✅ {archive_name}")
    logger.info(f"{'='*70}\n")
    
    return [str(p) for p in all_files], processed_archives