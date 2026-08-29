import os

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "document_summarizer.txt")

with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
    DOCUMENT_SUMMARIZER_PROMPT = _f.read().strip()
