"""
router/taxonomy_loader.py — Dynamic Glob Taxonomy Loader with Pydantic Schema Validation
"""

import copy
import glob
import json
import logging
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SubdomainSchema(BaseModel):
    subdomain_id: str = Field(min_length=3)
    name_en: Optional[str] = None
    name_nb: Optional[str] = None


class DomainSchema(BaseModel):
    domain_id: str = Field(min_length=2)
    subdomains: List[SubdomainSchema] = Field(default_factory=list)


class TaxonomySchema(BaseModel):
    version: Optional[str] = "1.0.0"
    domains: List[DomainSchema] = Field(default_factory=list)


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
            self._aliases: Dict[str, str] = {}
            self._initialized = False
            self.load()

    def load(self) -> None:
        try:
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            taxonomy_dir = os.path.join(backend_dir, "taxonomy")
            json_files = glob.glob(os.path.join(taxonomy_dir, "*.json"))

            logger.info(f"📂 Loading taxonomy files dynamically from: {taxonomy_dir} ({len(json_files)} files found)")

            for file_path in sorted(json_files):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                    # Validate schema
                    validated = TaxonomySchema(**raw_data)
                    self._parse_taxonomy_data(raw_data, validated.version)
                except Exception as file_exc:
                    logger.error(f"❌ Failed to parse/validate taxonomy file '{os.path.basename(file_path)}': {file_exc}")

            self._initialized = True
            logger.info(
                f"✅ Taxonomy loaded successfully | "
                f"domains={len(self._domains)} | subdomains={len(self._subdomains)} | aliases={len(self._aliases)}"
            )
        except Exception as e:
            logger.error(f"❌ Failed to load taxonomy data: {e}", exc_info=True)

    def reload(self) -> None:
        """Development helper to re-read taxonomy JSONs from disk without app restart."""
        self._domains.clear()
        self._subdomains.clear()
        self._aliases.clear()
        self._initialized = False
        self.load()

    def _parse_taxonomy_data(self, data: Dict[str, Any], version: Optional[str]) -> None:
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
                    "subdomains": [],
                    "version": version,
                }

            subdomains_list = d.get("subdomains", [])
            for sub in subdomains_list:
                subdomain_id = sub.get("subdomain_id")
                if not subdomain_id:
                    continue

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
                    "thin_pointers": sub.get("thin_pointers", []),
                    "notes": sub.get("notes", ""),
                }

                # Check aliases
                aliases = sub.get("aliases", [])
                for alias in aliases:
                    if isinstance(alias, str):
                        self._aliases[alias] = subdomain_id

                self._subdomains[subdomain_id] = sub_data
                if subdomain_id not in self._domains[domain_id]["subdomains"]:
                    self._domains[domain_id]["subdomains"].append(subdomain_id)

    def get_domain(self, domain_id: str) -> Optional[Dict[str, Any]]:
        d = self._domains.get(domain_id)
        return copy.deepcopy(d) if d else None

    def get_subdomain(self, subdomain_id: str) -> Optional[Dict[str, Any]]:
        s = self._subdomains.get(subdomain_id)
        return copy.deepcopy(s) if s else None

    def get_all_subdomains(self) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(self._subdomains)

    def get_all_domains(self) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(self._domains)

    def get_aliases(self) -> Dict[str, str]:
        # Include legacy hardcoded MO-04 -> DC-04 alias if not already in JSON
        res = dict(self._aliases)
        if "MO-04" not in res:
            res["MO-04"] = "DC-04"
        return res


taxonomy_loader = TaxonomyLoader()