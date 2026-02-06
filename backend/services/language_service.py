"""
app/services/language_service.py
Language detection and intent classification
"""

import logging
from typing import Tuple
import re

logger = logging.getLogger(__name__)


class LanguageService:
    """Detect language and query intent"""
    
    # Norwegian common words
    NORWEGIAN_INDICATORS = {
        'hva', 'hvordan', 'når', 'hvem', 'hvor', 'hvorfor',
        'er', 'jeg', 'du', 'det', 'og', 'i', 'på', 'til',
        'lov', 'forskrift', 'regler', 'paragraf', 'selskap',
        'aksjeselskap', 'virksomhet', 'foretak'
    }
    
    # English common words
    ENGLISH_INDICATORS = {
        'what', 'how', 'when', 'who', 'where', 'why',
        'is', 'are', 'the', 'and', 'in', 'on', 'to',
        'law', 'regulation', 'rules', 'company', 'business'
    }
    
    # Casual conversation triggers (no RAG needed)
    CASUAL_GREETINGS = {
        'hi', 'hello', 'hei', 'hallo', 'hey', 'good morning',
        'good afternoon', 'good evening', 'god morgen', 'god dag'
    }
    
    CASUAL_THANKS = {
        'thanks', 'thank you', 'takk', 'tusen takk', 'mange takk',
        'thank you so much', 'thanks a lot'
    }
    
    CASUAL_GOODBYE = {
        'bye', 'goodbye', 'see you', 'ha det', 'adjø', 'farvel'
    }
    
    def detect_language(self, text: str) -> str:
        """
        Detect if text is Norwegian or English
        
        Args:
            text: Input text
            
        Returns:
            'norwegian' or 'english'
        """
        try:
            text_lower = text.lower()
            words = set(re.findall(r'\b\w+\b', text_lower))
            
            norwegian_score = len(words & self.NORWEGIAN_INDICATORS)
            english_score = len(words & self.ENGLISH_INDICATORS)
            
            # Check for Norwegian-specific characters
            if any(char in text for char in 'æøå'):
                norwegian_score += 2
            
            logger.debug(f"Language scores - Norwegian: {norwegian_score}, English: {english_score}")
            
            return 'norwegian' if norwegian_score >= english_score else 'english'
            
        except Exception as e:
            logger.error(f"Language detection error: {e}")
            return 'norwegian'  # Default to Norwegian
    
    def is_casual_query(self, text: str) -> bool:
        """
        Determine if query is casual (no RAG needed)
        
        Args:
            text: User query
            
        Returns:
            True if casual, False if requires RAG
        """
        try:
            text_lower = text.lower().strip()
            
            # Check for exact matches first
            if text_lower in self.CASUAL_GREETINGS:
                return True
            if text_lower in self.CASUAL_THANKS:
                return True
            if text_lower in self.CASUAL_GOODBYE:
                return True
            
            # Check for partial matches
            for greeting in self.CASUAL_GREETINGS:
                if greeting in text_lower and len(text_lower) < 20:
                    return True
            
            for thanks in self.CASUAL_THANKS:
                if thanks in text_lower and len(text_lower) < 30:
                    return True
            
            # Very short queries (< 4 words) without legal keywords
            words = text_lower.split()
            if len(words) <= 3:
                legal_keywords = {'lov', 'law', 'forskrift', 'regulation', 'selskap', 'company', '§', 'paragraf'}
                if not any(keyword in text_lower for keyword in legal_keywords):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            return False
    
    def classify_query(self, text: str) -> Tuple[str, bool]:
        """
        Classify query: detect language and intent
        
        Args:
            text: User query
            
        Returns:
            Tuple of (language, is_casual)
        """
        language = self.detect_language(text)
        is_casual = self.is_casual_query(text)
        
        logger.info(f"Query classified - Language: {language}, Casual: {is_casual}")
        
        return language, is_casual