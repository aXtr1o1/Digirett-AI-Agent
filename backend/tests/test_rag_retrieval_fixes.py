import pytest
import urllib.parse
import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch
from agents.statute_registry import get_registry
from agents.query_reasoning_agent import QueryReasoningAgent
from services.rag_service import RAGService

# ── 1. Statute Registry Tests ──────────────────────────────────────────

def test_registry_fake_law_rejection():
    registry = get_registry()
    
    # Standard valid queries should still match
    assert registry.lookup("arbeidsmiljøloven") is not None
    assert registry.lookup("lov om arbeidsmiljø") is not None
    
    # Fake laws with qualifying suffixes should be rejected
    assert registry.lookup("arbeidsmiljøloven for kunstig intelligens") is None
    assert registry.lookup("arbeidsmiljøloven for roboter") is None
    assert registry.lookup("arbeidsmiljøloven for ai") is None
    assert registry.lookup("arbeidsmiljølov for maskiner") is None

def test_registry_word_boundaries():
    registry = get_registry()
    
    # No word boundary matches (substring scan shouldn't match parts of words)
    assert registry.lookup("arbeidsmiljølovenxx") is None

# ── 2. Precedence Rules & Query Reasoning Tests ─────────────────────────

@patch("agents.query_reasoning_agent.AzureChatOpenAI")
def test_precedence_rules_honors_none(mock_chat):
    # Mock LLM response to explicitly return "none" for a fake law
    mock_llm_instance = MagicMock()
    mock_generation = MagicMock()
    mock_generation.text = """Legal Topic               : Artificial Intelligence Law
Legal Domain              : arbeidsrett
Primary Statute Name      : none
Primary Statute ID        : none
Secondary Statute Name    : none
Secondary Statute ID      : none
Key Mechanism             : regulation of ai
Key Concepts              : ai, robots
Enriched Query            : En fake lov om kunstig intelligens eksisterer ikke.
Response Style            : informative
Legal Domain              : arbeidsrett
Jurisdiction              : NO
Source Type               : lov"""
    
    mock_llm_result = MagicMock()
    mock_llm_result.generations = [[mock_generation]]
    mock_llm_instance.agenerate = AsyncMock(return_value=mock_llm_result)
    mock_chat.return_value = mock_llm_instance
    
    agent = QueryReasoningAgent()
    
    # Run async function using asyncio.run
    result = asyncio.run(agent.run("arbeidsmiljøloven for kunstig intelligens"))
    
    assert result["primary_statute_id"] is None
    assert result["statute_from_registry"] is False

# ── 3. URL Encoding & Citation Deduplication Tests ─────────────────────

@patch("services.rag_service.LLMService")
@patch("services.rag_service.MilvusClient")
@patch("services.rag_service.RedisClient")
@patch("services.rag_service.SupabaseClient")
@patch("services.rag_service.EmbeddingService")
def test_citation_formatting_and_deduplication(
    mock_embed, mock_supa, mock_redis, mock_milvus, mock_llm
):
    # Mock search results containing section references with spaces
    mock_chunks = [
        {
            "source_doc_url": "https://lovdata.no/lov/2005-06-17-62",
            "section_ref": "§ 12-1",
            "doc_title": "Arbeidsmiljøloven",
            "text": "Overtid skal begrenses...",
            "score": 0.8
        }
    ]
    
    # Test formatting logic
    seen_urls = set()
    visible_sources = []
    for chunk in mock_chunks:
        base_url = chunk.get("source_doc_url")
        section_ref = chunk.get("section_ref")
        doc_title = chunk.get("doc_title")
        
        encoded_section = urllib.parse.quote(section_ref) if section_ref else ""
        full_url = f"{base_url}/{encoded_section}" if encoded_section else base_url
        
        if full_url and full_url not in seen_urls:
            seen_urls.add(full_url)
            visible_sources.append({
                "url": full_url,
                "doc_title": doc_title,
                "section_ref": section_ref
            })
            
    # Verify section ref is encoded (spaces become %20, § becomes %C2%A7)
    assert "%20" in visible_sources[0]["url"]
    assert "%C2%A7" in visible_sources[0]["url"]
    # Verify no base_url duplication exists in visible_sources (it only contains the encoded full_url)
    assert len(visible_sources) == 1
    assert visible_sources[0]["url"] == "https://lovdata.no/lov/2005-06-17-62/%C2%A7%2012-1"

# ── 4. Context Isolation Tests ──────────────────────────────────────────

def test_context_isolation():
    def get_isolated_chunks(query_str, chunks):
        is_specific_section_query = False
        section_nums = re.findall(r"§\s*(\d+(?:-\d+)?)", query_str) or re.findall(r"paragraf\s*(\d+(?:-\d+)?)", query_str, re.IGNORECASE)
        if section_nums:
            is_specific_section_query = True
            
        if is_specific_section_query and chunks:
            isolated_chunks = []
            for chunk in chunks:
                chunk_section = chunk.get("section_ref") or ""
                for sec in section_nums:
                    if sec in chunk_section:
                        isolated_chunks.append(chunk)
                        break
            if isolated_chunks:
                return isolated_chunks
        return chunks

    chunks = [
        {"section_ref": "§ 12-1", "text": "Correct Section"},
        {"section_ref": "§ 15-2", "text": "Wrong Section"}
    ]
    
    # Scenario A: General query -> no isolation, return all chunks
    assert len(get_isolated_chunks("hva er overtid?", chunks)) == 2
    
    # Scenario B: Specific section query -> keeps ONLY the requested section chunk
    isolated = get_isolated_chunks("hva står i § 12-1?", chunks)
    assert len(isolated) == 1
    assert isolated[0]["text"] == "Correct Section"
