# Language Detection & Response Generation - Executive Summary

## The Complete Flow

```
📄 USER UPLOADS DOCUMENT (Norwegian PDF)
    ↓
🔍 Detect Language: detect_document_language() → "norwegian"
    ↓
💾 Store: Supabase documents.language + Redis session
    ↓
❓ USER ASKS QUESTION (in English)
    ↓
🎯 Intent Classification: IntentAgent → {"intent": "LEGAL/CASUAL", "language": "english"}
    ↓
📋 Check: has_documents()? YES
    ↓
🔄 Override: language = get_document_language() → "norwegian"
    ↓
🚀 Route Based on [Intent + Documents]:
    ├─ LEGAL + DOC → _handle_legal(language="norwegian") → ✅ Works
    ├─ LEGAL + DOC → _handle_docqa(language="norwegian") → ✅ Works
    ├─ CASUAL + DOC → _handle_docqa(language="norwegian") → ✅ Works
    └─ CASUAL + DOC (unrelated) → _handle_casual(language="norwegian") → ❌ BROKEN
        └─ generate_casual_stream() doesn't receive language parameter
```

---

## Where Language Information Flows

### ✅ WORKING PATHS (Language properly passed through entire chain)

#### Legal Pipeline
```
_handle_legal(language="norwegian")
    ↓
llm_service.generate_legal_stream(query, rag_context, language="norwegian")
    ↓
generator_agent.stream_legal(query, rag_context, language="norwegian")
    ↓
User Prompt: "Respond in norwegian."
    ↓
Response in Norwegian ✅
```

#### Document QA Pipeline
```
_handle_docqa(language="norwegian")
    ↓
doc_qa_agent.stream_docqa(query, doc_text, language="norwegian")
    ↓
User Prompt: "Respond in norwegian."
    ↓
Response in Norwegian ✅
```

#### Hybrid Pipeline
```
_handle_hybrid(language="norwegian")
    ↓
doc_qa_agent.stream_hybrid(query, doc_text, rag_context, language="norwegian")
    ↓
User Prompt: "Respond in norwegian."
    ↓
Response in Norwegian ✅
```

---

### ❌ BROKEN PATH (Language lost in translation)

#### Casual Pipeline
```
_handle_casual(language="norwegian")  ← Language received here
    ↓
llm_service.generate_casual_stream(query, history)  ← ❌ Language NOT passed
    ↓
generator_agent.stream_casual(query, history)  ← ❌ No language parameter
    ↓
System Prompt: "Match the user's language (Norwegian ↔ English)"
    ↓
No explicit language instruction; infer from history
    ↓
Inference sees English query + English history
    ↓
Response in English ❌ (Should be Norwegian)
```

---

## 3 Critical Issues

### Issue #1: Missing Language in RAG Service Call
**File**: `backend/services/rag_service.py` line 554  
**Severity**: 🔴 CRITICAL (1 line fix)

```python
# CURRENT (BROKEN)
async for token in self._llm.generate_casual_stream(
    query=query,
    conversation_history=history,
):

# FIX
async for token in self._llm.generate_casual_stream(
    query=query,
    conversation_history=history,
    language=language,  # ADD THIS
):
```

### Issue #2: LLMService Missing Language Parameter
**File**: `backend/services/llm_service.py` line 74  
**Severity**: 🟠 HIGH (3 lines)

```python
# CURRENT (BROKEN)
async def generate_casual_stream(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
) -> AsyncIterator[str]:
    async for token in self._generator_agent.stream_casual(
        query=query,
        conversation_history=conversation_history,
        temperature=temperature,
    ):

# FIX
async def generate_casual_stream(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    language: str = "english",  # ADD THIS
) -> AsyncIterator[str]:
    async for token in self._generator_agent.stream_casual(
        query=query,
        conversation_history=conversation_history,
        temperature=temperature,
        language=language,  # ADD THIS
    ):
```

### Issue #3: GeneratorAgent Missing Language Parameter
**File**: `backend/agents/generator_agent.py` line 80  
**Severity**: 🟠 HIGH (3 lines)

```python
# CURRENT (BROKEN)
async def stream_casual(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
) -> AsyncIterator[str]:

# FIX
async def stream_casual(
    self,
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    temperature: Optional[float] = None,
    language: str = "english",  # ADD THIS
) -> AsyncIterator[str]:
    # Inject language into system prompt
    system_prompt = f"{self.CASUAL_SYSTEM_PROMPT}\n\nRespond in {language}."
    messages = [SystemMessage(content=system_prompt)]
```

---

## Impact Analysis

### Who's Affected
Users asking casual/general questions about uploaded documents when document language ≠ query language

### Example Scenarios

| Scenario | Document | Query | Response | Status |
|----------|----------|-------|----------|--------|
| User uploads Norwegian contract, asks about it in English | 🇳🇴 | 🇬🇧 | Norwegian | ✅ OK (Legal intent) |
| User uploads Norwegian contract, asks casual question in English | 🇳🇴 | 🇬🇧 | English | ❌ WRONG (Should be Norwegian) |
| No document, casual question in English | - | 🇬🇧 | English | ✅ OK |
| Legal question without document in English | - | 🇬🇧 | English | ✅ OK |

### Business Impact
- **Low**: Most users ask legal questions about documents (legal path works fine)
- **Medium**: Some users ask casual follow-ups (will get wrong language)
- **Workaround**: User can ask same question with legal phrasing to get correct language

---

## Where Language Information IS Available

```
✅ Document Language Storage
   └─ Supabase table: documents.language
   └─ Redis cache: session["docs"][].language

✅ Language Retrieval Methods
   └─ get_document_language(conversation_id) → Returns latest doc language
   └─ has_documents(conversation_id) → Checks if docs exist

✅ Language Override Applied
   └─ rag_service.process_query() line 456-463
   └─ if has_documents: language = doc_language

✅ Language Available in Handler Functions
   ├─ _handle_legal(language="norwegian") ✅
   ├─ _handle_docqa(language="norwegian") ✅
   ├─ _handle_hybrid(language="norwegian") ✅
   ├─ _handle_followup_with_doc(language="norwegian") ✅
   └─ _handle_casual(language="norwegian") ✅ RECEIVED

❌ Language LOST in Casual Pipeline
   └─ _handle_casual() receives language but doesn't pass to generate_casual_stream()
   └─ generate_casual_stream() doesn't accept language parameter
   └─ stream_casual() doesn't accept language parameter
   └─ System prompt has no language instruction
```

---

## Testing the Issue

### To Reproduce BROKEN Behavior

```
1. Upload a Norwegian PDF (e.g., contract)
2. Ask in English: "Tell me about the document" (legal intent)
   → Response in Norwegian ✅ Works

3. Upload a Norwegian PDF
4. Ask in English: "That's interesting, tell me more about it" (casual intent)
   → Response in English ❌ Should be Norwegian but isn't

5. Or upload an English PDF
6. Ask in Norwegian: "Fortell meg mer om det" (casual intent)
   → Response in Norwegian ❌ Should be English but isn't
```

### To Verify FIX

Same test cases after applying 3 fixes:
```
4. Upload a Norwegian PDF
5. Ask in English: "Tell me more about it" (casual intent)
   → Response in Norwegian ✅ Fixed!

5. Upload an English PDF
6. Ask in Norwegian: "Fortell meg mer om det" (casual intent)
   → Response in English ✅ Fixed!
```

---

## Code Change Checklist

- [ ] Add `language=language` parameter to RAG service line 554
- [ ] Add `language: str = "english"` parameter to LLMService line 74
- [ ] Pass `language=language` in LLMService call to generator_agent
- [ ] Add `language: str = "english"` parameter to GeneratorAgent line 80
- [ ] Inject language into GeneratorAgent system prompt
- [ ] Test: Upload Norwegian doc, ask casual question in English
- [ ] Test: Upload English doc, ask casual question in Norwegian
- [ ] Verify: Legal queries still work correctly

---

## Full Documentation

See **LANGUAGE_FLOW_ANALYSIS.md** for:
- Complete flow diagrams
- Detailed code locations
- Implementation recommendations
- Testing scenarios
- All affected files and line numbers
