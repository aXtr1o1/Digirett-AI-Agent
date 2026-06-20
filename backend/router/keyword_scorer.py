# backend/router/keyword_scorer.py

from typing import List, Dict, Tuple
from router.taxonomy_loader import taxonomy_loader
from router.query_normalizer import QueryNormalizer

# Common Norwegian and English stop words to ignore in token overlap scoring
STOP_WORDS = {
    # Norwegian
    "og", "i", "jeg", "det", "at", "en", "et", "den", "til", "er", "som", "på", "de", "med", 
    "han", "av", "ikke", "der", "så", "var", "meg", "seg", "men", "ett", "har", "om", "vi", 
    "min", "mitt", "ha", "hadde", "hun", "nå", "over", "da", "ved", "fra", "for", "ut", "sin", 
    "sine", "sitt", "mot", "å", "hva", "hvordan", "hvor", "hvem", "eller",
    # English
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", 
    "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers", "herself", 
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves", "what", "which", 
    "who", "whom", "this", "that", "these", "those", "am", "is", "are", "was", "were", "be", 
    "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an", 
    "the", "and", "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", 
    "with", "about", "against", "between", "into", "through", "during", "before", "after", 
    "above", "below", "to", "up", "down", "off", "under", "again", "further", "then", 
    "once", "here", "there", "when", "why", "how", "all", "any", "both", "each", "few", 
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", 
    "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now"
}

class KeywordScorer:
    
    @classmethod
    def score_query(cls, query_text: str, key_concepts: List[str] = None) -> List[Tuple[str, float]]:
        """
        Scores all subdomains against the user query.
        Also uses Key Concepts (translated/anchored Norwegian terms) from the reasoning agent
        to handle English queries.
        """
        if not query_text:
            return []
 
        # Prepare normalized query tokens and raw clean string
        normalized_query_tokens = QueryNormalizer.normalize(query_text)
        clean_query_str = " ".join(normalized_query_tokens)
 
        # Merge in key concept tokens if present
        concept_tokens = []
        if key_concepts:
            for concept in key_concepts:
                concept_tokens.extend(QueryNormalizer.normalize(concept))
        
        all_query_tokens = set(normalized_query_tokens + concept_tokens)
 
        subdomains = taxonomy_loader.get_all_subdomains()
        scores: Dict[str, float] = {}
 
        for sub_id, sub_data in subdomains.items():
            keywords = sub_data.get("routing_keywords", [])
            if not keywords:
                continue
 
            sub_score = 0.0
            
            for keyword in keywords:
                keyword_lower = keyword.lower()
                keyword_tokens = QueryNormalizer.normalize(keyword_lower)
                
                # Case 1: Exact phrase match (e.g. "stifte aksjeselskap")
                if len(keyword_tokens) > 1:
                    clean_kw_str = " ".join(keyword_tokens)
                    if clean_kw_str in clean_query_str:
                        sub_score += 1.5  # High weight for exact phrase match
                        continue
                
                # Case 2: Individual token overlap (excluding stop words)
                kw_token_set = set(keyword_tokens)
                kw_token_filtered = kw_token_set - STOP_WORDS
                all_query_filtered = all_query_tokens - STOP_WORDS
                
                if not kw_token_filtered:
                    continue
                    
                matching_tokens = kw_token_filtered.intersection(all_query_filtered)
                if matching_tokens:
                    # Score based on fraction of filtered keyword matched
                    sub_score += (len(matching_tokens) / len(kw_token_filtered)) * 0.5
 
            if sub_score > 0:
                scores[sub_id] = sub_score
 
        # Normalize scores to a 0.0 - 1.0 confidence interval
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if not sorted_scores:
            return []
 
        max_score = sorted_scores[0][1]
        normalized_sorted = []
        for sub_id, raw_score in sorted_scores:
            # Scale relative to the highest score, capped at 1.0
            confidence = min(1.0, raw_score / max_score if max_score > 0 else 0.0)
            normalized_sorted.append((sub_id, round(confidence, 2)))
 
        return normalized_sorted

