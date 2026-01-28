"""
Core Health Check for Norwegian Lovdata Hierarchical Chunking
Customized to show ONLY PASS for successful tests.
"""

import unittest
import tempfile
import os
from pathlib import Path
import sys

# 1. Pathing for the Digirett-AI-Agent package structure
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from src.processors.chunker import (
        NorwegianLovdataParser,
        NorwegianLovdataChunker,
        FileHasher,
        DocumentMetadata,
    )
except ImportError:
    print("❌ Error: Run this from the project root using 'python -m ingestion.tests.test_health'")
    sys.exit(1)


# ============================================================================
# Custom Runner Logic to show ONLY "PASS"
# ============================================================================

class CustomTextTestResult(unittest.TextTestResult):
    """Overrides the default 'ok' output with 'PASS'"""
    def addSuccess(self, test):
        # We skip calling super().addSuccess(test) to prevent the default "ok" from printing
        if self.showAll:
            self.stream.writeln("PASS")
        elif self.dots:
            self.stream.write('.')
            self.stream.flush()

class CustomTestRunner(unittest.TextTestRunner):
    """Uses the custom result class defined above"""
    resultclass = CustomTextTestResult
    
    def run(self, test):
        result = super(CustomTestRunner, self).run(test)
        return result

# ============================================================================
# Test Cases
# ============================================================================

class TestCoreLovdataChunking(unittest.TestCase):
    """15 critical test cases for Lovdata hierarchical chunking"""

    def setUp(self):
        self.parser = NorwegianLovdataParser()
        self.chunker = NorwegianLovdataChunker()
        self.hasher = FileHasher()

    def test_separator_detection(self):
        self.assertTrue(self.parser.is_separator("----------------------------------------"))
        self.assertFalse(self.parser.is_separator("--"))

    def test_metadata_line_detection(self):
        self.assertTrue(self.parser.is_metadata_line("Datokode: LOV-2023"))
        self.assertTrue(self.parser.is_metadata_line("    - DokumentID: 123"))
        self.assertFalse(self.parser.is_metadata_line("Dette er vanlig brødtekst."))

    def test_paragraph_detection(self):
        result = self.parser.classify_norwegian_parent("§ 1.")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "paragraph")

    def test_kapittel_detection(self):
        result = self.parser.classify_norwegian_parent("Kapittel I. Innledning")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "kapittel")

    def test_dynamic_heading_detection(self):
        self.assertTrue(self.parser.is_dynamic_parent("GENERELLE BESTEMMELSER"))

    def test_child_content_detection(self):
        text = "Loven gjelder også for alle særlige tilfeller i Norge."
        self.assertTrue(self.parser.is_child_content(text))

    def test_innhold_section_skipped(self):
        text = """Datokode: TEST
Innhold
    - § 1.
----------------------------------------
§ 1.
Dette er faktisk innhold med mange ord her."""
        metadata, parents = self.parser.parse_file(text, "test.txt")
        self.assertEqual(len(parents), 1)

    def test_parse_metadata(self):
        text = "Datokode: LOV-1898-12-10-1\nYEAR: 1898\n---"
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        metadata = self.parser.parse_metadata(lines)
        self.assertEqual(metadata.year, 1898)

    def test_file_hash_consistency(self):
        h1 = self.hasher.hash_file("abc")
        h2 = self.hasher.hash_file("abc")
        self.assertEqual(h1, h2)

    # def test_chunk_id_generation(self):
    #     file_hash = "a" * 64
    #     cid = self.hasher.generate_chunk_id(file_hash, 1, 2)
    #     self.assertTrue(cid.startswith("a"*16))
    #     self.assertIn("_0001_0002", cid)

    def test_chunk_creation(self):
        text = "---\n§ 1.\nDette er faktisk innhold som har nok ord til å bli en chunk."
        metadata, chunks = self.chunker.chunk_text(text, "law.txt")
        self.assertGreater(len(chunks), 0)

    def test_parent_child_integrity(self):
        text = """Tittel: Test Document
----------------------------------------
§ 1.
Dette er den første viktige paragrafen i dokumentet.

§ 2.
Her kommer den andre paragrafen med mange ord for testing."""
        metadata, chunks = self.chunker.chunk_text(text, "law.txt")
        self.assertGreater(len(chunks), 0)
        self.assertTrue(any(c.parent_index >= 0 for c in chunks))

    def test_unicode_handling(self):
        text = """----------------------------------------
§ 1.
Norske tegn som Æ, Ø og Å må håndteres korrekt av systemet vårt."""
        metadata, chunks = self.chunker.chunk_text(text, "law.txt")
        self.assertGreater(len(chunks), 0)
        self.assertIn("Æ", chunks[0].text)

    def test_empty_file(self):
        metadata, chunks = self.chunker.chunk_text("", "empty.txt")
        self.assertEqual(len(chunks), 0)

    def test_chunk_file_from_disk(self):
        with tempfile.NamedTemporaryFile(delete=False, mode="w", encoding="utf-8") as f:
            f.write("---\n§ 1.\nDette er testinnhold som er langt nok for parseren.")
            fname = f.name

        try:
            metadata, chunks = self.chunker.chunk_file(fname)
            self.assertGreater(len(chunks), 0)
        finally:
            if os.path.exists(fname):
                os.remove(fname)


if __name__ == "__main__":
    # Load tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCoreLovdataChunking)
    # Use the Custom Test Runner to show ONLY "PASS"
    runner = CustomTestRunner(verbosity=2)
    result = runner.run(suite)
    
    sys.exit(0 if result.wasSuccessful() else 1)