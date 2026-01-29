import os
import tarfile
import requests
import logging
from pathlib import Path
from typing import List, Tuple
import sys
logger = logging.getLogger("lovdata-collector")

BASE_URL = "https://api.lovdata.no"
LIST_ENDPOINT = "/v1/publicData/list"
GET_ENDPOINT = "/v1/publicData/get"
current_dir=os.path.dirname(os.path.abspath(__file__))

REPO_PATH=os.path.abspath(os.path.join(current_dir,"..",".."))

DATA_DIR = os.path.join(os.path.join(REPO_PATH), "data")

RAW_XML_DIR = Path(os.path.join(DATA_DIR, "raw_xml"))
ARCHIVE_DIR = Path(os.path.join(DATA_DIR, "archives"))

# RAW_XML_DIR.mkdir(parents=True, exist_ok=True)
# ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)



# --------------------------------------------------
# Small helpers (MI-friendly)
# --------------------------------------------------
def _is_safe_path(name: str) -> bool:
    return ".." not in Path(name).parts


def _is_valid_xml(data: bytes) -> bool:
    return isinstance(data, (bytes, bytearray)) and data.strip().startswith(b"<")


def _existing_archive() -> Path | None:
    archives = list(ARCHIVE_DIR.glob("*.tar.bz2"))
    return archives[0] if archives else None


# --------------------------------------------------
# Network helpers
# --------------------------------------------------
def _fetch_archive_name() -> str:
    resp = requests.get(f"{BASE_URL}{LIST_ENDPOINT}", timeout=30)

    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise RuntimeError("Lovdata list API returned empty response")
    return data[0]["filename"]


def _download_archive(archive_name: str) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    archive_path = Path(os.path.join(ARCHIVE_DIR, archive_name))
    
    if archive_path.exists():
        return archive_path

    url = f"{BASE_URL}{GET_ENDPOINT}/{archive_name}"
    
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(archive_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

    return archive_path


# --------------------------------------------------
# Extraction
# --------------------------------------------------
def _extract_xml_files(archive_path: Path, limit: int) -> List[Path]:
    if limit == 0:
        return []
    RAW_XML_DIR.mkdir(parents=True, exist_ok=True)
    extracted: List[Path] = []
    
    tar = tarfile.open(archive_path, "r:bz2")
    try:
        for member in tar.getmembers():

            if not _is_safe_path(member.name):
                raise ValueError(f"Unsafe path detected: {member.name}")

            if not member.isfile() or not member.name.endswith(".xml"):
                continue

            if len(extracted) >= limit:
                break

            target = RAW_XML_DIR / os.path.basename(member.name)
            if target.exists():
                extracted.append(target)
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


# --------------------------------------------------
# Public API
# --------------------------------------------------
def fetch_lovdata_files(limit: int = 200) -> Tuple[List[str], str]:
    if limit < 0:
        raise ValueError("limit must be >= 0")

    # ✅ IDENTITY FIX: reuse local archive
    existing = _existing_archive()
    if existing:
    
        xml_files = _extract_xml_files(existing, limit)
   
        return [str(p) for p in xml_files], existing.name

    archive_name = "lovtidend-avd1-2001-2025.tar.bz2"
    print(archive_name)
    archive_path = _download_archive(archive_name)

    xml_files = _extract_xml_files(archive_path, limit)
    return [str(p) for p in xml_files], archive_name