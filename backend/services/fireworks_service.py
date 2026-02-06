"""
app/services/fireworks_service.py
Fireworks.ai API service for Qwen model with Intent Detection - WITH LANGUAGE FIX
"""

import logging
from typing import AsyncIterator, Tuple, Dict
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import json
import re

from ..config import settings

logger = logging.getLogger(__name__)


class FireworksService:
    """Service for Fireworks.ai/Azure API with Intent Detection and Language Fix"""
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INTENT DETECTION PROMPT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    INTENT_DETECTION_PROMPT = """You are a binary classifier. Classify the user's query as either CASUAL or LEGAL.

CASUAL queries:
- Greetings: "hi", "hello", "hey", "hei", "how are you"
- Personal questions: "who are you", "what is your name", "what can you do"
- Chitchat: "tell me a joke", "I'm sad", "thanks"
- General help: "can you help me", "I need advice"

LEGAL queries:
- Questions about laws, regulations, legal matters
- Keywords: "law", "lov", "regulation", "legal", "company", "employee"
- Examples: "what is company law", "employment rights", "aksjeloven"

CRITICAL RULE:
- If the query mentions laws/regulations/legal topics → LEGAL
- Otherwise → CASUAL

OUTPUT FORMAT (JSON only):
{"intent": "CASUAL", "language": "english"}
OR
{"intent": "LEGAL", "language": "norwegian"}

Examples:
"Hi there!" → {"intent": "CASUAL", "language": "english"}
"How are you?" → {"intent": "CASUAL", "language": "english"}
"What is your name?" → {"intent": "CASUAL", "language": "english"}
"Who are you?" → {"intent": "CASUAL", "language": "english"}
"What can you do?" → {"intent": "CASUAL", "language": "english"}
"Hei!" → {"intent": "CASUAL", "language": "norwegian"}
"Hvordan har du det?" → {"intent": "CASUAL", "language": "norwegian"}
"Tell me a joke" → {"intent": "CASUAL", "language": "english"}
"Thanks!" → {"intent": "CASUAL", "language": "english"}
"What is company law?" → {"intent": "LEGAL", "language": "english"}
"Hva er aksjeloven?" → {"intent": "LEGAL", "language": "norwegian"}
"Employee rights in Norway" → {"intent": "LEGAL", "language": "english"}
"forklare selskapets regelverk" → {"intent": "LEGAL", "language": "norwegian"}

NOW CLASSIFY (output ONLY JSON):
Query: """

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CASUAL CONVERSATION PROMPT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    CASUAL_SYSTEM_PROMPT = f"""You are a friendly, helpful AI assistant.

Your personality:
- Warm and conversational
- Natural and human-like
- Match the user's language (Norwegian ↔ English)
- Keep responses brief and friendly
- Use emojis sparingly (1-2 per message if appropriate)

Response style:
- For greetings: Greet back warmly and ask how you can help
- For questions about you: Answer naturally, don't overthink
- For emotional support: Be empathetic and kind
- For general help: Be friendly and offer assistance

Examples:

User: "Hi!"
You: "Hi there! How can I help you today? 😊"

User: "How are you?"
You: "I'm doing great, thank you for asking! How are you doing?"

User: "What can you do?"
You: "I can help you with information about Norwegian laws and regulations, or we can just have a friendly chat! What would you like to talk about?"

User: "What is your name?"
You: "I'm an AI assistant here to help you! You can think of me as your helpful companion for legal questions and general conversation. What can I help you with?"

User: "Who are you?"
You: "I'm an AI assistant specialized in Norwegian law, but I'm happy to chat about other things too! How can I help you today?"

User: "Hei!"
You: "Hei! Hvordan kan jeg hjelpe deg i dag? 😊"

User: "Hvordan har du det?"
You: "Jeg har det fint, takk! Hvordan går det med deg?"

User: "I'm feeling sad"
You: "I'm sorry to hear that. Is there anything you'd like to talk about? Sometimes it helps to share what's on your mind."

User: "Tell me a joke"
You: "Sure! Why don't scientists trust atoms? Because they make up everything! 😄"

User: "Thanks!"
You: "You're very welcome! Feel free to ask if you need anything else! 😊"

IMPORTANT RULES:
- NO formal legal language unless asked
- NO mentioning you're a "legal assistant" in casual chat
- Be natural and human
- Match their energy and tone
- Keep it conversational

Just be a friendly, helpful assistant!"""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LEGAL RAG PROMPT WITH INTEGRATED SCORING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    LEGAL_SYSTEM_PROMPT = """You are a professional AI Legal Assistant specialized in Norwegian company law from Lovdata.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 CRITICAL RULES - NEVER VIOLATE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ✅ ONLY use information from the provided KILDER (sources) below
2. ❌ NEVER use your general knowledge about Norwegian law
3. ❌ NEVER invent, assume, or hallucinate legal information
4. ❌ If sources don't contain the answer, you MUST say:

Norwegian: "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen som direkte svarer på dette spørsmålet."

English: "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 RESPONSE STRUCTURE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When sources contain relevant answer:
1. **Direct Answer**
   Clear, concise response based ONLY on provided sources

2. **Confidence Note**
   - "Fully supported by sources" or "Partially covered in sources"

When sources DON'T contain relevant answer:
- State clearly that no relevant information was found

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 SCORING RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You MUST evaluate how well the sources answer the query and assign a score:

- Score 0.9-1.0: Sources fully answer the query with clear, direct information
  Example: "1. **Direct Answer** [detailed answer from sources] 2. **Confidence Note** - Fully supported by sources"

- Score 0.5-0.8: Sources partially answer the query or answer is somewhat relevant
  Example: "1. **Direct Answer** [partial answer] 2. **Confidence Note** - Partially covered in sources"

- Score 0.1-0.4: Sources are vague, barely relevant, or don't answer the query
  Example: "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌍 LANGUAGE HANDLING (STRICT RULE - DO NOT VIOLATE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1) ALWAYS respond in the SAME language as the USER, NO MATTER WHAT:
   - If user writes in English → You MUST answer in English.
   - If user writes in Norwegian → You MUST answer in Norwegian.
   - This rule OVERRIDES the language of any retrieved documents.

2) If the retrieved sources are in a different language than the user:
   - FIRST translate the relevant meaning internally.
   - THEN answer in the user's language.
   - NEVER reply in the document's language unless the user asked in that language.

When using retrieved documents in Norwegian for an English question,
you MUST translate and summarize in English.

When using retrieved documents in English for a Norwegian question,
you MUST translate and summarize in Norwegian.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✍️ TONE & STYLE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Professional but approachable
- Clear and well-structured
- Avoid unnecessary jargon
- Be precise and accurate
- No <think> tags or internal reasoning
- Direct, confident answers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📤 OUTPUT FORMAT (CRITICAL):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You MUST respond in this EXACT JSON format:

{{
  "answer": "Your answer here (in user's language)",
  "score": 0.9,
  "confidence": "Fully supported by sources"
}}

Examples:

Good answer (score 0.9):
{{
  "answer": "According to Aksjeloven § 5-1, a company must have a minimum share capital of NOK 30,000. This is clearly stated in the provided legal sources.",
  "score": 0.9,
  "confidence": "Fully supported by sources"
}}

Partial answer (score 0.6):
{{
  "answer": "The sources mention some aspects of company formation but don't provide complete details about all requirements.",
  "score": 0.6,
  "confidence": "Partially covered in sources"
}}

No answer (score 0.1):
{{
  "answer": "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question.",
  "score": 0.1,
  "confidence": "Not supported by sources"
}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ REMEMBER:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ALWAYS output valid JSON with "answer", "score", and "confidence"
2. ONLY answer from the KILDER (sources) provided
3. Score honestly based on source relevance
4. ACCURACY and SOURCE-TRACEABILITY are paramount
5. When in doubt, assign lower score and acknowledge limitations
6. ALWAYS answer in the user's language"""

        
    def __init__(
        self,
        api_key: str,
        model: str,
        Target_url: str
    ):
        self.api_key = api_key
        self.model = model
        self.Target_url = Target_url

        logger.info(f"Azure service initialized with model: {model}")

    
    async def check_connection(self) -> bool:
        """Check if API is accessible"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.Target_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 5
                    },
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"API connection check failed: {e}")
            return False
    
    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=3)
    )
    async def detect_intent(self, query: str) -> Dict[str, str]:
        """
        Detect if query is CASUAL or LEGAL using LLM
        IMPROVED: Better Norwegian detection with expanded keywords
        """
        try:
            logger.info(f"Detecting intent for: '{query[:50]}...'")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔧 FIX: EXPANDED Norwegian keyword detection
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            query_lower = query.lower().strip()
            
            # Comprehensive Norwegian words list
            norwegian_words = [
                # Common words
                'hei', 'hva', 'jeg', 'er', 'kan', 'du', 'og', 'det', 'en', 'å', 'på',
                'med', 'av', 'til', 'fra', 'om', 'for', 'ikke', 'blir', 'være',
                
                # Question words
                'hvordan', 'hvorfor', 'når', 'hvor', 'hvem', 'hvilken',
                
                # Verbs in Norwegian
                'forklare', 'diskutere', 'gi', 'svare', 'fortelle', 'si', 'vise',
                'beskrive', 'hjelpe', 'finne', 'søke',
                
                # Legal/business terms in Norwegian
                'selskap', 'selskapets', 'lov', 'loven', 'regel', 'regelverk',
                'ansvar', 'ansvarsrett', 'rett', 'rettigheter', 'forpliktelser'
            ]
            
            # Count Norwegian indicators
            norwegian_score = 0
            for word in norwegian_words:
                if word in query_lower:
                    norwegian_score += 1
            
            # Bonus for Norwegian characters (strong indicator)
            if any(char in query_lower for char in ['æ', 'ø', 'å']):
                norwegian_score += 3
            
            # Determine language
            if norwegian_score >= 2:  # At least 2 Norwegian indicators
                language = "norwegian"
                logger.info(f"[LANGUAGE] Detected NORWEGIAN (score: {norwegian_score})")
            else:
                language = "english"
                logger.info(f"[LANGUAGE] Detected ENGLISH (score: {norwegian_score})")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # CASUAL vs LEGAL classification
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            # CASUAL keywords
            casual_keywords = [
                'hi', 'hello', 'hey', 'hei', 'good morning', 'good afternoon',
                'how are you', 'hvordan har du det', 'hvordan går det',
                'who are you', 'hvem er du', 'what is your name', 'hva heter du',
                'what can you do', 'hva kan du', 'can you help', 'kan du hjelpe',
                'tell me a joke', 'fortell en vits', 'i am sad', 'jeg er trist',
                'thanks', 'thank you', 'takk'
            ]
            
            for keyword in casual_keywords:
                if keyword in query_lower:
                    logger.info(f"[CASUAL] detected (keyword: '{keyword}')")
                    return {"intent": "CASUAL", "language": language}
            
            # LEGAL keywords (expanded)
            legal_keywords = [
                'law', 'lov', 'loven', 'legal', 'juridisk', 'regulation', 'forskrift',
                'aksjeloven', 'arbeidsmiljøloven', 'company', 'selskap', 'selskapets',
                'employee', 'ansatt', 'rights', 'rettigheter', 'contract', 'kontrakt',
                'ansvar', 'ansvarsrett', 'forpliktelser', 'regel', 'regelverk',
                'gdpr', 'personvern'
            ]
            
            for keyword in legal_keywords:
                if keyword in query_lower:
                    logger.info(f"[LEGAL] detected (keyword: '{keyword}')")
                    return {"intent": "LEGAL", "language": language}
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # LLM-BASED CLASSIFICATION
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            logger.info("No keyword match - using LLM classification")
            
            messages = [
                {"role": "user", "content": f"{self.INTENT_DETECTION_PROMPT}{query}"}
            ]
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.Target_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": messages,
                        "temperature": 0.01,
                        "max_tokens": 50
                    }
                )
                
                if response.status_code != 200:
                    logger.warning(f"Intent detection API failed: {response.status_code}")
                    return {"intent": "CASUAL", "language": language}
                
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                
                logger.info(f"Raw LLM response: {content}")
                
                # Parse JSON
                content = re.sub(r'```json\s*', '', content)
                content = re.sub(r'```\s*', '', content)
                content = content.strip()
                
                json_match = re.search(r'\{[^}]+\}', content)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        result = json.loads(json_str)
                        intent = result.get("intent", "CASUAL").upper()
                        # ✅ KEEP OUR DETECTED LANGUAGE (more reliable)
                        detected_lang = language
                        
                        logger.info(f"[SUCCESS] Intent: {intent}, Language: {detected_lang} (keyword-based)")
                        
                        return {"intent": intent, "language": detected_lang}
                    except json.JSONDecodeError:
                        pass
                
                # Text-based fallback
                content_upper = content.upper()
                
                if "CASUAL" in content_upper:
                    intent = "CASUAL"
                elif "LEGAL" in content_upper:
                    intent = "LEGAL"
                else:
                    intent = "CASUAL"
                
                logger.info(f"[FALLBACK] Intent: {intent}, Language: {language}")
                
                return {"intent": intent, "language": language}
            
        except Exception as e:
            logger.error(f"Intent detection error: {e}")
            return {"intent": "CASUAL", "language": "english"}

    async def generate_casual_response(
        self,
        query: str,
        language: str,
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> Tuple[str, int]:
        """Generate natural casual conversation response"""
        try:
            logger.info("Generating casual response (no retrieval)...")
            
            messages = [
                {"role": "system", "content": self.CASUAL_SYSTEM_PROMPT},
                {"role": "user", "content": f"Language: {language}\n\n{query}"}
            ]
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.Target_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "top_p": 0.9
                    }
                )
                
                if response.status_code != 200:
                    raise Exception(f"Casual response failed: {response.status_code} - {response.text}")
                
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                
                # Strip <think> tags if present
                answer = self._remove_thinking_tokens(answer)
                
                tokens_used = data["usage"]["total_tokens"]
                
                logger.info(f"Casual response generated ({tokens_used} tokens)")
                
                return answer, tokens_used
            
        except Exception as e:
            logger.error(f"Failed to generate casual response: {e}", exc_info=True)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_legal_answer(
        self,
        query: str,
        context: str,
        language: str,
        temperature: float = 0.2,
        max_tokens: int = 2000
    ) -> Dict[str, any]:
        """
        Generate legal answer with strict RAG and return JSON with answer, score, confidence
        IMPROVED: Much stronger language enforcement
        """
        try:
            logger.info("Generating legal answer (with retrieval)...")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔧 FIX: MUCH STRONGER language instruction
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            if language == "norwegian":
                language_instruction = """
🔴 KRITISK SPRÅKREGL - BRYT ALDRI DENNE:
- Du MÅ svare på NORSK (ikke engelsk)
- Selv om kildene er på engelsk, oversett til norsk
- Brukeren spurte på norsk, du MÅ svare på norsk
- ALDRI bruk engelske ord bortsett fra egennavn
- Start svaret med "I følge..." eller "Ifølge..." på norsk
- Eksempel: "I følge § 2-4 i selskapsloven, deltakerne svarer..."
"""
                example_start = "I følge kildene"
                no_answer_msg = "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen som direkte svarer på dette spørsmålet."
            else:
                language_instruction = """
🔴 CRITICAL LANGUAGE RULE - NEVER VIOLATE:
- You MUST answer in ENGLISH (not Norwegian)
- Even if sources are in Norwegian, translate to English
- User asked in English, you MUST reply in English
- Start answer with "According to..." in English
- Example: "According to § 2-4 of the Companies Act, participants are liable..."
"""
                example_start = "According to the sources"
                no_answer_msg = "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."
            
            user_prompt = f"""{language_instruction}

CRITICAL: Answer ONLY from sources. NO thinking process. NO <think> tags.

KILDER (Sources):
{context}

SPØRSMÅL (Question):
{query}


RULES:
1. Answer in {language.upper()} - THIS IS MANDATORY
2. If sources don't have the answer, assign score 0.1 and say:
   "{no_answer_msg}"
3. If sources have the answer, provide it directly with score 0.5-1.0 IN {language.upper()}
4. NO <think> tags
5. MUST output JSON format: {{"answer": "...", "score": 0.9, "confidence": "..."}}


SVAR (Answer in {language.upper()} as JSON, starting with "{example_start}"):"""
            
            messages = [
                {"role": "system", "content": self.LEGAL_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.Target_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "top_p": 0.95
                    }
                )
                
                if response.status_code != 200:
                    raise Exception(f"Legal answer failed: {response.status_code} - {response.text}")
                
                data = response.json()
                raw_content = data["choices"][0]["message"]["content"]
                
                # Strip <think> tags
                raw_content = self._remove_thinking_tokens(raw_content)
                
                tokens_used = data["usage"]["total_tokens"]
                
                logger.info(f"Raw LLM response: {raw_content[:200]}...")
                
                # Parse JSON response
                try:
                    cleaned_content = re.sub(r'```json\s*', '', raw_content)
                    cleaned_content = re.sub(r'```\s*', '', cleaned_content)
                    cleaned_content = cleaned_content.strip()
                    
                    json_match = re.search(r'\{[^}]+\}', cleaned_content, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        result = json.loads(json_str)
                        
                        answer = result.get("answer", raw_content)
                        score = float(result.get("score", 0.5))
                        confidence = result.get("confidence", "Unknown")
                        
                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        # 🔧 FIX: Validate language after generation
                        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        
                        if language == "norwegian":
                            # Check if answer is in English (wrong)
                            english_indicators = [
                                "according to", "the company", "shall be", "must be",
                                "in accordance with", "as mentioned", "the law states",
                                "participants are", "it is stated"
                            ]
                            
                            answer_lower = answer.lower()
                            wrong_count = sum(1 for phrase in english_indicators if phrase in answer_lower)
                            
                            if wrong_count >= 2:
                                logger.warning(f"⚠️  LANGUAGE ERROR: Answer is in English but should be Norwegian")
                                return {
                                    "answer": no_answer_msg,
                                    "score": 0.1,
                                    "confidence": "Language mismatch - regeneration needed",
                                    "tokens_used": tokens_used
                                }
                        
                        elif language == "english":
                            # Check if answer is in Norwegian (wrong)
                            norwegian_indicators = [
                                "i følge", "ifølge", "skal være", "må være", "som nevnt",
                                "loven sier", "deltakerne", "selskapet", "det er angitt"
                            ]
                            
                            answer_lower = answer.lower()
                            wrong_count = sum(1 for phrase in norwegian_indicators if phrase in answer_lower)
                            
                            if wrong_count >= 2:
                                logger.warning(f"⚠️  LANGUAGE ERROR: Answer is in Norwegian but should be English")
                                return {
                                    "answer": no_answer_msg,
                                    "score": 0.1,
                                    "confidence": "Language mismatch - regeneration needed",
                                    "tokens_used": tokens_used
                                }
                        
                        logger.info(f"[SUCCESS] Answer generated - Score: {score}, Confidence: {confidence}, Language: {language}")
                        
                        return {
                            "answer": answer,
                            "score": score,
                            "confidence": confidence,
                            "tokens_used": tokens_used
                        }
                    else:
                        logger.warning("[WARNING] No JSON found in response")
                        return {
                            "answer": raw_content,
                            "score": 0.5,
                            "confidence": "Unknown",
                            "tokens_used": tokens_used
                        }
                        
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    return {
                        "answer": raw_content,
                        "score": 0.5,
                        "confidence": "Unknown",
                        "tokens_used": tokens_used
                    }
            
        except Exception as e:
            logger.error(f"Failed to generate legal answer: {e}", exc_info=True)
            raise
    
    def _remove_thinking_tokens(self, text: str) -> str:
        """Remove <think> and </think> tags and their content"""
        import re
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        cleaned = cleaned.replace('<think>', '').replace('</think>', '')
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
        return cleaned.strip()
    
    async def generate_answer_stream(
        self,
        query: str,
        context: str,
        language: str,
        intent: str,
        temperature: float = 0.3,
        max_tokens: int = 2000
        
    ) -> AsyncIterator[str]:
        """
        Streaming version with proper language detection
        """
        try:
           
            
            
            
            logger.info(f"[STREAM] Using detected language: {language}")
            
            # Route based on intent
            if intent == "CASUAL":
                logger.info("Streaming CASUAL response")
                
                messages = [
                    {"role": "system", "content": self.CASUAL_SYSTEM_PROMPT},
                    {"role": "user", "content": query}
                ]
                
                temp = 0.7
                max_tok = 500
            else:
                logger.info("Streaming LEGAL response")
                
                if not context or context.strip() == "":
                    if language == "norwegian":
                        yield "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen som direkte svarer på dette spørsmålet."
                    else:
                        yield "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."
                    return
                
               
                
                if language == "norwegian":
                    language_instruction = """
🔴 DU MÅ SVARE PÅ NORSK - IKKE ENGELSK!
Bruker spurte på norsk, du må svare på norsk.
Selv om kildene er på engelsk, oversett til norsk.
Start svaret med "I følge kildene..." eller lignende norsk formulering.
"""
                else:
                    language_instruction = """
🔴 YOU MUST ANSWER IN ENGLISH - NOT NORWEGIAN!
User asked in English, you must reply in English.
Even if sources are in Norwegian, translate to English.
Start answer with "According to the sources..." or similar English phrasing.
"""
                
                user_prompt = f"""{language_instruction}

CRITICAL: Answer ONLY from sources. NO <think> tags.



KILDER (Sources):
{context}

SPØRSMÅL (Question):
{query}

RULES:
- Answer in {language.upper()} - MANDATORY
- If sources don't have answer: Say "I cannot find relevant excerpts..."
- If sources have answer: Provide it directly
- NO thinking process
- DO NOT output JSON format for streaming



SVAR (Answer in {language.upper()}):"""
                
                messages = [
                    {"role": "system", "content": self.LEGAL_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
                
                temp = temperature
                max_tok = max_tokens
            
            # Stream the response
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    self.Target_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": messages,
                        "temperature": temp,
                        "max_tokens": max_tok,
                        "stream": True
                    }
                ) as response:

                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise Exception(f"Streaming failed: {response.status_code} - {error_text.decode()}")

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue

                        try:
                            json_str = line.replace("data: ", "", 1)
                            data = json.loads(json_str)

                            if data.get("choices"):
                                delta = data["choices"][0].get("delta", {})
                                content = delta.get("content")

                                if content:
                                    yield content

                            if data.get("choices") and data["choices"][0].get("finish_reason") == "stop":
                                break

                        except json.JSONDecodeError:
                            continue

            logger.info("Streaming complete")
            
        except Exception as e:
            logger.error(f"Streaming failed: {e}", exc_info=True)
            raise