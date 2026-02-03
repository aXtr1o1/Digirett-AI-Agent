"""
app/services/llm_service.py
Azure OpenAI service with strict retrieval-grounded responses
"""

import logging
from typing import AsyncIterator, Tuple
from openai import AzureOpenAI, AsyncAzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)


class AzureOpenAIService:
    """Service for Azure OpenAI API with strict RAG compliance"""
    
    # STRICT retrieval-grounded system prompt
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LEGAL RAG PROMPT
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
📋 RESPONSE STRUCTURE (When sources contain the answer):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **Direct Answer**
Clear, concise response based ONLY on provided sources

2. **Confidence Note**
- "Fully supported by sources" or "Partially covered in sources"

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
⚠️ REMEMBER:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are a retrieval-based assistant. ACCURACY and SOURCE-TRACEABILITY are more important than providing any answer. When in doubt, say you cannot find the information rather than guessing.

ONLY answer from the KILDER (sources) provided below. If the sources are empty or don't contain the answer, acknowledge it clearly.
You are ALSO a legal relevance evaluator.

    User Query:
    "{query}"

    Retrieved Legal Excerpts:
    {chunks}

    Task:
    Determine whether the retrieved excerpts contain sufficient and relevant legal information
    to answer the user's query.

    Rules:
    - If excerpts are clearly relevant → relevant = true
    - If excerpts are vague, unrelated, or insufficient → relevant = false

    Example:
    - if retrieval-based assistant return I cannot find any relevant legal excerpts in the available Lovdata database that directly answer this question. The score is 0.1
    - if retrieval-based assistant return 1. **Direct Answer**
        Clear, concise response based ONLY on provided sources

        2. **Confidence Note**
        - "Fully supported by sources" or "Partially covered in sources"
        The score is 0.9

    Respond ONLY in valid JSON:

    {
  "relevant": true | false,
  "score": 0.0,
  "reason": "short explanation"
}
"""

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
        azure_endpoint: str,
        api_key: str,
        api_version: str,
        deployment_name: str
    ):
        self.azure_endpoint = azure_endpoint
        self.api_key = api_key
        self.api_version = api_version
        self.deployment_name = deployment_name
        
        self.client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
        )
        
        self.async_client = AsyncAzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
        )
        
        logger.info(f"Azure OpenAI service initialized with deployment: {deployment_name}")
    
    async def check_connection(self) -> bool:
        """Check if Azure OpenAI is accessible"""
        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            return True
        except Exception as e:
            logger.error(f"Azure OpenAI connection check failed: {e}")
            return False
    async def judge_relevance(self, query: str, chunks: list[str]) -> dict:
        """
        Uses LLM to judge whether retrieved documents are relevant.
        Returns relevance flag + confidence score.
        """

        prompt = LEGAL_SYSTEM_PROMPT.format(
            query=query,
            chunks="\n\n".join(chunks) if chunks else "EMPTY"
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": prompt}
            ]
        )
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
        temperature: float = 0.3,  # Lower temperature for more focused responses
        max_tokens: int = 2000
    ) -> Tuple[str, int]:
        """Generate answer using Azure OpenAI"""
        try:
            logger.info("Generating answer with Azure OpenAI...")
            
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
            
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.95
            )
            
            answer = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            
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
            logger.info("Starting streaming response...")
            
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
            
            stream = await self.async_client.chat.completions.create(
                model=self.deployment_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                # Azure streaming can send empty choices or non-content deltas
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta is None:
                    continue

                content = getattr(delta, "content", None)

                if content:
                    yield content
            
            logger.info("Streaming complete")
            
        except Exception as e:
            logger.error(f"Streaming failed: {e}", exc_info=True)
            raise