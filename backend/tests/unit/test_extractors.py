"""
Unit tests for knowledge extractors.

Tests the extraction strategies without any DB or embedding calls.
"""

from app.domains.knowledge.extractors import (
    _extract_dependency_signal,
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


class TestDependencyExtraction:
    def test_package_json_extraction(self):
        content = (
            '{"dependencies": {"react": "^18.0.0", "typescript": "~5.0.0"}, '
            '"devDependencies": {"vite": "^5.0.0"}}'
        )
        chunks = _extract_dependency_signal("package.json", content)
        assert len(chunks) == 1
        assert chunks[0]["chunk_type"] == "dependency_signal"
        assert "react" in chunks[0]["content"]
        assert "typescript" in chunks[0]["content"]
        assert "vite" in chunks[0]["content"]

    def test_requirements_txt_extraction(self):
        content = "fastapi>=0.100.0\npydantic>=2.0.0\n# comment\nopenai>=1.0.0"
        chunks = _extract_dependency_signal("requirements.txt", content)
        assert len(chunks) == 1
        assert "fastapi" in chunks[0]["content"]
        assert "pydantic" in chunks[0]["content"]
        assert "openai" in chunks[0]["content"]
        # Comments should not be included as dependency entries
        assert "# comment" not in chunks[0]["content"]

    def test_empty_package_json_returns_no_chunks(self):
        content = '{"name": "my-app", "version": "1.0.0"}'
        chunks = _extract_dependency_signal("package.json", content)
        assert chunks == []

    def test_invalid_json_falls_back_gracefully(self):
        content = "this is not json"
        chunks = _extract_dependency_signal("package.json", content)
        # Should return fallback chunk, not raise
        assert len(chunks) == 1
        assert chunks[0]["chunk_type"] == "dependency_signal"


class TestCodeExtraction:
    def test_python_module_description(self):
        content = '''"""This module handles authentication."""

def login(email: str) -> str:
    pass

def logout(token: str) -> None:
    pass

def _internal_helper():
    pass
'''
        chunks = extract_chunks("app/auth.py", content, allow_code_snippets=False)
        assert len(chunks) >= 1
        module_chunks = [c for c in chunks if c["chunk_type"] == "module_description"]
        assert len(module_chunks) == 1
        content_text = module_chunks[0]["content"]
        assert "app/auth.py" in content_text
        assert "authentication" in content_text  # docstring
        assert "login" in content_text  # public function
        assert "logout" in content_text
        # Private functions should NOT appear
        assert "_internal_helper" not in content_text

    def test_no_code_snippets_without_opt_in(self):
        content = '''def public_function():
    """Does something."""
    return 42
'''
        chunks = extract_chunks("module.py", content, allow_code_snippets=False)
        snippet_chunks = [c for c in chunks if c["chunk_type"] == "code_snippet"]
        assert len(snippet_chunks) == 0

    def test_code_snippets_with_opt_in(self):
        content = '''def public_function():
    """Does something."""
    return 42
'''
        chunks = extract_chunks("module.py", content, allow_code_snippets=True)
        snippet_chunks = [c for c in chunks if c["chunk_type"] == "code_snippet"]
        assert len(snippet_chunks) >= 1
        assert "public_function" in snippet_chunks[0]["content"]
        assert snippet_chunks[0]["start_line"] == 1
        assert snippet_chunks[0]["end_line"] >= 3

    def test_python_multiline_signature_snippet_includes_body(self):
        content = '''async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401)
    return TokenPair(access_token="x", refresh_token="y")
'''
        chunks = extract_chunks("app/routes/auth.py", content, allow_code_snippets=True)
        snippet_chunks = [c for c in chunks if c["chunk_type"] == "code_snippet"]

        assert len(snippet_chunks) == 1
        assert "result = await db.execute" in snippet_chunks[0]["content"]
        assert "return TokenPair" in snippet_chunks[0]["content"]
        assert snippet_chunks[0]["start_line"] == 1
        assert snippet_chunks[0]["end_line"] == 9

    def test_typescript_exports_extracted(self):
        content = '''/**
 * Authentication service.
 */
export function loginUser(email: string): Promise<string> {
    return fetch('/api/login');
}

export class AuthService {
    constructor() {}
}
'''
        chunks = extract_chunks("src/auth.ts", content, allow_code_snippets=False)
        module_chunks = [c for c in chunks if c["chunk_type"] == "module_description"]
        assert len(module_chunks) == 1
        assert "loginUser" in module_chunks[0]["content"]
        assert "AuthService" in module_chunks[0]["content"]

    def test_typescript_exported_object_api_snippet_extracted(self):
        content = """export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', new URLSearchParams({ username: email, password })),
  register: (email: string, password: string, full_name: string) =>
    api.post('/auth/register', { email, password, full_name }),
  me: () => api.get('/auth/me'),
}
"""
        chunks = extract_chunks("frontend/src/lib/api.ts", content, allow_code_snippets=True)
        snippet_chunks = [c for c in chunks if c["chunk_type"] == "code_snippet"]

        assert snippet_chunks
        assert "const authApi" in snippet_chunks[0]["content"]
        assert "/auth/login" in snippet_chunks[0]["content"]
        assert "/auth/register" in snippet_chunks[0]["content"]

    def test_large_function_truncated_in_snippet(self):
        # Build a function with > 60 lines
        lines = ["def big_function():"] + [f"    x = {i}" for i in range(70)]
        content = "\n".join(lines)
        chunks = extract_chunks("big.py", content, allow_code_snippets=True)
        snippet_chunks = [c for c in chunks if c["chunk_type"] == "code_snippet"]
        if snippet_chunks:
            # Should be truncated
            assert "truncated" in snippet_chunks[0]["content"]
            assert "x = 50" in snippet_chunks[0]["content"]
            assert "x = 69" not in snippet_chunks[0]["content"]
            assert snippet_chunks[0]["chunk_metadata"]["line_count"] == 60

    def test_large_react_component_keeps_auth_handler_in_snippet_window(self):
        filler = "\n".join(f"  const field{i} = {i}" for i in range(20))
        tail = "\n".join(f"      <span>{i}</span>" for i in range(70))
        content = f"""export function LoginPage() {{
  const navigate = useNavigate()
{filler}

  const onSubmit = async (data: FormData) => {{
    const response = await authApi.login(data.email, data.password)
    setSessionTokens(response.data.access_token, response.data.refresh_token)
    navigate('/')
  }}

  return (
    <div>
{tail}
    </div>
  )
}}
"""
        chunks = extract_chunks("frontend/src/pages/LoginPage.tsx", content, allow_code_snippets=True)
        snippet_chunks = [c for c in chunks if c["chunk_type"] == "code_snippet"]

        assert snippet_chunks
        assert "authApi.login" in snippet_chunks[0]["content"]
        assert "setSessionTokens" in snippet_chunks[0]["content"]
        assert "// ... (truncated for safety)" in snippet_chunks[0]["content"]


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
