# backend/router/deterministic_rules.py

import re
from typing import Optional

class DeterministicRules:
    
    @staticmethod
    def evaluate(query: str) -> Optional[str]:
        if not query:
            return None
            
        q_lower = query.lower()

        # ── 1. Foreldelse routing ──
        if "foreldelse" in q_lower or "foreldet" in q_lower:
            # Check if it has a reclamation context first
            if "reklamasjon" in q_lower or "reklamasjonsfrist" in q_lower:
                # Let it match OB-02 which has a co-retrieval rule to DC-04
                return "OB-02"
            return "DC-04"

        # ── 2. Cookies vs contract eCom ──
        cookie_signals = ["cookies", "informasjonskapsler", "cookie-banner", "sporing", "tracking"]
        if any(sig in q_lower for sig in cookie_signals):
            return "PR-08"

        # ── 3. Oppsigelse/Termination boundary ──
        breach_signals = ["mislighold", "heving", "erstatning", "mangel", "defekt", "leverte ikke", "forsinket", "ødelagt", "skadet"]
        ordinary_termination_signals = ["si opp", "oppsigelsestid", "oppsigelsesklausul", "automatisk fornyelse"]
        
        # If breach context is present, route to OB-01 (Breach remedy)
        if any(sig in q_lower for sig in breach_signals):
            return "OB-01"

        # Ordinary contract termination without breach
        if any(sig in q_lower for sig in ordinary_termination_signals):
            # If it's about employee dismissal, route to EL-02 instead
            if any(emp in q_lower for emp in ["ansatt", "arbeidstaker", "arbeidsforhold", "arbeidsavtale", "oppsigelse av ansatt"]):
                return "EL-02"
            return "OB-05"

        # ── 4. Insolvency boundary ──
        bankruptcy_signals = ["oppbud begjært", "konkurs åpnet", "bobestyrer", "konkursbo", "slå konkurs", "begjære konkurs"]
        if any(sig in q_lower for sig in bankruptcy_signals):
            return "IN-01"

        # ── 5. Employment injunction vs commercial injunction ──
        employment_inj_signals = ["stå i stilling", "gjeninntreden", "fratreden"]
        if any(sig in q_lower for sig in employment_inj_signals):
            return "EL-05"

        # ── 6. Standalone VO boundary ──
        if any(sig in q_lower for sig in ["selge virksomhet", "salg av virksomhet", "selger virksomheten"]):
            if "fusjon" not in q_lower and "fisjon" not in q_lower:
                return "EL-04"

        return None
 