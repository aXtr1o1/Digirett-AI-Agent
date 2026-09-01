from __future__ import annotations

import re
import urllib.parse
from typing import Optional


def clean_lovdata_url(
    raw_url: Optional[str] = None,
    canon_id: str = "",
    section_number: str = "",
) -> str:
    clean_sec = section_number.replace(" ", "").strip() if section_number else ""

    # If no raw_url provided, construct from canon_id and section_number
    if not raw_url:
        if canon_id:
            if clean_sec and (clean_sec.startswith("§") or clean_sec.startswith("paragraf-")):
                return f"https://lovdata.no/dokument/{canon_id}/{clean_sec}"
            return f"https://lovdata.no/dokument/{canon_id}"
        return ""

    # 1. Unquote percent-encodings
    unquoted = urllib.parse.unquote(str(raw_url)).strip()

    # 2. Strip fragment / anchor hash (#...)
    if "#" in unquoted:
        unquoted = unquoted.split("#")[0].strip()

    # 3. Ensure base prefix https://lovdata.no/dokument/
    if not unquoted.startswith("http"):
        unquoted = f"https://lovdata.no/dokument/{unquoted.lstrip('/')}"

    # 4. Parse URL path components
    parsed = urllib.parse.urlparse(unquoted)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]

    # 5. Remove synthetic suffixes and Roman numerals/list elements
    # (Unstructured regulations only use base URL; Roman numerals and /sec-* 404 on Lovdata)
    roman_and_synthetic = {
        "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
        "del_1", "del_2", "del_3", "del_4", "part_1", "part_2"
    }
    while path_parts and (
        path_parts[-1].lower().startswith("sec-")
        or path_parts[-1].lower().startswith("del_")
        or path_parts[-1].lower().startswith("part-")
        or path_parts[-1].lower() in roman_and_synthetic
    ):
        path_parts.pop()

    # 6. Deduplicate repeated trailing section parts (e.g. ['§3', '§ 3'] or ['§3', '§3'])
    if len(path_parts) >= 2:
        last = path_parts[-1].replace(" ", "").lower()
        second_last = path_parts[-2].replace(" ", "").lower()
        if last and second_last and (
            last == second_last
            or last.strip("§") == second_last.strip("§")
            or f"§{last}" == second_last
            or last == f"§{second_last}"
        ):
            path_parts.pop()

    # Reconstruct clean URL
    clean_path = "/" + "/".join(path_parts)
    return f"{parsed.scheme}://{parsed.netloc}{clean_path}"
