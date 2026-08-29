"""
Canonical domain enumeration and normalization.

Single source-of-truth for all domain values across:
- QueryReasoningAgent (extraction)
- RouterAgent (routing)
- RetrieverAgent (Milvus filtering)
- Evaluation (metrics)

All domains use LOWERCASE keys, matching Milvus storage.
"""

from typing import Optional, Set

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CANONICAL LOWERCASE DOMAINS (matches Milvus)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DOMAINS_CANONICAL: Set[str] = {
    "arbeidsrett",
    "arsregnskap_og_selskapsrapportering",
    "avtalerett",
    "inkasso_og_tvangsfullbyrdelse",
    "konkursrett_og_insolvens",
    "manda_fusjon_fisjon",
    "obligasjonsrett",
    "panterett_og_sikkerhetsrett",
    "pengekravsrett_fordringer",
    "personvern_gdpr_business_compliance",
    "selskapsrett",
    "tvistelosning_smb",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTER AGENT TITLES → CANONICAL LOWERCASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DOMAIN_ROUTER_TO_CANONICAL = {
    "Arbeidsrett": "arbeidsrett",
    "Arsregnskap_og_selskapsrapportering_dataset": "arsregnskap_og_selskapsrapportering",
    "Avtalerett": "avtalerett",
    "Inkasso_og_tvangsfullbyrdelse_dataset": "inkasso_og_tvangsfullbyrdelse",
    "Konkursrett_og_insolvens_dataset": "konkursrett_og_insolvens",
    "MandA_Fusjon_Fisjon": "manda_fusjon_fisjon",
    "Obligasjonrett": "obligasjonsrett",
    "Panterett_og_sikkerhetsrett_dataset": "panterett_og_sikkerhetsrett",
    "Pengekravsrett_fordringer_dataset": "pengekravsrett_fordringer",
    "Personvern_GDPR_business_compliance_dataset": "personvern_gdpr_business_compliance",
    "Selskapsrett": "selskapsrett",
    "Tvistelosning_SMB_dataset": "tvistelosning_smb",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NORMALIZATION FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def normalize_domain(domain_input: Optional[str]) -> Optional[str]:
    """
    Convert any domain format to canonical lowercase.
    
    Args:
        domain_input: Domain in any format (router title, lowercase, etc.)
        
    Returns:
        Canonical lowercase domain, or None if not recognized.
    """
    if not domain_input:
        return None
    
    domain_str = str(domain_input).strip()
    
    # First try exact router mapping
    if domain_str in DOMAIN_ROUTER_TO_CANONICAL:
        return DOMAIN_ROUTER_TO_CANONICAL[domain_str]
    
    # Try lowercase version
    lowercase = domain_str.lower()
    if lowercase in DOMAINS_CANONICAL:
        return lowercase
    
    # No match
    return None


def is_valid_domain(domain: Optional[str]) -> bool:
    """Check if domain is in canonical set."""
    return domain in DOMAINS_CANONICAL if domain else False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ROUTER FILTER CONFIGURATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VALID_B2B_B2C = frozenset({"B2B", "B2C", "BOTH"})
VALID_REL_TYPES = frozenset({"commercial", "consumer", "employment"})
VALID_JURISDICTIONS = frozenset({"NO", "EU-EEA", "BOTH"})

