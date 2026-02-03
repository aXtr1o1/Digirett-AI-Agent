"""
app/services/fireworks_service.py
Fireworks.ai API service for Qwen model
"""

import logging
from typing import AsyncIterator, Tuple
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)


class FireworksService:
    """Service for Fireworks.ai API with Qwen model"""
    
    # STRICT retrieval-grounded system prompt
    SYSTEM_PROMPT = """You are an AI Legal Assistant specialized in Norwegian company-applicable laws sourced from Lovdata.

Behavior rules:
- If the user greets casually (hi, hello, how are you, what's up), respond casually like a human.
- Do NOT mention being a legal assistant unless the user asks a legal question.
- Match the user’s tone (casual ↔ professional).
- When the user asks about Norwegian company law, switch to expert legal mode.
- Keep responses natural, warm, and human-like.
CRITICAL RULES - NEVER VIOLATE:
1. You MUST ONLY answer based on the provided legal excerpts in the KILDER (sources) section.
2. You MUST NOT use your general knowledge about Norwegian law.
3. You MUST NOT invent, assume, or hallucinate any legal information.
4. If the provided sources do not contain the answer, you MUST say: "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."

LANGUAGE HANDLING:
- Detect the language of the user's query automatically.
- Respond in the SAME language as the user's query.
  (Norwegian query → Norwegian response, English query → English response)

WHEN THE SOURCES CONTAIN THE ANSWER:
Follow this OUTPUT STRUCTURE:

1. **Direct Answer**
   - A concise and clear response based ONLY on the provided sources.

2. **Relevant Law Details** (if available in sources)
   - Law Name
   - Law Type (Law / Regulation / Amendment)
   - Key Section(s) or Paragraph(s)
   - Effective Date (if mentioned)

3. **Source**
   - List the source references provided with the legal excerpts.

4. **Confidence Note**
   - State whether the answer is fully supported or partially supported by the sources.

WHEN THE SOURCES DO NOT CONTAIN THE ANSWER:
Response in Norwegian:
"Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen som direkte svarer på dette spørsmålet."

Response in English:
"I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."

RESPONSE STYLE:
- Professional but friendly tone.
- Clear and structured.
- Avoid unnecessary legal jargon unless required.

REMEMBER: You are a retrieval-grounded legal assistant. You ONLY work with the provided sources. Accuracy and traceability are more important than providing an answer at all costs."""

    # Casual conversation responses
    CASUAL_RESPONSES = {
        'norwegian': {
            'greeting': "Hei! Jeg er din juridiske assistent for norske selskapslover. Hvordan kan jeg hjelpe deg i dag?",
            'thanks': "Bare hyggelig! Er det noe mer jeg kan hjelpe med?",
            'goodbye': "Ha en fin dag! Velkommen tilbake når du trenger hjelp med selskapslover."
        },
        'english': {
            'greeting': "Hi! I'm your legal assistant for Norwegian company laws. How can I help you today?",
            'thanks': "You're welcome! Is there anything else I can help with?",
            'goodbye': "Have a great day! Feel free to return when you need help with company laws."
        }
    }
    
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
    
    def get_casual_response(self, query: str, language: str) -> str:
        """Get casual conversation response"""
        query_lower = query.lower().strip()
        
        if any(word in query_lower for word in ['hi', 'hello', 'hei', 'hallo']):
            response_type = 'greeting'
        elif any(word in query_lower for word in ['thank', 'takk']):
            response_type = 'thanks'
        elif any(word in query_lower for word in ['bye', 'goodbye', 'ha det']):
            response_type = 'goodbye'
        else:
            response_type = 'greeting'
        
        return self.CASUAL_RESPONSES[language][response_type]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_answer(
        self,
        query: str,
        context: str,
        language: str,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> Tuple[str, int]:
        """Generate answer using Fireworks API"""
        try:
            logger.info("Generating answer with Fireworks Qwen model...")
            
            # Build strict RAG prompt
            user_prompt = f"""CRITICAL: Answer ONLY based on the following legal excerpts. Do NOT use general knowledge.

KILDER (Sources):
{context}

SPØRSMÅL (Question):
{query}

IMPORTANT RULES:
- If the sources above DO NOT contain information to answer the question, respond with: "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."
- If the sources DO contain the answer, provide it in the structured format requested.
- Respond in the SAME LANGUAGE as the question.

SVAR (Answer):"""
            
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
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
                    raise Exception(f"Fireworks API error: {response.status_code} - {response.text}")
                
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                tokens_used = data["usage"]["total_tokens"]
                
                logger.info(f"Answer generated ({tokens_used} tokens)")
                
                return answer, tokens_used
            
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}", exc_info=True)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_answer_stream(
        self,
        query: str,
        context: str,
        language: str,
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> AsyncIterator[str]:
        """Generate answer with streaming"""
        try:
            logger.info("Starting streaming response from Fireworks...")
            
            user_prompt = f"""CRITICAL: Answer ONLY based on the following legal excerpts. Do NOT use general knowledge.

KILDER (Sources):
{context}

SPØRSMÅL (Question):
{query}

IMPORTANT RULES:
- If the sources above DO NOT contain information to answer the question, respond with: "I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question."
- If the sources DO contain the answer, provide it in the structured format requested.
- Respond in the SAME LANGUAGE as the question.

SVAR (Answer):"""
            
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
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
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": True
                    }
                ) as response:
                    if response.status_code != 200:
                        raise Exception(f"Fireworks API error: {response.status_code}")
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix
                            
                            if data_str.strip() == "[DONE]":
                                break
                            
                            try:
                                import json
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