# backend/router/taxonomy_loader.py

import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class TaxonomyLoader:
    _instance: Optional["TaxonomyLoader"] = None

    def __new__(cls) -> "TaxonomyLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._domains: Dict[str, Dict[str, Any]] = {}
            self._subdomains: Dict[str, Dict[str, Any]] = {}
            self._initialized = False
            self.load()

    def load(self) -> None:
        try:
            # Find backend directory (two parents up from backend/router/taxonomy_loader.py)
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # Path to the new taxonomy folder inside backend
            taxonomy_dir = os.path.join(backend_dir, "taxonomy")
            
            path_remaining = os.path.join(taxonomy_dir, "taxonomy_remaining_10_domains_v1_1_0.json")
            path_contract_employment = os.path.join(taxonomy_dir, "taxonomy_contract_employment_v1.0.1.json")

            logger.info(f"📂 Loading taxonomy files from: {taxonomy_dir}")
            
            # Read taxonomy remaining 10 domains
            if os.path.exists(path_remaining):
                with open(path_remaining, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._parse_taxonomy_data(data)
            else:
                logger.error(f"❌ Missing taxonomy file: {path_remaining}")

            # Read companion taxonomy (contract and employment)
            if os.path.exists(path_contract_employment):
                with open(path_contract_employment, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._parse_taxonomy_data(data)
            else:
                logger.error(f"❌ Missing taxonomy file: {path_contract_employment}")

            self._initialized = True
            logger.info(
                f"✅ Taxonomy loaded successfully | "
                f"domains={len(self._domains)} | subdomains={len(self._subdomains)}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to load taxonomy data: {e}", exc_info=True)

    def _parse_taxonomy_data(self, data: Dict[str, Any]) -> None:
        domains_list = data.get("domains", [])
        for d in domains_list:
            domain_id = d.get("domain_id")
            if not domain_id:
                continue
            
            if domain_id not in self._domains:
                self._domains[domain_id] = {
                    "domain_id": domain_id,
                    "name_en": d.get("name_en"),
                    "name_nb": d.get("name_nb"),
                    "default": d.get("default", {}),
                    "subdomains": []
                }
            
            subdomains_list = d.get("subdomains", [])
            for sub in subdomains_list:
                subdomain_id = sub.get("subdomain_id")
                if not subdomain_id:
                    continue
                
                # Check for thin pointer / alias notes or attributes
                # Standardize uppercase constraints in parsing
                constraints = sub.get("routing_constraints", {})
                if "b2b_b2c" in constraints and isinstance(constraints["b2b_b2c"], list):
                    constraints["b2b_b2c"] = [v.upper() for v in constraints["b2b_b2c"]]
                if "jurisdiction" in constraints and isinstance(constraints["jurisdiction"], list):
                    constraints["jurisdiction"] = [v.upper() for v in constraints["jurisdiction"]]

                sub_data = {
                    "subdomain_id": subdomain_id,
                    "domain_id": domain_id,
                    "name_en": sub.get("name_en"),
                    "name_nb": sub.get("name_nb"),
                    "scope_in": sub.get("scope_in", []),
                    "scope_out": sub.get("scope_out", []),
                    "routing_constraints": constraints,
                    "routing_keywords": sub.get("routing_keywords", []),
                    "confusers": sub.get("confusers", []),
                    "required_sources": sub.get("required_sources", []),
                    "notes": sub.get("notes", ""),
                    "co_retrieval": sub.get("co_retrieval", {})
                }
                
                self._subdomains[subdomain_id] = sub_data
                if subdomain_id not in self._domains[domain_id]["subdomains"]:
                    self._domains[domain_id]["subdomains"].append(subdomain_id)

    def get_subdomain(self, subdomain_id: str) -> Optional[Dict[str, Any]]:
        return self._subdomains.get(subdomain_id)

    def get_domain(self, domain_id: str) -> Optional[Dict[str, Any]]:
        return self._domains.get(domain_id)

    def get_all_subdomains(self) -> Dict[str, Dict[str, Any]]:
        return self._subdomains

    def get_all_domains(self) -> Dict[str, Dict[str, Any]]:
        return self._domains

# Module level singleton
taxonomy_loader = TaxonomyLoader()
