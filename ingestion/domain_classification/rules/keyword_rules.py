# """
# domain_classification/rules/keyword_rules.py
# =============================================
# Keyword-based classification engine.
# """

# from __future__ import annotations

# import logging
# import yaml
# from pathlib import Path
# from typing import Any, Dict, Tuple

# logger = logging.getLogger(__name__)

# _CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "domain_rules.yaml"


# class KeywordClassifier:
#     """Classifies text based on keyword matches defined in domain_rules.yaml."""

#     def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
#         self.config_path = config_path
#         self.domains: Dict[str, Any] = {}
#         self.default_domain = "ukjent"
#         self._load_config()

#     def _load_config(self) -> None:
#         if not self.config_path.exists():
#             return
#         try:
#             with open(self.config_path, "r", encoding="utf-8") as f:
#                 data = yaml.safe_load(f)
#             self.domains = data.get("domains", {})
#             self.default_domain = data.get("default_domain", "ukjent")
#         except Exception as exc:
#             logger.error("Failed to load domain rules: %s", exc)

#     def classify(self, text: str) -> Tuple[str, str]:
#         """
#         Scan text for keywords. Return (domain, subdomain) with the most hits.
#         """
#         if not text:
#             return self.default_domain, ""

#         text_lower = text.lower()
#         domain_scores: Dict[str, int] = {}
#         domain_subdomain_scores: Dict[str, Dict[str, int]] = {}

#         for domain, rules in self.domains.items():
#             if domain == "_client_custom": continue # skip placeholder
            
#             score = 0
#             keywords = rules.get("keywords", [])
#             for kw in keywords:
#                 if kw.lower() in text_lower:
#                     score += 1
            
#             domain_scores[domain] = score
            
#             # Check subdomains
#             subdomains = rules.get("subdomains", {})
#             if subdomains:
#                 domain_subdomain_scores[domain] = {}
#                 for sub, sub_kws in subdomains.items():
#                     sub_score = 0
#                     for kw in sub_kws:
#                         if kw.lower() in text_lower:
#                             sub_score += 1
#                     domain_subdomain_scores[domain][sub] = sub_score

#         # Find best domain
#         best_domain = max(domain_scores.items(), key=lambda x: x[1], default=(self.default_domain, 0))
        
#         if best_domain[1] == 0:
#             return self.default_domain, ""

#         final_domain = best_domain[0]
#         final_subdomain = ""

#         # Find best subdomain within the winning domain
#         if final_domain in domain_subdomain_scores:
#             sub_scores = domain_subdomain_scores[final_domain]
#             if sub_scores:
#                 best_sub = max(sub_scores.items(), key=lambda x: x[1])
#                 if best_sub[1] > 0:
#                     final_subdomain = best_sub[0]

#         return final_domain, final_subdomain
