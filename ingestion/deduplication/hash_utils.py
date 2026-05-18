import hashlib
def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of text content."""
    if not content:
        return ""
    clean_text = " ".join(content.split())
    return hashlib.sha256(clean_text.encode("utf-8")).hexdigest()


def compute_composite_hash(source_name: str, content: str) -> str:
    """Compute SHA-256 hash combining source and content."""
    if not content:
        return ""
    clean_text = " ".join(content.split())
    combined = f"{source_name}::{clean_text}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()
