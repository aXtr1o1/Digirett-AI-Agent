import pytest
from ingestion.models.legal_section import LegalBlock, NormalizedLegalSection
from ingestion.src.chunking.legal_chunker import LegalSectionChunker


def test_chunker_single_section_under_limit():
    blocks = [
        LegalBlock(block_type="LEDD", text="Første ledd med vanlig tekst.", order=0),
        LegalBlock(block_type="LEDD", text="Andre ledd med litt mer tekst.", order=1),
    ]
    section = NormalizedLegalSection(
        legal_document_id="NL/lov/2005-06-17-62",
        canonical_document_id="NL/lov/2005-06-17-62",
        document_type="LAW",
        document_title="Arbeidsmiljøloven",
        section_type="LAW_PARAGRAPH",
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        section_number="§ 15-7",
        source_text="Første ledd med vanlig tekst.\n\nAndre ledd med litt mer tekst.",
        structured_blocks=blocks,
    )

    chunker = LegalSectionChunker(max_tokens=2000, overlap_tokens=200)
    chunks = chunker.chunk_section(section)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 1
    assert chunks[0].source_section_key == "NL/lov/2005-06-17-62/§15-7"
    assert chunks[0].source_block_start == 0
    assert chunks[0].source_block_end == 1
    assert "Første ledd" in chunks[0].source_text
    assert "Andre ledd" in chunks[0].source_text


def test_chunker_hierarchical_split_oversized():
    # Create 4 blocks of 20 words each (~25 tokens)
    long_text_1 = " ".join(["ord1"] * 20)
    long_text_2 = " ".join(["ord2"] * 20)
    long_text_3 = " ".join(["ord3"] * 20)
    long_text_4 = " ".join(["ord4"] * 20)

    blocks = [
        LegalBlock(block_type="LEDD", text=long_text_1, order=0),
        LegalBlock(block_type="LEDD", text=long_text_2, order=1),
        LegalBlock(block_type="LEDD", text=long_text_3, order=2),
        LegalBlock(block_type="LEDD", text=long_text_4, order=3),
    ]
    source_text = f"{long_text_1}\n\n{long_text_2}\n\n{long_text_3}\n\n{long_text_4}"

    section = NormalizedLegalSection(
        legal_document_id="NL/lov/2005-06-17-62",
        canonical_document_id="NL/lov/2005-06-17-62",
        document_type="LAW",
        document_title="Arbeidsmiljøloven",
        section_type="LAW_PARAGRAPH",
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        section_number="§ 15-7",
        source_text=source_text,
        structured_blocks=blocks,
    )

    chunker = LegalSectionChunker(max_tokens=60, overlap_tokens=0)
    chunks = chunker.chunk_section(section)

    assert len(chunks) >= 2
    assert chunks[0].source_block_start == 0
    assert chunks[-1].source_block_end == 3
    for c in chunks:
        assert c.source_section_key == "NL/lov/2005-06-17-62/§15-7"
        assert c.section_ref == "§ 15-7"


def test_chunker_hierarchical_split_with_block_overlap():
    # 4 blocks where each block is ~20 tokens
    blocks = [
        LegalBlock(block_type="LEDD", text="Blokk en inneholder første del av lovteksten.", order=0),
        LegalBlock(block_type="LEDD", text="Blokk to inneholder andre del av lovteksten.", order=1),
        LegalBlock(block_type="LEDD", text="Blokk tre inneholder tredje del av lovteksten.", order=2),
        LegalBlock(block_type="LEDD", text="Blokk fire inneholder fjerde del av lovteksten.", order=3),
    ]
    source_text = "\n\n".join(b.text for b in blocks)

    section = NormalizedLegalSection(
        legal_document_id="NL/lov/2005-06-17-62",
        canonical_document_id="NL/lov/2005-06-17-62",
        document_type="LAW",
        document_title="Arbeidsmiljøloven",
        section_type="LAW_PARAGRAPH",
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        section_number="§ 15-7",
        source_text=source_text,
        structured_blocks=blocks,
    )

    # max_tokens=30 means ~2 blocks per chunk; overlap_tokens=15 means 1 block overlaps
    chunker = LegalSectionChunker(max_tokens=30, overlap_tokens=15)
    chunks = chunker.chunk_section(section)

    assert len(chunks) >= 2
    # Verify that block overlap occurs: trailing block of Chunk 1 appears in Chunk 2
    assert "Blokk en" in chunks[0].source_text
    assert "Blokk to" in chunks[0].source_text
    assert "Blokk to" in chunks[1].source_text
    assert "Blokk tre" in chunks[1].source_text
    # Verify block range overlaps
    assert chunks[0].source_block_start == 0
    assert chunks[0].source_block_end == 1
    assert chunks[1].source_block_start == 1


def test_chunker_sentence_overlap():
    # 1 large block exceeding max_tokens, split by sentences
    sentences = [
        "Dette er den første setningen i paragrafen.",
        "Dette er den andre setningen i paragrafen.",
        "Dette er den tredje setningen i paragrafen.",
        "Dette er den fjerde setningen i paragrafen.",
    ]
    text = " ".join(sentences)
    blocks = [LegalBlock(block_type="LEDD", text=text, order=0)]

    section = NormalizedLegalSection(
        legal_document_id="NL/lov/2005-06-17-62",
        canonical_document_id="NL/lov/2005-06-17-62",
        document_type="LAW",
        document_title="Arbeidsmiljøloven",
        section_type="LAW_PARAGRAPH",
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        section_number="§ 15-7",
        source_text=text,
        structured_blocks=blocks,
    )

    # Set token limits so ~2 sentences fit per sub-chunk and 1 sentence overlaps
    chunker = LegalSectionChunker(max_tokens=25, overlap_tokens=15)
    chunks = chunker.chunk_section(section)

    assert len(chunks) >= 2
    # Verify sentence overlap in text
    assert "første setningen" in chunks[0].source_text
    assert "andre setningen" in chunks[0].source_text
    assert "andre setningen" in chunks[1].source_text


def test_chunker_word_overlap_fallback():
    # Single sentence with no punctuation exceeding max_tokens
    words = ["ord"] * 30
    text = " ".join(words)
    blocks = [LegalBlock(block_type="LEDD", text=text, order=0)]

    section = NormalizedLegalSection(
        legal_document_id="NL/lov/2005-06-17-62",
        canonical_document_id="NL/lov/2005-06-17-62",
        document_type="LAW",
        document_title="Arbeidsmiljøloven",
        section_type="LAW_PARAGRAPH",
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        section_number="§ 15-7",
        source_text=text,
        structured_blocks=blocks,
    )

    chunker = LegalSectionChunker(max_tokens=15, overlap_tokens=5)
    chunks = chunker.chunk_section(section)

    assert len(chunks) >= 2
    for c in chunks:
        assert c.token_count <= 15
