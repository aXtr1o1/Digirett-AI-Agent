import pytest
from ingestion.src.chunking.chunk_validator import ChunkContentValidator


def test_validator_preserves_definitions_without_legal_verbs():
    validator = ChunkContentValidator()
    
    # Definition without mandatory standard modal legal verb
    chunk_def = {
        "text": "Med 'arbeidstaker' i denne lov forstås enhver som utfører arbeid i annens tjeneste."
    }
    is_valid, reason = validator.validate(chunk_def)
    assert is_valid is True
    assert reason == "ok"


def test_validator_preserves_lists_and_conditions():
    validator = ChunkContentValidator()
    
    chunk_list = {
        "text": "a) 30 dager ved oppsigelse\nb) 60 dager ved avskjed"
    }
    is_valid, reason = validator.validate(chunk_list)
    assert is_valid is True
    assert reason == "ok"


def test_validator_rejects_empty():
    validator = ChunkContentValidator()
    is_valid, reason = validator.validate({"text": "   "})
    assert is_valid is False
    assert "Empty text" in reason


def test_validator_rejects_repeal_stub():
    validator = ChunkContentValidator()
    chunk_repeal = {"text": "(Opphevet med vedtak 18 nov 1905.)"}
    is_valid, reason = validator.validate(chunk_repeal)
    assert is_valid is False
    assert "annotation stub" in reason


def test_validator_rejects_toc_range_header():
    validator = ChunkContentValidator()
    chunk_toc = {"text": "§ 85.\nD. Om den dømmande makta (§§ 86–91)"}
    is_valid, reason = validator.validate(chunk_toc)
    assert is_valid is False
    assert "TOC" in reason
