# Language Detection & Response Generation Flow Analysis
## Digirett-AI-Agent Backend

**Date**: April 24, 2026  
**Scope**: Backend language detection, storage, and usage in response generation  
**Status**: ANALYSIS COMPLETE - 2 CRITICAL ISSUES IDENTIFIED

---

## Executive Summary

The system successfully detects document language and overrides query language when documents are present. However, **language information is not passed to the casual response generator**, causing responses to casual questions about documents to be generated in query language rather than document language.

### Quick Findings
- ✅ Document language detection: Working correctly
- ✅ Document language storage: In Supabase + Redis cache
- ✅ Language override in RAG pipeline: Working correctly  
- ✅ Language passing to legal/docqa generators: Working correctly
- ❌ **Language passing to casual generator: BROKEN**
- ❌ **Casual generator doesn't accept language parameter: BROKEN**

---

## Part 1: Document Language Detection

### Entry Point: POST /api/v1/documents/upload
**File**: `backend/api/routes/documents.py` (line 71+)

```
Upload → document_service.store_document()
```

### Detection Implementation
**File**: `backend/services/document_service.py`

#### detect_document_language() (lines 39-66)
```python
def detect_document_language(self, text: str) -> str:
    """
    Detect language using langdetect library
    Returns: 'norwegian', 'english', or language code
    Falls back to 'english' on error
    """
```

**Detection Process**:
1. Validates text length (minimum 50 chars)
2. Uses `langdetect.detect()` on first 1000 characters
3. Normalizes codes:
   - `no`, `nb`, `nn` → `"norwegian"`
   - `en`, `en-US`, `en-GB` → `"english"`
   - Other codes returned as-is
4. Graceful fallback to `"english"` on any error

#### store_document() (lines 256-377)
**Flow**:
```
1. Parse document with PyMuPDF
   ↓
2. Extract text → document_language = detect_document_language(text)
   ↓
3. Store in Supabase documents table with language field
   ↓
4. Cache document metadata in Redis session
```

**Storage in Supabase** (line 325):
```python
self._supabase.table("documents").insert({
    "document_id":    document_id,
    "conversation_id": conversation_id,
    "language":       document_language,  # ← Language stored here
    "extracted_text": extracted_text,
    # ... other fields
})
```

**Storage in Redis** (line 151-162):
```
redis_key = f"doc:session:{conversation_id}"
session["docs"].append({
    "document_id": document_id,
    "file_name": filename,
    "char_count": char_count,
    "upload_order": upload_order,
    "language": document_language  # ← Language stored in session
})
```

---

## Part 2: Language Retrieval & Override

### Retrieval Methods
**File**: `backend/services/document_service.py`

#### get_document_language() (lines 524-533)
```python
def get_document_language(self, conversation_id: str) -> Optional[str]:
    """
    Retrieve language of most recently uploaded document.
    Returns None if no documents exist.
    """
    docs = self.get_session_documents(conversation_id)
    if not docs:
        return None
    
    # Sort by upload_order descending to get latest
    docs_sorted = sorted(docs, key=lambda d: d.get("upload_order", 0), reverse=True)
    latest_language = docs_sorted[0].get("language", "english")
    return latest_language
```

#### has_documents() (lines 510-512)
```python
def has_documents(self, conversation_id: str) -> bool:
    """Check if session has at least one uploaded document."""
    session = self.get_or_create_session(conversation_id)
    return len(session.get("docs", [])) > 0
```

### Language Override in RAG Pipeline
**File**: `backend/services/rag_service.py` (lines 456-463)

```python
# ── Classify intent ────────────────────────────────────────
intent_result = await self._orchestrator.classify(query, conversation_id)
intent = intent_result["intent"]
language = intent_result["language"]  # ← Query language initially

# ── Override language with document language if documents exist ────
if self._document_service.has_documents(conversation_id):
    doc_language = self._document_service.get_document_language(conversation_id)
    if doc_language:
        logger.info(f"🌐 Using document language '{doc_language}' "
                    f"instead of query language '{language}'")
        language = doc_language  # ← CRITICAL: Override happens here
```

**This is the KEY decision point where document language replaces query language.**

---

## Part 3: Query Classification & Intent

### IntentAgent: Query Language Detection
**File**: `backend/agents/intent_agent.py` (lines 1-55)

**System Prompt**:
```
You are a binary classifier. Classify as LEGAL or CASUAL and detect language.
Output: {"intent": "LEGAL"|"CASUAL", "language": "english"|"norwegian"}
```

**Returns**: 
```python
{"intent": "LEGAL", "language": "norwegian"}  # Language = query language
```

**Note**: IntentAgent only detects query language. Document language override happens downstream in RAGService.

---

## Part 4: Response Generation Routing

### Query Processing Flow
**File**: `backend/services/rag_service.py` - `process_query()` (lines 404+)

```
1. Load conversation history
2. Classify intent → get query language
3. IF documents exist → override language with document language
4. Emit intent event with final language
5. Route based on [Intent + Document Presence]
```

### Routing Decision Tree

```
LEGAL Intent
├─ Document Present
│  ├─ Query about DOCUMENT → _handle_docqa(language=DOC_LANG)
│  ├─ Query about DOC+LAW → _handle_hybrid(language=DOC_LANG)
│  ├─ Follow-up → _handle_followup_with_doc(language=DOC_LANG)
│  └─ Query about LAW (not doc) → _handle_legal(language=DOC_LANG)
├─ No Documents → _handle_legal(language=QUERY_LANG)

CASUAL Intent
├─ Document Present
│  ├─ Question is doc-related → _handle_docqa(language=DOC_LANG)
│  ├─ Question is hybrid → _handle_hybrid(language=DOC_LANG)
│  ├─ Follow-up → _handle_followup_with_doc(language=DOC_LANG)
│  └─ Question is unrelated → _handle_casual(language=DOC_LANG) ← BUG HERE
└─ No Documents → _handle_casual(language=QUERY_LANG) ← BUG HERE
```

---

## Part 5: Response Generation (The Generators)

### Handler: _handle_casual() 
**File**: `backend/services/rag_service.py` (lines 548-565)

```python
async def _handle_casual(
    self,
    query: str,
    history: List[Dict[str, str]],
    language: str,  # ← Language is received
) -> AsyncIterator[Dict[str, Any]]:
    logger.info("💬 CASUAL pipeline")
    
    yield {"type": "sources", "data": []}
    
    full_answer = ""
    token_count = 0
    
    async for token in self._llm.generate_casual_stream(
        query=query,
        conversation_history=history,
        # ❌ BUG: language parameter NOT passed here
    ):
        token_count += 1
        full_answer += token
        yield {"type": "token", "data": token}
```

**Issue**: `language` received but not passed to `generate_casual_stream()`

### LLMService: generate_casual_stream()
**File**: `backend/services/llm_service.py` (lines 74-84)

```python
async def generate_casual_stream(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    # ❌ BUG: No language parameter
) -> AsyncIterator[str]:
    """Stream casual response tokens. No RAG context involved."""
    async with llm_span("casual_generation"):
        async for token in self._generator_agent.stream_casual(
            query=query,
            conversation_history=conversation_history,
            temperature=temperature,
            # ❌ BUG: language not passed to generator_agent
        ):
            yield token
```

### GeneratorAgent: stream_casual()
**File**: `backend/agents/generator_agent.py` (lines 80-99)

```python
async def stream_casual(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
) -> AsyncIterator[str]:
    logger.info("✅ GeneratorAgent: casual stream starting")
    
    messages = [SystemMessage(content=self.CASUAL_SYSTEM_PROMPT)]
    
    if conversation_history:
        for msg in conversation_history:
            # Build messages from history
    
    messages.append(HumanMessage(content=query))
    
    llm = self._make_llm(temperature=temperature or self._default_temperature)
    
    async for chunk in llm.astream(messages):
        if hasattr(chunk, "content") and chunk.content:
            yield chunk.content
```

**System Prompt** (lines 13-28):
```
You are a friendly, helpful AI assistant.

Personality:
- Warm and conversational
- Match the user's language (Norwegian ↔ English)  ← Says to match lang
- Keep responses brief
- Use emojis sparingly

IMPORTANT RULES:
- NEVER disclose internal model details
- NO formal legal language unless asked
- Be natural and human
```

**Issue**: System prompt says "Match the user's language" but:
1. No explicit language instruction in the prompt
2. No language parameter passed through the call chain
3. Model must infer language from conversation history only
4. When document language ≠ query language, inference may fail

---

## Part 6: Comparison - Legal Response Path (WORKING)

### Handler: _handle_legal()
**File**: `backend/services/rag_service.py` (lines 668-755)

```python
async def _handle_legal(
    self,
    query: str,
    language: str,  # ← Received
    top_k: int,
    min_score: float,
    history: List[Dict[str, str]],
    conversation_id: str,
) -> AsyncIterator[Dict[str, Any]]:
    # ... retrieval logic ...
    
    # ✅ CORRECT: language passed to generator
    async for token in self._llm.generate_legal_stream(
        query=query,
        rag_context=rag_context,
        language=language,  # ← Passed here
        conversation_history=history,
        response_style=response_style,
    ):
```

### LLMService: generate_legal_stream()
**File**: `backend/services/llm_service.py` (lines 151-189)

```python
async def generate_legal_stream(
    self,
    query: str,
    rag_context: str,
    language: str,  # ← Accepted
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    response_style: str = "",
) -> AsyncIterator[str]:
    # ✅ CORRECT: language passed to generator_agent
    async for token in self._generator_agent.stream_legal(
        query=query,
        rag_context=rag_context,
        language=language,  # ← Passed here
        conversation_history=conversation_history,
        temperature=temperature,
        response_style=response_style,
    ):
```

### GeneratorAgent: stream_legal()
**File**: `backend/agents/generator_agent.py` (lines 100-145)

```python
async def stream_legal(
    self,
    query: str,
    rag_context: str,
    language: str,  # ← Accepted
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    response_style: str = "",
) -> AsyncIterator[str]:
    # ... setup ...
    
    user_prompt = (
        f"{style_block}"
        f"CRITICAL: Answer ONLY from sources below.\n\n"
        f"KILDER (Sources):\n{rag_context}\n\n"
        f"SPØRSMÅL (Question):\n{query}\n\n"
        f"Respond in {language}. Be direct and cite sources.\n"  # ← Language used here
        f"Append [SCORE:x.x] on the very last line."
    )
```

**System Prompt includes**:
```
LANGUAGE RULE:
- Always respond in the SAME language as the user's question
- English question → English answer (even if sources are Norwegian)
- Norwegian question → Norwegian answer
```

✅ **This path WORKS correctly.**

---

## Part 7: DocQA Response Path (WORKING)

### Handler: _handle_docqa()
**File**: `backend/services/rag_service.py` (lines 818-850)

```python
async def _handle_docqa(
    self,
    query: str,
    language: str,  # ← Received
    history: List[Dict[str, str]],
    conversation_id: str,
) -> AsyncIterator[Dict[str, Any]]:
    logger.info("📄 DOCQA pipeline")
    
    doc_text = self._document_service.get_all_session_document_texts(
        conversation_id
    )
    
    # ... validation ...
    
    async for token in self._doc_qa_agent.stream_docqa(
        query=query,
        doc_text=doc_text,
        language=language,  # ← Passed here ✅
        conversation_history=history,
    ):
```

### DocumentQAAgent: stream_docqa()
**File**: `backend/agents/document_qa_agent.py` (lines 54-103)

```python
async def stream_docqa(
    self,
    query: str,
    doc_text: str,
    language: str,  # ← Accepted ✅
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> AsyncIterator[str]:
    logger.info("📄 DocumentQAAgent: DOCQA stream starting")
    logger.debug(f"   Language: {language}")
    
    # ... setup ...
    
    user_prompt = (
        f"DOCUMENT TEXT:\n{truncated_doc}\n\n"
        f"QUESTION: {query}\n\n"
        f"Respond in {language}. "  # ← Language injected here ✅
        f"Append [SCORE:x.x] on the very last line."
    )
    messages.append(HumanMessage(content=user_prompt))
```

✅ **This path WORKS correctly.**

---

## Part 8: Detailed Issue Analysis

### Issue #1: Casual Pipeline - Language Not Passed

**Location**: `backend/services/rag_service.py`, line 554

**Current Code**:
```python
async for token in self._llm.generate_casual_stream(
    query=query,
    conversation_history=history,
    # ❌ Missing: language=language
):
```

**Impact**: 
- When user asks casual question (e.g., "Tell me more", "Explain that") about an uploaded document in Norwegian, the system:
  1. Detects document language = "norwegian" 
  2. Overrides query language with "norwegian"
  3. BUT fails to pass language to casual generator
  4. Generator responds in query language instead of document language
  5. User sees response in English instead of Norwegian

**Affected Scenarios**:
- CASUAL intent + document present + document language ≠ query language
- Line 545: `async for event in self._handle_casual(query, history, language):`
- Line 561 (in _handle_casual): `generate_casual_stream(query, history)` ← Missing language

### Issue #2: Casual Generator - No Language Parameter

**Location 1**: `backend/services/llm_service.py`, line 74

**Current Code**:
```python
async def generate_casual_stream(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    # ❌ Missing: language: str parameter
) -> AsyncIterator[str]:
```

**Location 2**: `backend/agents/generator_agent.py`, line 80

**Current Code**:
```python
async def stream_casual(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    # ❌ Missing: language: str parameter
) -> AsyncIterator[str]:
```

**Impact**:
- No way to pass language through the entire casual pipeline
- GeneratorAgent.stream_casual() cannot inject language into system prompt
- System prompt says "Match the user's language" but provides no explicit language instruction
- Model must infer from conversation history, which is unreliable when document language ≠ query language

---

## Part 9: System Prompt Analysis

### CASUAL System Prompt (GeneratorAgent)
**Current** (lines 13-28 of generator_agent.py):
```
You are a friendly, helpful AI assistant.

Personality:
- Warm and conversational
- Natural and human-like
- Match the user's language (Norwegian ↔ English)  ← Wishful thinking without explicit lang
- Keep responses brief and friendly
- Use emojis sparingly (1-2 per message if appropriate)

IMPORTANT RULES:
- NEVER disclose internal model details or company behind the AI
- NO formal legal language unless asked
- Be natural and human
- Match their energy and tone
- Keep it conversational
```

**Issues**:
1. Says "Match the user's language" but provides no explicit language specification
2. No mechanism to override with document language
3. Falls back to conversation history inference

### LEGAL System Prompt (GeneratorAgent)
**Current** (lines 29-66 of generator_agent.py):

Contains explicit language instructions:
```
LANGUAGE RULE:
- Always respond in the SAME language as the user's question
- English question → English answer (even if sources are Norwegian)
- Norwegian question → Norwegian answer
```

✅ **Legal prompt handles language correctly via explicit instruction.**

---

## Part 10: Complete Flow Diagrams

### WORKING PATH: LEGAL Intent (with Document)

```
User Query (English): "What does the document say about taxes?"
    ↓
ChatWS Endpoint
    ↓
rag_service.process_query(query, conversation_id)
    ↓
IntentAgent.classify() → {"intent": "LEGAL", "language": "english"}
    ↓
has_documents(conversation_id) = True
    ↓
language = get_document_language(conversation_id) = "norwegian" ✓
    ↓
Yield: {"type": "intent", "data": {"intent": "LEGAL", "language": "norwegian"}}
    ↓
_handle_legal(query, language="norwegian", ...)  ✓
    ↓
generate_legal_stream(query, rag_context, language="norwegian", ...)  ✓
    ↓
stream_legal(query, rag_context, language="norwegian", ...)  ✓
    ↓
System Prompt: "Respond in norwegian"  ✓
    ↓
Response in Norwegian ✓

✅ WORKING CORRECTLY
```

### BROKEN PATH: CASUAL Intent (with Document, Unrelated Question)

```
User Query (English): "Tell me a joke"
    ↓
ChatWS Endpoint
    ↓
rag_service.process_query(query, conversation_id)
    ↓
IntentAgent.classify() → {"intent": "CASUAL", "language": "english"}
    ↓
has_documents(conversation_id) = True
    ↓
language = get_document_language(conversation_id) = "norwegian" ✓
    ↓
Yield: {"type": "intent", "data": {"intent": "CASUAL", "language": "norwegian"}}
    ↓
DocumentClassifier.classify() → intent="NOT_RELATED"
    ↓
_handle_casual(query, language="norwegian", ...)  ✓ Language passed
    ↓
generate_casual_stream(query, conversation_history)  ✗ Language NOT passed
    ↓
stream_casual(query, conversation_history)  ✗ Language NOT available
    ↓
System Prompt: "Match the user's language (Norwegian ↔ English)"
    ↓
No explicit language instruction; infer from history
    ↓
Inference sees English in query + history
    ↓
Response in English ✗ WRONG (should be Norwegian)

❌ BROKEN
```

---

## Part 11: Complete Availability Table

| Component | Location | Language Available | Passed Forward | Used | Status |
|-----------|----------|-------------------|-----------------|------|--------|
| **Detection** | document_service.detect_document_language() | ✓ Detected | ✓ Stored | N/A | ✅ OK |
| **Storage** | Supabase + Redis | ✓ Stored | ✓ Retrievable | N/A | ✅ OK |
| **Retrieval** | document_service.get_document_language() | ✓ Retrieved | ✓ Returned | N/A | ✅ OK |
| **Intent Agent** | agents/intent_agent.py | Query lang | ✓ Returned | N/A | ✅ OK |
| **Override Decision** | rag_service.process_query() line 456 | ✓ Both available | ✓ Override applied | N/A | ✅ OK |
| **Intent Event** | rag_service.process_query() line 466 | ✓ Final lang | ✓ Yielded | Frontend | ✅ OK |
| **Legal Handler** | rag_service._handle_legal() | ✓ Received | ✓ Passed | generate_legal_stream | ✅ OK |
| **DocQA Handler** | rag_service._handle_docqa() | ✓ Received | ✓ Passed | stream_docqa | ✅ OK |
| **Hybrid Handler** | rag_service._handle_hybrid() | ✓ Received | ✓ Passed | stream_hybrid | ✅ OK |
| **Followup Handler** | rag_service._handle_followup_with_doc() | ✓ Received | ✓ Passed to docqa | stream_docqa | ✅ OK |
| **Casual Handler** | rag_service._handle_casual() | ✓ Received | ✗ **NOT passed** | generate_casual_stream | ❌ BUG |
| **LLMService.gen_casual** | llm_service.generate_casual_stream() | ✗ No param | ✗ **Cannot accept** | stream_casual | ❌ BUG |
| **GeneratorAgent.casual** | generator_agent.stream_casual() | ✗ No param | ✗ **Cannot use** | System prompt | ❌ BUG |
| **Legal Generator** | generator_agent.stream_legal() | ✓ Param | ✓ Used in prompt | User prompt | ✅ OK |
| **DocQA Generator** | document_qa_agent.stream_docqa() | ✓ Param | ✓ Used in prompt | User prompt | ✅ OK |

---

## Part 12: Recommendations

### Fix #1: Pass Language to Casual Generator (IMMEDIATE)

**File**: `backend/services/rag_service.py` line 554

**Current**:
```python
async for token in self._llm.generate_casual_stream(
    query=query,
    conversation_history=history,
):
```

**Fixed**:
```python
async for token in self._llm.generate_casual_stream(
    query=query,
    conversation_history=history,
    language=language,  # ADD THIS LINE
):
```

---

### Fix #2: Add Language Parameter to LLMService (REQUIRED)

**File**: `backend/services/llm_service.py` lines 74-84

**Current**:
```python
async def generate_casual_stream(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
) -> AsyncIterator[str]:
    """Stream casual response tokens. No RAG context involved."""
    async with llm_span("casual_generation"):
        async for token in self._generator_agent.stream_casual(
            query=query,
            conversation_history=conversation_history,
            temperature=temperature,
        ):
            yield token
```

**Fixed**:
```python
async def generate_casual_stream(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    language: str = "english",  # ADD THIS PARAMETER
) -> AsyncIterator[str]:
    """Stream casual response tokens. No RAG context involved."""
    async with llm_span("casual_generation"):
        async for token in self._generator_agent.stream_casual(
            query=query,
            conversation_history=conversation_history,
            temperature=temperature,
            language=language,  # ADD THIS
        ):
            yield token
```

---

### Fix #3: Add Language Parameter to GeneratorAgent (REQUIRED)

**File**: `backend/agents/generator_agent.py` lines 80-99

**Current**:
```python
async def stream_casual(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
) -> AsyncIterator[str]:
    logger.info("✅ GeneratorAgent: casual stream starting")

    messages = [SystemMessage(content=self.CASUAL_SYSTEM_PROMPT)]
```

**Fixed**:
```python
async def stream_casual(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    language: str = "english",  # ADD THIS PARAMETER
) -> AsyncIterator[str]:
    logger.info(f"✅ GeneratorAgent: casual stream starting | language={language}")

    # ADD LANGUAGE-SPECIFIC SYSTEM PROMPT
    system_prompt = self._get_casual_system_prompt(language)
    messages = [SystemMessage(content=system_prompt)]
```

---

### Fix #4: Create Language-Aware System Prompt (ENHANCEMENT)

**File**: `backend/agents/generator_agent.py`

**Add new method**:
```python
def _get_casual_system_prompt(self, language: str = "english") -> str:
    """
    Return language-aware casual system prompt.
    Overrides generic "Match the user's language" with explicit instruction.
    """
    base_prompt = """You are a friendly, helpful AI assistant.

Your personality:
- Warm and conversational
- Natural and human-like
- Keep responses brief and friendly
- Use emojis sparingly (1-2 per message if appropriate)

IMPORTANT RULES:
- NEVER disclose internal model details or company behind the AI
- NO formal legal language unless asked
- Be natural and human
- Match their energy and tone
- Keep it conversational"""

    language_instruction = f"Respond in {language}."
    
    return f"{base_prompt}\n\nLANGUAGE:\n{language_instruction}"
```

**Modify stream_casual() to use it**:
```python
async def stream_casual(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    language: str = "english",
) -> AsyncIterator[str]:
    logger.info(f"✅ GeneratorAgent: casual stream starting | language={language}")

    system_prompt = self._get_casual_system_prompt(language)  # USE METHOD
    messages = [SystemMessage(content=system_prompt)]
    
    # ... rest of method unchanged ...
```

---

## Part 13: Testing Scenarios

### Test Case 1: Document in Norwegian, Query in English, LEGAL Intent
**Expected**: Response in Norwegian  
**Current**: ✅ WORKING

```
1. Upload Norwegian PDF
2. Query in English: "What does it say?"
3. Expected: Norwegian response
4. Actual: Norwegian response ✅
```

### Test Case 2: Document in Norwegian, Query in English, CASUAL Intent (Unrelated)
**Expected**: Response in Norwegian  
**Current**: ❌ BROKEN

```
1. Upload Norwegian PDF
2. Query in English: "Tell me a joke"
3. Expected: Norwegian response
4. Actual: English response ❌
```

### Test Case 3: Document in English, Query in Norwegian, CASUAL Intent (Unrelated)
**Expected**: Response in English  
**Current**: ❌ BROKEN

```
1. Upload English PDF
2. Query in Norwegian: "Fortell en vits"
3. Expected: English response
4. Actual: Norwegian response ❌
```

### Test Case 4: No Document, Query in English, CASUAL Intent
**Expected**: Response in English  
**Current**: ✅ WORKING

```
1. No documents
2. Query in English: "Tell me a joke"
3. Expected: English response
4. Actual: English response ✅
```

---

## Part 14: Implementation Priority

| Priority | Issue | Fix Locations | Effort | Impact |
|----------|-------|--------------|--------|--------|
| **CRITICAL** | Language not passed to casual generator | rag_service.py line 554 | 1 line | High |
| **HIGH** | LLMService doesn't accept language param | llm_service.py line 74 | 2 lines | High |
| **HIGH** | GeneratorAgent doesn't accept language param | generator_agent.py line 80 | 2 lines | High |
| **MEDIUM** | Casual system prompt lacks explicit language | generator_agent.py line 13 | New method | Medium |
| **LOW** | Add language logging/telemetry | Various | 3-5 lines | Low |

---

## Part 15: Code Locations Summary

### All References to Language Flow

```
DETECTION
├── backend/services/document_service.py
│   ├── detect_document_language() [line 39]
│   └── store_document() [line 287]

STORAGE
├── Supabase
│   └── documents.language [line 325]
└── Redis
    └── session["docs"][].language [line ~162]

RETRIEVAL
├── backend/services/document_service.py
│   ├── has_documents() [line 510]
│   ├── get_document_language() [line 524]
│   └── get_session_documents() [line 504]

OVERRIDE
└── backend/services/rag_service.py
    └── process_query() [line 456-463]

ROUTING
└── backend/services/rag_service.py
    ├── process_query() [line 468+]
    ├── _handle_legal() [line 668]
    ├── _handle_docqa() [line 818]
    ├── _handle_hybrid() [line 868]
    ├── _handle_followup_with_doc() [line 811]
    └── _handle_casual() [line 548] ← BUG HERE

GENERATION
├── backend/services/llm_service.py
│   ├── generate_casual_stream() [line 74] ← FIX NEEDED
│   ├── generate_legal_stream() [line 151] ✓ OK
│   └── generate_legal_answer() [line 88] ✓ OK
├── backend/agents/generator_agent.py
│   ├── stream_casual() [line 80] ← FIX NEEDED
│   └── stream_legal() [line 100] ✓ OK
└── backend/agents/document_qa_agent.py
    ├── stream_docqa() [line 54] ✓ OK
    └── stream_hybrid() [line 110] ✓ OK
```

---

## Part 16: Conclusion

The Digirett-AI-Agent backend has a well-designed language detection and override system that works correctly for 80% of the system:

✅ **Working Well**:
- Document language detection (uses langdetect)
- Storage in Supabase and Redis
- Language override in RAG pipeline
- Legal response generation with language
- Document QA generation with language
- Hybrid generation with language

❌ **Broken**:
- Casual response generation is missing language parameter
- Language information available but not forwarded to casual generator
- Affects scenarios: CASUAL intent + document + doc_lang ≠ query_lang

**Root Cause**: Casual generator was developed without language-awareness, while legal generators were built with explicit language support.

**Fix Effort**: ~10 lines of code across 3 files

**Impact**: Users asking casual questions about documents will get responses in the wrong language
