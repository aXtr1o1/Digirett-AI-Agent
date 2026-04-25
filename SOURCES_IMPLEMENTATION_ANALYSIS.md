# Sources/Citations Implementation Analysis

## 🎯 Problem Summary

### Problem 1: Sources Embedded in Response Text
**Current behavior:** Sources appear INSIDE the assistant's response message
**Desired behavior:** Response text is clean, sources appear in a SEPARATE "Citations" section below

### Problem 2: Citations Display Raw URLs Instead of Titles
**Current behavior:** Citations show raw URLs like `https://lovdata.no/lov/2005-04-08-17/§10-1`
**Desired behavior:** Citations show document titles like "Lov om arbeidsmiljø" (Employment Act)

---

## 📊 Code Flow Analysis

### Backend Flow

#### 1. **RAG Context Building** (`backend/services/rag_service.py:841`)
```python
def _build_context(chunks: List[Dict[str, Any]]) -> str:
    # Builds a string like:
    # [1] https://lovdata.no/lov/... | § 6-1 | domain | subdomain
    # <text content>
    # ---
    # [2] https://lovdata.no/lov/... | § 3-2
    # <text content>
```

**Issue:** This context is passed directly to the LLM, which may include source URLs in its answer.

#### 2. **Sources Emission** (`backend/services/rag_service.py:665-675`)
```python
yield {"type": "sources", "data": visible_sources}
# Emits: ["https://lovdata.no/lov/...", "https://lovdata.no/lov/.../§6-1"]
```

**Issue:** Only raw URLs are sent, no document titles.

#### 3. **Answer Generation** (`backend/agents/generator_agent.py:170-200`)
- LLM receives the context with embedded URLs
- Generates answer (may reference sources in text)
- Answer is streamed as tokens
- No separation of answer from embedded citations

#### 4. **WebSocket Response** (`backend/api/routes/chat.py:150`)
- `sources` event has only raw URLs
- `token` event streams the answer (may contain embedded source references)
- `complete` event includes `full_answer` (cleaned of [SCORE:x.x] but may have embedded sources)

### Frontend Flow

#### 1. **WebSocket Event Processing** (`frontend/src/services/chatService.js:90-105`)
```javascript
case "sources":
  sources = Array.isArray(event.data) ? event.data : [];
  // sources = ["https://lovdata.no/lov/...", ...]

case "token":
  fullMessage += token;  // Answer accumulates tokens
  onChunk(token);        // Streams to UI
```

#### 2. **Source Processing** (`frontend/src/services/chatService.js:120`)
```javascript
sources: sources.map((url) =>
  typeof url === "string" ? { url, title: url } : url
)
// Converts: ["https://..."] → [{ url: "https://...", title: "https://..." }]
```

**Issue:** Title defaults to URL if not provided.

#### 3. **Message Display** (`frontend/src/components/chat/Message.jsx:180-185`)
- Answer is rendered as markdown
- Sources are displayed via `<SourceLinks />` component
- SourceLinks component shows `source.title` or `source.url`

---

## 🔧 Solution Architecture

### Solution 1: Clean Answer from Embedded Sources

**Strategy:** Prevent LLM from including sources in the answer text by:
1. Modifying the LLM prompt to explicitly forbid source mention in answer
2. Post-processing the answer to remove any accidentally embedded source URLs
3. Extracting referenced sources into structured citations

#### Implementation Steps:

**Step 1: Modify Generator System Prompt**
- File: `backend/agents/generator_agent.py` (LEGAL_SYSTEM_PROMPT)
- Add explicit instruction: "NEVER include source URLs in your answer text"
- Add instruction: "Do NOT use citations like [1], [2] - the frontend will handle that"

**Step 2: Clean Answer in LLMService**
- File: `backend/services/llm_service.py` (generate_legal_answer method)
- After extracting score, remove any embedded URLs/section refs from answer
- Use regex to strip: `https://...`, `§ \d+(-\d+)?`, `[CITATION:...]` etc.

**Step 3: Strip Answer in RAG Pipeline**
- File: `backend/services/rag_service.py` (_handle_legal method)
- Before streaming tokens, clean the scored_answer
- Stream clean tokens to frontend

---

### Solution 2: Document Titles in Source Objects

**Strategy:** Build rich source objects with both URL and title, send to frontend.

#### Implementation Steps:

**Step 1: Enrich Search Results with Titles**
- File: `backend/services/rag_service.py` (_handle_legal, after search_results)
- For each chunk in search_results, extract/build title:
  - Try: `chunk.get("file_name")` (document title if uploaded)
  - Try: `chunk.get("title")` (from Milvus metadata)
  - Try: `chunk.get("section_ref")` + base statute (e.g., "§ 6-1 - Employment Act")
  - Default: Extract from URL path (e.g., "lov/2005-04-08-17" → "Lov om arbeidsmiljø")

**Step 2: Build Source Objects**
- File: `backend/services/rag_service.py` (around line 665)
- Instead of emitting raw URLs:
```python
visible_sources = []
for chunk in search_results:
    visible_sources.append({
        "url": full_url,
        "title": extracted_title,
        "section_ref": chunk.get("section_ref", ""),
        "type": chunk.get("statute_type", "statute")  # statute, regulation, case, etc
    })

yield {"type": "sources", "data": visible_sources}
```

**Step 3: Lookup Statute Names**
- File: `backend/agents/statute_registry.py` or new file
- Create mapping: statute_id → statute_name
- Example: "LOV-2005-04-08-17" → "Lov om arbeidsmiljø (Employment Act)"

**Step 4: Update Frontend Processing**
- File: `frontend/src/services/chatService.js`
- Already handles objects: `{ url, title } : url`
- Just ensure backend sends objects instead of strings

**Step 5: Update SourceLinks Component**
- File: `frontend/src/components/chat/SourceLinks.jsx`
- Already displays `source.title` with fallback to `source.url` ✅
- Could enhance with section_ref display: "§ 6-1 from Employment Act"

---

## 📝 Implementation Order

### Phase 1: Clean Answer Text (Prevents Source Embedding)
1. ✅ Update `LEGAL_SYSTEM_PROMPT` in `generator_agent.py`
2. ✅ Add answer cleaning function to `llm_service.py`
3. ✅ Call cleaning function before emitting tokens in `rag_service.py`

### Phase 2: Enrich Source Objects (Adds Titles)
1. ✅ Create statute name lookup (registry or mapping)
2. ✅ Build source object enrichment logic in `rag_service.py`
3. ✅ Modify `_build_context()` to NOT include URLs (keep only for metadata)
4. ✅ Update sources emission to send `{ url, title, section_ref }` objects
5. ✅ Test frontend already handles objects correctly

### Phase 3: Post-Processing Cleanup
1. ✅ Strip any embedded URLs from final answer
2. ✅ Remove `[CITATION:...]` patterns if any
3. ✅ Ensure clean spacing

---

## 🔍 Key Code Locations

| Problem | File | Line | Current Code | Solution |
|---------|------|------|--------------|----------|
| **Problem 1** | `generator_agent.py` | 23 | LEGAL_SYSTEM_PROMPT | Add rule: "NEVER embed sources in answer text" |
| | `llm_service.py` | 160 | generate_legal_answer() | Add answer cleaning regex |
| | `rag_service.py` | 665 | sources emission | Keep existing, just ensure clean answer |
| **Problem 2** | `rag_service.py` | 665 | `visible_sources` (raw URLs) | Convert to `{ url, title, section_ref }` objects |
| | `rag_service.py` | 841 | `_build_context()` | Keep URLs in context, but extract titles for sources emission |
| | `statute_registry.py` | - | (new file or lookup) | Map statute IDs to human-readable names |
| | `chatService.js` | 90 | sources handling | Already handles objects ✅ |
| | `SourceLinks.jsx` | 32 | display logic | Already handles titles ✅ |

---

## 🎬 Data Structure Evolution

### Current (Problem State):
```
Backend → Frontend
sources: ["https://lovdata.no/lov/2005-04-08-17/§10-1"]
         ↓
Frontend: { url: "https://lovdata.no/lov/2005-04-08-17/§10-1", 
            title: "https://lovdata.no/lov/2005-04-08-17/§10-1" }
         ↓
UI: "https://lovdata.no/lov/2005-04-08-17/§10-1" (raw URL as title)
```

### Desired (Solution State):
```
Backend → Frontend
sources: [
  { 
    url: "https://lovdata.no/lov/2005-04-08-17/§10-1",
    title: "§ 10-1 - Lovdan om arbeidsmiljø",
    section_ref: "§ 10-1",
    type: "statute"
  }
]
         ↓
Frontend: (already expects this format) ✅
         ↓
UI: "§ 10-1 - Lov om arbeidsmiljø" (human-readable title)
   with link to https://lovdata.no/...
```

---

## ⚙️ Technical Implementation Details

### Answer Cleaning Function (Python)
```python
def _clean_answer_text(answer: str) -> str:
    """Remove embedded URLs, citations, and source references from answer."""
    # Remove URLs
    answer = re.sub(r'https?://[^\s\)]+', '', answer)
    
    # Remove section refs like "§ 10-1"
    answer = re.sub(r'§\s*\d+(-\d+)?', '', answer)
    
    # Remove citation patterns like [1], [2], [CITATION:...]
    answer = re.sub(r'\[\d+\]', '', answer)
    answer = re.sub(r'\[CITATION:[^\]]+\]', '', answer)
    
    # Clean up excessive whitespace
    answer = re.sub(r'\s+', ' ', answer).strip()
    
    return answer
```

### Statute Name Lookup (Python)
```python
# Option 1: Database lookup from Milvus/Supabase metadata
statute_names = {
    "LOV-2005-04-08-17": "Lov om arbeidsmiljø",
    "FOR-1994-12-20-1357": "Foreskrifter om sjøvern",
    # ... build from actual data
}

# Option 2: Parse from existing chunk metadata
def extract_statute_title(chunk: Dict) -> str:
    # Try existing metadata
    if "statute_title" in chunk:
        return chunk["statute_title"]
    
    # Parse from URL/statute_id
    statute_id = chunk.get("statute_id", "")
    return statute_names.get(statute_id, f"Statute {statute_id}")
```

### Source Object Builder (Python)
```python
def build_source_object(chunk: Dict) -> Dict:
    """Convert RAG chunk to frontend source object."""
    base_url = chunk.get("source_doc_url") or chunk.get("url") or ""
    section_ref = (chunk.get("section_ref") or "").strip()
    
    # Build full URL with section anchor
    full_url = f"{base_url}/{section_ref}" if section_ref else base_url
    
    # Extract title
    title = extract_statute_title(chunk)
    if section_ref:
        title = f"{section_ref} - {title}"
    
    return {
        "url": full_url,
        "title": title,
        "section_ref": section_ref,
        "type": chunk.get("statute_type", "statute"),
        "domain": chunk.get("domain"),
    }
```

---

## ✅ Verification Checklist

- [ ] Updated LEGAL_SYSTEM_PROMPT forbids embedded sources
- [ ] Answer cleaning function removes URLs, §, [citations]
- [ ] Sources emitted as `{ url, title, section_ref }` objects
- [ ] Statute name lookup working (all laws have human-readable names)
- [ ] Frontend receives objects and displays titles correctly
- [ ] Test: Legal answer has NO embedded URLs or §
- [ ] Test: Citations section shows "Statute Name § Section"
- [ ] Test: Clicking citation opens correct Lovdata page
- [ ] Test: Both Norwegian and English responses clean
- [ ] Test: Multiple sources shown with different titles

---

## 🚀 Next Steps

1. **Review this analysis** - confirm understanding of problems and solutions
2. **Approve approach** - decide on statute name lookup strategy
3. **Implement Phase 1** - clean answer text (quick win, prevents embedding)
4. **Implement Phase 2** - enrich source objects with titles
5. **Test** - verify both problems are solved
6. **Deploy** - roll out to production

---

## 📌 Quick Reference

**Problem 1 Fix:** System prompt + answer cleaning regex in `llm_service.py`
**Problem 2 Fix:** Source object enrichment in `rag_service.py` + statute name lookup

**Frontend:** Already handles rich source objects ✅ (no changes needed)

**Files to Modify:**
- `backend/agents/generator_agent.py` (prompt)
- `backend/services/llm_service.py` (answer cleaning)
- `backend/services/rag_service.py` (sources emission)
- `backend/agents/statute_registry.py` or new lookup file (statute names)
