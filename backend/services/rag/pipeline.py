from typing import Any, Dict, List, Tuple
import re


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def build_context(search_results: List[Dict[str, Any]], max_chars: int) -> Tuple[str, Dict[str, Any]]:
    parts = []
    cur = 0
    included = 0
    truncated = 0

    for i, r in enumerate(search_results, 1):
        title = r.get("parent_title") or r.get("file_name") or "Unknown"
        parent_type = r.get("parent_type") or ""
        score = float(r.get("score", 0.0))
        text = (r.get("text") or "").strip()

        header = f"[Source {i} | score={score:.4f} | {parent_type} | {title}]\n"
        chunk = f"{header}{text}\n"

        if cur + len(chunk) > max_chars:
            avail = max_chars - cur - len(header) - 50
            if avail > 200:
                parts.append(f"{header}{text[:avail]}... [truncated]\n")
                truncated += 1
            break

        parts.append(chunk)
        cur += len(chunk)
        included += 1

    context = "\n---\n".join(parts)
    meta = {
        "chunks_included": included,
        "chunks_truncated": truncated,
        "final_context_chars": len(context),
        "estimated_tokens": estimate_tokens(context),
    }
    return context, meta


# -----------------------------
# NEW: helpers for source dedupe
# -----------------------------
_WS_RE = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip())


def _source_dedupe_key(r: Dict[str, Any]) -> tuple:
    """
    Dedup strategy:
    - Prefer URL if present (more stable)
    - Use normalized title + normalized excerpt prefix to catch same content returned twice
    """
    url = _norm(r.get("url") or "")
    title = _norm(r.get("parent_title") or r.get("file_name") or "Unknown")
    text = _norm(r.get("text") or "")
    text_prefix = text[:220]  # enough to detect duplicates reliably
    return (url or title, title, text_prefix)


def format_sources(search_results: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """
    Return ONLY sources from retrieved VDB rows, but eliminate duplicates.
    - url must be exactly the retrieved 'url'
    - include chunk_id and parent metadata so UI can show sources even if URL repeats
    """
    out: List[Dict[str, Any]] = []
    seen = set()

    # important: dedupe BEFORE slicing to k
    for r in (search_results or []):
        key = _source_dedupe_key(r)
        if key in seen:
            continue
        seen.add(key)

        url = (r.get("url") or "").strip()
        text = (r.get("text") or "")
        out.append(
            {
                "title": r.get("parent_title") or r.get("file_name") or "Unknown",
                "url": url,
                "chunk_id": r.get("chunk_id", ""),
                "chunk_text": (text[:240] + "...") if text else "",
                "relevance_score": round(float(r.get("score", 0.0)), 4),
                "metadata": {
                    "file_name": r.get("file_name", ""),
                    "doc_type": r.get("doc_type", ""),
                    "omrade": r.get("omrade", ""),
                    "parent_type": r.get("parent_type", ""),
                    "parent_index": r.get("parent_index", 0),
                    "child_index": r.get("child_index", 0),
                    "chunk_index": r.get("chunk_index", 0),
                    "token_count": r.get("token_count", 0),
                },
            }
        )

        if len(out) >= k:
            break

    return out
