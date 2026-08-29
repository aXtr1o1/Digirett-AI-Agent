import os

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "reranker_prompt.txt")

with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
    RERANKER_PROMPT_TEMPLATE = _f.read().strip()