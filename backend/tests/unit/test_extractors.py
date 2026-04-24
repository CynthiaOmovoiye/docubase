"""
Unit tests for knowledge extractors.

Tests the extraction strategies without any DB or embedding calls.
"""

from app.domains.knowledge.extractors import (
    _is_binary_content,
    _split_by_headings,
    extract_chunks,
)


class TestDocumentationExtraction:
    def test_readme_produces_documentation_chunks(self):
        content = "# Overview\n\nThis project does X.\n\n## Features\n\nIt has Y and Z."
        chunks = extract_chunks("README.md", content, allow_code_snippets=False)
        assert len(chunks) > 0
        assert all(c["chunk_type"] == "documentation" for c in chunks)
        assert all(c["source_ref"] == "README.md" for c in chunks)
        assert all(c["start_line"] is not None for c in chunks)
        assert all(c["end_line"] is not None for c in chunks)

    def test_headings_split_into_sections(self):
        content = "# Section A\n\nContent A.\n\n# Section B\n\nContent B."
        sections = _split_by_headings(content)
        assert len(sections) == 2
        assert sections[0][0] == "Section A"
        assert sections[1][0] == "Section B"

    def test_no_headings_returns_single_section(self):
        content = "Just some plain text without any headings."
        sections = _split_by_headings(content)
        assert len(sections) == 1
        assert sections[0][0] == ""

    def test_preamble_before_first_heading_is_included(self):
        content = "Some intro text.\n\n# Section\n\nContent."
        sections = _split_by_headings(content)
        assert len(sections) == 2
        assert sections[0][0] == ""  # preamble has no heading
        assert "intro text" in sections[0][1]

    def test_long_text_is_split_into_multiple_chunks(self):
        # Create text longer than MAX_CHUNK_CHARS (2000)
        content = "# Long Section\n\n" + ("word " * 500)
        chunks = extract_chunks("docs/guide.md", content, allow_code_snippets=False)
        assert len(chunks) >= 2, "Long text should produce multiple chunks"




class TestPdfExtraction:
    def test_clean_text_produces_documentation_chunks(self):
        content = "--- Page 1 ---\nCynthia Omovoiye\nSoftware Engineer\n\nExperience:\nBuilt AI pipelines."
        chunks = extract_chunks("Resume.pdf [abc123def456]", content, allow_code_snippets=False)
        assert len(chunks) >= 1
        assert all(c["chunk_type"] == "documentation" for c in chunks)

    def test_binary_mojibake_is_rejected(self):
        # Simulate binary PDF bytes decoded as UTF-8 with replacement chars
        binary_like = "\ufffd" * 50 + "".join(chr(i) for i in range(1, 20)) + "\ufffd" * 50
        chunks = extract_chunks("Resume.pdf [abc123def456]", binary_like, allow_code_snippets=False)
        assert chunks == []

    def test_drive_virtual_filename_routes_to_pdf_extractor(self):
        # Virtual Drive filenames like "Name.pdf [fileId]" must be handled correctly
        content = "--- Page 1 ---\nSome resume text here."
        chunks = extract_chunks(
            "Cynthia_Omovoiye_Resume.pdf [11JmWkaOATrc7Fx9RIws4]",
            content,
            allow_code_snippets=False,
        )
        assert len(chunks) >= 1
        assert all(c["chunk_type"] == "documentation" for c in chunks)

    def test_high_control_byte_density_is_rejected(self):
        # Simulate content with many control bytes (binary stream decoded as string)
        control_heavy = "Normal text " + "".join(chr(i) for i in range(1, 32)) * 20
        chunks = extract_chunks("doc.pdf", control_heavy, allow_code_snippets=False)
        assert chunks == []

    def test_is_binary_content_rejects_replacement_chars(self):
        assert _is_binary_content("\ufffd" * 10) is True

    def test_is_binary_content_accepts_normal_prose(self):
        assert _is_binary_content("Hello, this is a normal resume.\nSkills: Python, SQL.") is False

    def test_is_binary_content_rejects_empty(self):
        assert _is_binary_content("") is True


class TestManualSource:
    def test_manual_notes_are_documentation(self):
        content = "This project implements a real-time chat system using WebSockets."
        chunks = extract_chunks("manual/notes.md", content, allow_code_snippets=False)
        assert len(chunks) >= 1
        assert all(c["chunk_type"] == "documentation" for c in chunks)

    def test_txt_file_treated_as_documentation(self):
        content = "Plain text file content."
        chunks = extract_chunks("notes.txt", content, allow_code_snippets=False)
        assert len(chunks) >= 1
        assert all(c["chunk_type"] == "documentation" for c in chunks)

    def test_unknown_extension_falls_back_to_documentation(self):
        content = "Some unknown format content."
        chunks = extract_chunks("data.xyz", content, allow_code_snippets=False)
        assert len(chunks) >= 1
        # Should fall back to documentation
        assert all(c["chunk_type"] == "documentation" for c in chunks)


class TestEmbedder:
    """Test the local stub embedder without any API calls."""

    def test_local_stub_returns_correct_dimensions(self):
        import asyncio

        from app.domains.embedding.embedder import LocalStubEmbedder, settings
        embedder = LocalStubEmbedder()
        vector = asyncio.get_event_loop().run_until_complete(embedder.embed("hello world"))
        assert len(vector) == settings.embedding_dimensions

    def test_local_stub_is_deterministic(self):
        import asyncio

        from app.domains.embedding.embedder import LocalStubEmbedder
        embedder = LocalStubEmbedder()
        loop = asyncio.get_event_loop()
        v1 = loop.run_until_complete(embedder.embed("test input"))
        v2 = loop.run_until_complete(embedder.embed("test input"))
        assert v1 == v2

    def test_local_stub_different_inputs_differ(self):
        import asyncio

        from app.domains.embedding.embedder import LocalStubEmbedder
        embedder = LocalStubEmbedder()
        loop = asyncio.get_event_loop()
        v1 = loop.run_until_complete(embedder.embed("first input"))
        v2 = loop.run_until_complete(embedder.embed("different input"))
        assert v1 != v2

    def test_local_stub_is_unit_normalised(self):
        import asyncio
        import math

        from app.domains.embedding.embedder import LocalStubEmbedder
        embedder = LocalStubEmbedder()
        vector = asyncio.get_event_loop().run_until_complete(embedder.embed("normalise me"))
        norm = math.sqrt(sum(x * x for x in vector))
        assert abs(norm - 1.0) < 1e-6, f"Expected unit norm, got {norm}"

    def test_batch_embed_returns_correct_count(self):
        import asyncio

        from app.domains.embedding.embedder import LocalStubEmbedder, settings
        embedder = LocalStubEmbedder()
        texts = ["first", "second", "third"]
        vectors = asyncio.get_event_loop().run_until_complete(embedder.embed_batch(texts))
        assert len(vectors) == 3
        assert all(len(v) == settings.embedding_dimensions for v in vectors)
