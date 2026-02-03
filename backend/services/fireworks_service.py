"""
app/services/fireworks_service.py
Fireworks.ai API service for Qwen model with Intent Detection - UPDATED WITH SCORING
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
    """Service for Fireworks.ai API with Qwen model and Intent Detection"""
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SIMPLIFIED INTENT DETECTION PROMPT (Works better with Qwen)
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

NOW CLASSIFY (output ONLY JSON):
Query: """

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CASUAL CONVERSATION PROMPT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    CASUAL_SYSTEM_PROMPT = """You are a friendly, helpful AI assistant.

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
🌍 LANGUAGE HANDLING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Automatically detect user's language
- Respond in the SAME language:
  • Norwegian query → Norwegian response
  • English query → English response

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
5. When in doubt, assign lower score and acknowledge limitations"""

        
    def __init__(
        self,
        api_key: str,
        model: str = "accounts/fireworks/models/qwen3-8b"
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.fireworks.ai/inference/v1/chat/completions"
        
        logger.info(f"Fireworks service initialized with model: {model}")
    
    async def check_connection(self) -> bool:
        """Check if Fireworks API is accessible"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 5
                    },
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Fireworks connection check failed: {e}")
            return False
    
    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=3)
    )
    async def detect_intent(self, query: str) -> Dict[str, str]:
        """
        Detect if query is CASUAL or LEGAL using LLM
        IMPROVED: Better parsing and keyword fallback
        """
        try:
            logger.info(f"Detecting intent for: '{query[:50]}...'")
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # KEYWORD-BASED FALLBACK (Fast classification for common cases)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            query_lower = query.lower().strip()
            
            # Detect language first
            norwegian_words = ['hei', 'hva', 'jeg', 'er', 'kan', 'du', 'og', 'det', 'en', 'å', 'på']
            is_norwegian = any(word in query_lower.split() for word in norwegian_words)
            language = "norwegian" if is_norwegian else "english"
            
            # CASUAL keywords (high confidence)
            casual_keywords = [
                'hi', 'hello', 'hey', 'hei', 'good morning', 'good afternoon',
                'how are you', 'hvordan har du det', 'hvordan går det',
                'who are you', 'hvem er du', 'what is your name', 'hva heter du',
                'what can you do', 'hva kan du', 'can you help', 'kan du hjelpe',
                'tell me a joke', 'fortell en vits', 'i am sad', 'jeg er trist',
                'thanks', 'thank you', 'takk'
            ]
            
            # Check for exact casual matches
            for keyword in casual_keywords:
                if keyword in query_lower:
                    logger.info(f"[CASUAL] detected (keyword: '{keyword}')")
                    return {"intent": "CASUAL", "language": language}
            
            # LEGAL keywords (high confidence)
            legal_keywords = [
                'law', 'lov', 'loven', 'legal', 'juridisk', 'regulation', 'forskrift',
                'aksjeloven', 'arbeidsmiljøloven', 'company', 'selskap', 'employee', 'ansatt',
                'rights', 'rettigheter', 'contract', 'kontrakt', 'gdpr', 'personvern'
            ]
            
            # Check for exact legal matches
            for keyword in legal_keywords:
                if keyword in query_lower:
                    logger.info(f"[LEGAL] detected (keyword: '{keyword}')")
                    return {"intent": "LEGAL", "language": language}
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # LLM-BASED CLASSIFICATION (For unclear cases)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            messages = [
                {"role": "user", "content": f"{self.INTENT_DETECTION_PROMPT}{query}"}
            ]
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.01,  # Very low for strict classification
                        "max_tokens": 50
                    }
                )
                
                if response.status_code != 200:
                    logger.warning(f"Intent detection API failed: {response.status_code}")
                    # Default to CASUAL if API fails
                    return {"intent": "CASUAL", "language": language}
                
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                
                logger.info(f"Raw LLM response: {content}")
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # ROBUST JSON PARSING
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                
                # Remove markdown code blocks
                content = re.sub(r'```json\s*', '', content)
                content = re.sub(r'```\s*', '', content)
                content = content.strip()
                
                # Try to extract JSON from the response
                json_match = re.search(r'\{[^}]+\}', content)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        result = json.loads(json_str)
                        intent = result.get("intent", "CASUAL").upper()
                        detected_lang = result.get("language", language).lower()
                        
                        logger.info(f"[SUCCESS] JSON parsed: {intent}, {detected_lang}")
                        
                        return {
                            "intent": intent,
                            "language": detected_lang
                        }
                    except json.JSONDecodeError:
                        pass
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # TEXT-BASED FALLBACK
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                
                content_upper = content.upper()
                
                if "CASUAL" in content_upper:
                    intent = "CASUAL"
                elif "LEGAL" in content_upper:
                    intent = "LEGAL"
                else:
                    # Ultimate fallback: Default to CASUAL for friendly experience
                    intent = "CASUAL"
                
                logger.info(f"[WARNING] Fallback classification: {intent}, {language}")
                
                return {
                    "intent": intent,
                    "language": language
                }
            
        except Exception as e:
            logger.error(f"Intent detection error: {e}")
            # Default to CASUAL to avoid forcing retrieval on errors
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
                {"role": "user", "content": query}
            ]
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
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
        """
        try:
            logger.info("Generating legal answer (with retrieval)...")
            
            # Build strict RAG prompt
            user_prompt = f"""CRITICAL: Answer ONLY from sources. NO thinking process. NO <think> tags.

KILDER (Sources):
{context}

SPØRSMÅL (Question):
{query}

RULES:
- If sources don't have the answer, assign score 0.1 and say: "I cannot find relevant legal excerpts..."
- If sources have the answer, provide it directly with score 0.5-1.0
- NO <think> tags
- Respond in SAME LANGUAGE as question
- MUST output JSON format: {{"answer": "...", "score": 0.9, "confidence": "..."}}

SVAR (Answer in JSON):"""
            
            messages = [
                {"role": "system", "content": self.LEGAL_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
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
                
                # Strip <think> tags if present
                raw_content = self._remove_thinking_tokens(raw_content)
                
                tokens_used = data["usage"]["total_tokens"]
                
                logger.info(f"Raw LLM response: {raw_content[:200]}...")
                
                # Parse JSON response
                try:
                    # Remove markdown code blocks if present
                    cleaned_content = re.sub(r'```json\s*', '', raw_content)
                    cleaned_content = re.sub(r'```\s*', '', cleaned_content)
                    cleaned_content = cleaned_content.strip()
                    
                    # Try to extract JSON
                    json_match = re.search(r'\{[^}]+\}', cleaned_content, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        result = json.loads(json_str)
                        
                        answer = result.get("answer", raw_content)
                        score = float(result.get("score", 0.5))
                        confidence = result.get("confidence", "Unknown")
                        
                        logger.info(f"[SUCCESS] JSON parsed - Score: {score}, Confidence: {confidence}")
                        
                        return {
                            "answer": answer,
                            "score": score,
                            "confidence": confidence,
                            "tokens_used": tokens_used
                        }
                    else:
                        # Fallback: No JSON found, use raw content
                        logger.warning("[WARNING] No JSON found in response, using raw content")
                        return {
                            "answer": raw_content,
                            "score": 0.5,  # Default medium score
                            "confidence": "Unknown",
                            "tokens_used": tokens_used
                        }
                        
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    # Fallback: Return raw content with default score
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
        # Remove everything between <think> and </think>
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Remove standalone tags if any
        cleaned = cleaned.replace('<think>', '').replace('</think>', '')
        # Clean up extra whitespace
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
        return cleaned.strip()
    
    async def generate_answer_stream(
        self,
        query: str,
        context: str,
        language: str,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> AsyncIterator[str]:
        """
        Streaming version - streams tokens directly without JSON wrapping
        Note: Scoring is done after streaming completes
        """
        try:
            # Detect intent
            intent_result = await self.detect_intent(query)
            intent = intent_result["intent"]
            detected_language = intent_result["language"]
            
            if not language or language == "auto":
                language = detected_language
            
            # Route based on intent
            if intent == "CASUAL":
                # Stream casual response
                logger.info("Streaming CASUAL response")
                
                messages = [
                    {"role": "system", "content": self.CASUAL_SYSTEM_PROMPT},
                    {"role": "user", "content": query}
                ]
                
                temp = 0.7
                max_tok = 500
            else:
                # Stream legal response
                logger.info("Streaming LEGAL response")
                
                if not context or context.strip() == "":
                    if language == "norwegian":
                        yield "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen som direkte svarer på dette spørsmålet."
                    else:
                        yield "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."
                    return
                
                # For streaming, we don't use JSON format - just stream the answer
                user_prompt = f"""CRITICAL: Answer ONLY from sources. NO <think> tags.

KILDER (Sources):
{context}

SPØRSMÅL (Question):
{query}

RULES:
- If sources don't have answer: "I cannot find relevant legal excerpts..."
- If sources have answer: Provide it directly
- NO thinking process
- Respond in SAME LANGUAGE
- DO NOT output JSON format for streaming

SVAR (Answer):"""
                
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
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temp,
                        "max_tokens": max_tok,
                        "stream": True
                    }
                ) as response:
                    if response.status_code != 200:
                        raise Exception(f"Streaming failed: {response.status_code}")
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            
                            if data_str.strip() == "[DONE]":
                                break
                            
                            try:
                                data = json.loads(data_str)
                                
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content")
                                    
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                continue
            
            logger.info("Streaming complete")
            
        except Exception as e:
            logger.error(f"Streaming failed: {e}", exc_info=True)
            raise