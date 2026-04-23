"""
Knowledge extraction strategies.

Each extractor takes a RawFile and produces a list of Chunks (as dicts)
ready for embedding and storage.

Extractors do NOT run policy checks — that's done by the pipeline before
calling any extractor. All content arriving here has already cleared policy.

Chunk content represents DERIVED knowledge, not raw file content:
  - README / docs  → documentation chunks split by section
  - Python/TS/JS   → module_description (docstrings + signatures only)
                      code_snippet (small function body, only if opt-in)
  - package.json / pyproject.toml → dependency_signal (name + version list)
  - PDF (pre-extracted text) → documentation chunks
  - Manual notes   → manual_note chunk(s)

Each returned dict has keys matching the Chunk model plus Phase 0 evidence
metadata when available:
  chunk_type, content, source_ref, chunk_metadata, start_line, end_line, segment_id
"""

import json
import re
from pathlib import PurePosixPath

from app.core.logging import get_logger

logger = get_logger(__name__)

# Maximum characters per chunk before we split further
_MAX_CHUNK_CHARS = 2000
# Overlap between adjacent prose chunks (characters)
_OVERLAP_CHARS = 200

# File extensions classified as code
_CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".swift", ".kt",
    ".scala", ".sh", ".bash", ".zsh",
}

# Dependency manifest files
_DEPENDENCY_FILES = {
    "package.json", "pyproject.toml", "requirements.txt",
    "requirements.in", "Pipfile", "go.mod", "Cargo.toml",
    "pom.xml", "build.gradle",
}

# Documentation / markdown
_DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt"}


# ─── Public entry point ───────────────────────────────────────────────────────

def extract_chunks(
    path: str,
    content: str,
    allow_code_snippets: bool,
) -> list[dict]:
    """
    Main dispatch function.

    Returns a list of chunk dicts. Each dict has:
      - chunk_type: str (ChunkType value)
      - content: str
      - source_ref: str
      - chunk_metadata: dict
    """
    suffix = PurePosixPath(path).suffix.lower()
    filename = PurePosixPath(path).name.lower()

    if filename in _DEPENDENCY_FILES:
        return _extract_dependency_signal(path, content)

    if suffix in _DOC_EXTENSIONS:
        return _extract_documentation(path, content)

    if suffix in _CODE_EXTENSIONS:
        return _extract_code_knowledge(path, content, allow_code_snippets)

    # Fallback: treat as plain documentation
    return _extract_documentation(path, content)


# ─── Dependency manifests ─────────────────────────────────────────────────────

def _extract_dependency_signal(path: str, content: str) -> list[dict]:
    """
    Extract a compact dependency list as a single chunk.

    We never store the full manifest — just the dependency names and versions.
    This gives the twin knowledge of what libraries/frameworks the project uses
    without exposing config secrets (e.g. registry URLs, auth tokens).
    """
    filename = PurePosixPath(path).name.lower()
    deps: list[str] = []

    try:
        if filename == "package.json":
            data = json.loads(content)
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                for name, version in data.get(section, {}).items():
                    deps.append(f"{name}@{version}")

        elif filename == "pyproject.toml":
            # Simple regex extraction — avoids a TOML library dependency
            for line in content.splitlines():
                m = re.match(r'\s*"?([a-zA-Z0-9_-]+[a-zA-Z0-9._-]*)([>=<!^~][^"]*)?', line)
                if m and "=" not in line.split("=")[0]:
                    continue
                # Look for dependency lines: package>=x.y or "package>=x.y"
                m = re.match(r'\s*"?([a-zA-Z0-9_.-]+)\s*([>=<!^~][^",]*)?', line)
                if m and not line.strip().startswith("#") and not line.strip().startswith("["):
                    dep = m.group(1).strip().strip('"')
                    ver = (m.group(2) or "").strip()
                    if dep and len(dep) > 1:
                        deps.append(f"{dep}{ver}" if ver else dep)

        elif filename in ("requirements.txt", "requirements.in"):
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    deps.append(line.split("#")[0].strip())

        elif filename == "go.mod":
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("require") or (line and "/" in line and not line.startswith("go ")):
                    parts = line.split()
                    if len(parts) >= 1:
                        deps.append(" ".join(parts[:2]))

        elif filename == "cargo.toml":
            for line in content.splitlines():
                m = re.match(r'([a-zA-Z0-9_-]+)\s*=\s*"([^"]+)"', line)
                if m:
                    deps.append(f"{m.group(1)}@{m.group(2)}")

    except Exception as exc:
        logger.warning("dependency_extraction_failed", path=path, error=str(exc))
        # Fallback: return first 1000 chars as a plain text chunk
        return [{
            "chunk_type": "dependency_signal",
            "content": content[:1000],
            "source_ref": path,
            "chunk_metadata": {"extraction": "raw_fallback"},
        }]

    if not deps:
        return []

    # Deduplicate and build a readable summary
    seen: set[str] = set()
    unique_deps = []
    for d in deps:
        key = d.split("@")[0].split(">=")[0].split("==")[0].lower()
        if key not in seen:
            seen.add(key)
            unique_deps.append(d)

    chunk_content = f"Dependencies in {PurePosixPath(path).name}:\n" + "\n".join(unique_deps[:200])

    return [{
        "chunk_type": "dependency_signal",
        "content": chunk_content,
        "source_ref": path,
        "start_line": 1,
        "end_line": max(1, len(content.splitlines())),
        "chunk_metadata": {
            "manifest_type": filename,
            "dep_count": len(unique_deps),
        },
    }]


# ─── Documentation / Markdown ─────────────────────────────────────────────────

def _extract_documentation(path: str, content: str) -> list[dict]:
    """
    Split markdown/text into section-based documentation chunks.

    Uses heading boundaries (##, ###) as natural split points.
    Falls back to character-based splitting with overlap for prose without headings.
    """
    sections = _split_by_headings_with_spans(content)
    chunks = []

    for section_title, section_body, section_start_line, _section_end_line in sections:
        pieces = _split_long_text_with_line_spans(
            section_body,
            section_start_line,
            _MAX_CHUNK_CHARS,
            _OVERLAP_CHARS,
        )
        for i, (piece, start_line, end_line) in enumerate(pieces):
            if not piece.strip():
                continue
            label = section_title or PurePosixPath(path).name
            chunks.append({
                "chunk_type": "documentation",
                "content": f"{label}\n\n{piece}".strip(),
                "source_ref": path,
                "start_line": start_line,
                "end_line": end_line,
                "chunk_metadata": {
                    "section": section_title,
                    "part": i,
                },
            })

    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """
    Split markdown text at H1/H2/H3 boundaries.

    Returns a list of (heading_title, body) tuples.
    If there are no headings, returns a single ("", full_text) tuple.
    """
    return [(title, body) for title, body, _start, _end in _split_by_headings_with_spans(text)]


def _split_by_headings_with_spans(text: str) -> list[tuple[str, str, int, int]]:
    """
    Split markdown text at H1/H2/H3 boundaries and retain line spans.
    """
    lines = text.splitlines()
    heading_indexes: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if match:
            heading_indexes.append((idx, match.group(2).strip()))

    if not heading_indexes:
        return [("", text, 1, max(1, len(lines)))]

    sections: list[tuple[str, str, int, int]] = []

    first_heading_idx = heading_indexes[0][0]
    if first_heading_idx > 0:
        preamble_lines = lines[:first_heading_idx]
        preamble_body = "\n".join(preamble_lines).strip()
        if preamble_body:
            sections.append(("", preamble_body, 1, first_heading_idx))

    for i, (heading_idx, title) in enumerate(heading_indexes):
        body_start_idx = heading_idx + 1
        next_heading_idx = heading_indexes[i + 1][0] if i + 1 < len(heading_indexes) else len(lines)
        body_lines = lines[body_start_idx:next_heading_idx]
        body = "\n".join(body_lines).strip()
        start_line = max(1, body_start_idx + 1)
        end_line = max(start_line, next_heading_idx)
        sections.append((title, body, start_line, end_line))

    return sections


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """
    Split text into pieces of at most max_chars characters.

    Splits at paragraph boundaries when possible to preserve readability.
    Falls back to hard splits if a single paragraph exceeds max_chars.
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    pieces = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).lstrip("\n")
        else:
            if current:
                pieces.append(current)
            if len(para) <= max_chars:
                # Start new piece with overlap from previous
                tail = current[-overlap:] if current else ""
                current = (tail + "\n\n" + para).lstrip("\n") if tail else para
            else:
                # Hard-split the paragraph
                for j in range(0, len(para), max_chars - overlap):
                    pieces.append(para[j : j + max_chars])
                current = ""

    if current:
        pieces.append(current)

    return pieces


def _split_long_text_with_line_spans(
    text: str,
    start_line: int,
    max_chars: int,
    overlap: int,
) -> list[tuple[str, int, int]]:
    """
    Split text into chunks while preserving approximate line spans.
    """
    if not text.strip():
        return [(text, start_line, start_line)]

    lines = text.splitlines()
    if not lines:
        return [(text, start_line, start_line)]

    pieces: list[tuple[str, int, int]] = []
    current_lines: list[str] = []
    current_start = start_line
    current_chars = 0
    last_global_line = start_line

    for offset, line in enumerate(lines):
        line_chars = len(line) + (1 if current_lines else 0)
        global_line = start_line + offset

        if len(line) > max_chars:
            if current_lines:
                piece_text = "\n".join(current_lines)
                pieces.append((piece_text, current_start, last_global_line))
                current_lines = []
                current_chars = 0
            step = max(1, max_chars - overlap)
            for j in range(0, len(line), step):
                pieces.append((line[j : j + max_chars], global_line, global_line))
            current_start = global_line + 1
            last_global_line = global_line
            continue

        if current_lines and current_chars + line_chars > max_chars:
            piece_text = "\n".join(current_lines)
            pieces.append((piece_text, current_start, last_global_line))
            overlap_lines: list[str] = []
            overlap_chars = 0
            for candidate in reversed(current_lines):
                addition = len(candidate) + (1 if overlap_lines else 0)
                if overlap_chars + addition > overlap:
                    break
                overlap_lines.insert(0, candidate)
                overlap_chars += addition
            current_lines = overlap_lines + [line]
            current_start = global_line - len(overlap_lines)
            current_chars = sum(len(item) for item in current_lines) + max(0, len(current_lines) - 1)
        else:
            if not current_lines:
                current_start = global_line
            current_lines.append(line)
            current_chars += line_chars

        last_global_line = global_line

    if current_lines:
        pieces.append(( "\n".join(current_lines), current_start, last_global_line))

    return pieces


# ─── Code files ───────────────────────────────────────────────────────────────

def _extract_code_knowledge(
    path: str,
    content: str,
    allow_code_snippets: bool,
) -> list[dict]:
    """
    Extract knowledge from code files.

    Always produces:
    - module_description: docstring, top-level description, class/function names

    If allow_code_snippets=True, also produces:
    - code_snippet: function/class bodies ≤ 60 lines each
      (never full file dumps)
    """
    chunks = []
    suffix = PurePosixPath(path).suffix.lower()

    # 1. Module description
    description = _extract_module_description(path, content, suffix)
    if description:
        chunks.append({
            "chunk_type": "module_description",
            "content": description,
            "source_ref": path,
            "start_line": 1,
            "end_line": max(1, len(content.splitlines())),
            "chunk_metadata": {"language": suffix.lstrip(".")},
        })

    # 2. Code snippets (opt-in)
    if allow_code_snippets:
        snippets = _extract_code_snippets(path, content, suffix)
        chunks.extend(snippets)

    return chunks


def _extract_module_description(path: str, content: str, suffix: str) -> str:
    """
    Build a module-level description from:
    - File-level docstring (Python) or leading block comment (other languages)
    - List of top-level function/class/export names
    - No code bodies — structure only
    """
    lines = content.splitlines()
    parts: list[str] = []

    parts.append(f"Module: {path}")

    # Extract docstring / leading comment
    if suffix == ".py":
        docstring = _extract_python_docstring(lines)
        if docstring:
            parts.append(f"Description: {docstring}")
    else:
        comment = _extract_leading_block_comment(lines, suffix)
        if comment:
            parts.append(f"Description: {comment}")

    # Extract function/class names
    names = _extract_symbol_names(lines, suffix)
    if names:
        parts.append("Exports/symbols: " + ", ".join(names[:50]))

    return "\n".join(parts)


def _extract_python_docstring(lines: list[str]) -> str:
    """Extract module-level docstring from Python source."""
    in_docstring = False
    docstring_lines: list[str] = []
    quote = None

    for line in lines:
        stripped = line.strip()
        if not in_docstring:
            # Skip blank lines and comments at top
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith('"""') or stripped.startswith("'''"):
                quote = stripped[:3]
                # May be a one-liner
                rest = stripped[3:]
                end_idx = rest.find(quote)
                if end_idx != -1:
                    return rest[:end_idx].strip()
                in_docstring = True
                if rest.strip():
                    docstring_lines.append(rest.strip())
            else:
                # No docstring
                break
        else:
            if quote and quote in stripped:
                # End of docstring
                end_idx = stripped.find(quote)
                if end_idx > 0:
                    docstring_lines.append(stripped[:end_idx].strip())
                break
            docstring_lines.append(line.rstrip())

    result = "\n".join(docstring_lines).strip()
    return result[:500] if result else ""


def _extract_leading_block_comment(lines: list[str], suffix: str) -> str:
    """Extract leading block comment or JSDoc from non-Python source."""
    result_lines: list[str] = []
    in_block = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not in_block:
            if stripped.startswith("/*") or stripped.startswith("/**"):
                in_block = True
                rest = stripped[2:].lstrip("* ").strip()
                if rest:
                    result_lines.append(rest)
            elif stripped.startswith("//"):
                result_lines.append(stripped[2:].strip())
            elif stripped.startswith("#"):
                result_lines.append(stripped[1:].strip())
            else:
                break
        else:
            if stripped.startswith("*/") or stripped.endswith("*/"):
                break
            clean = stripped.lstrip("* ").strip()
            if clean:
                result_lines.append(clean)
        if len(result_lines) > 20:
            break

    return " ".join(result_lines)[:500]


def _extract_symbol_names(lines: list[str], suffix: str) -> list[str]:
    """Extract top-level function/class/export names from source code."""
    names: list[str] = []

    if suffix == ".py":
        for line in lines:
            m = re.match(r"^(def|class|async def)\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
            if m and not m.group(2).startswith("_"):
                names.append(f"{m.group(1)} {m.group(2)}")

    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        for line in lines:
            # export function / export class / export const / export default
            m = re.match(
                r"^export\s+(?:default\s+)?(?:async\s+)?(function|class|const|let|var|type|interface)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)",
                line,
            )
            if m:
                names.append(f"{m.group(1)} {m.group(2)}")

    elif suffix == ".go":
        for line in lines:
            m = re.match(r"^func\s+(\([^)]+\)\s+)?([A-Z][a-zA-Z0-9_]*)", line)
            if m:
                names.append(f"func {m.group(2)}")

    elif suffix == ".rs":
        for line in lines:
            m = re.match(r"^pub\s+(?:async\s+)?fn\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
            if m:
                names.append(f"fn {m.group(1)}")

    return names


def _extract_code_snippets(path: str, content: str, suffix: str) -> list[dict]:
    """
    Extract small function/class bodies as code_snippet chunks.

    Limit: max 60 lines per snippet, max 20 snippets per file.
    We never dump the full file — this is always scoped extractions.
    """
    snippets = []
    lines = content.splitlines()
    max_snippets = 20

    if suffix == ".py":
        blocks = _extract_python_blocks(lines)
    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        blocks = _extract_js_blocks(lines)
    else:
        # For other languages, we don't attempt snippet extraction
        return []

    for name, block_lines, start_line, end_line in blocks[:max_snippets]:
        is_truncated = False
        if len(block_lines) > 60:
            # Keep a bounded but useful window. Ten lines was too shallow for
            # React components because it often omitted the handler that makes
            # the API call; sixty lines remains scoped and avoids full-file dumps.
            truncated_lines = block_lines[:59] + [_truncation_notice(suffix)]
            block_lines = truncated_lines
            is_truncated = True

        snippet_text = "\n".join(block_lines)
        snippets.append({
            "chunk_type": "code_snippet",
            "content": f"# {path} — {name}\n\n{snippet_text}",
            "source_ref": path,
            "start_line": start_line,
            "end_line": end_line,
            "chunk_metadata": {
                "symbol_name": name,
                "language": suffix.lstrip("."),
                "line_count": len(block_lines),
                "truncated": is_truncated,
            },
        })

    return snippets


def _truncation_notice(suffix: str) -> str:
    code_suffixes = {
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".swift",
        ".kt",
        ".scala",
    }
    if suffix in code_suffixes:
        return "  // ... (truncated for safety)"
    return "    # ... (truncated for safety)"


def _extract_python_blocks(lines: list[str]) -> list[tuple[str, list[str], int, int]]:
    """
    Extract top-level function and class blocks from Python source.

    Uses indentation to determine block boundaries.
    Private functions (starting with _) are excluded.
    """
    blocks: list[tuple[str, list[str], int, int]] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        m = re.match(r"^(def|class|async def)\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
        if m and not m.group(2).startswith("_"):
            name = f"{m.group(1)} {m.group(2)}"
            start_line = i + 1
            block = [line.rstrip()]
            i += 1

            # Top-level Python definitions often use multi-line signatures:
            #
            #   async def login(
            #       form: OAuth2PasswordRequestForm = Depends(),
            #   ) -> TokenPair:
            #
            # The old indentation-only collector stopped at the unindented
            # closing ``) -> ...:`` line, so snippets for important handlers
            # contained only the signature and no body.  First collect the full
            # signature through the colon, then collect the indented body.
            signature_complete = line.rstrip().endswith(":")
            while i < n and not signature_complete:
                signature_line = lines[i]
                block.append(signature_line.rstrip())
                i += 1
                if signature_line.rstrip().endswith(":"):
                    signature_complete = True

            # Collect indented block
            while i < n:
                next_line = lines[i]
                if next_line.strip() == "":
                    block.append("")
                    i += 1
                    # If next non-empty line is not indented, block is over
                    j = i
                    while j < n and lines[j].strip() == "":
                        j += 1
                    if j < n and lines[j] and not lines[j][0].isspace():
                        break
                elif next_line[0].isspace():
                    block.append(next_line.rstrip())
                    i += 1
                else:
                    break
            # Strip trailing blank lines
            while block and not block[-1].strip():
                block.pop()
            end_line = start_line + max(0, len(block) - 1)
            blocks.append((name, block, start_line, end_line))
        else:
            i += 1

    return blocks


def _extract_js_blocks(lines: list[str]) -> list[tuple[str, list[str], int, int]]:
    """
    Extract exported function/class blocks from TypeScript/JavaScript.

    Collects brace-balanced blocks. Limited to exported symbols.
    """
    blocks: list[tuple[str, list[str], int, int]] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        function_match = re.match(
            r"^export\s+(?:default\s+)?(?:async\s+)?(?:function|class)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)",
            line,
        )
        const_match = re.match(
            r"^export\s+(const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\b",
            line,
        )
        if function_match or const_match:
            name = (
                function_match.group(1)
                if function_match
                else f"{const_match.group(1)} {const_match.group(2)}"
            )
            start_line = i + 1
            block = [line.rstrip()]
            depth = line.count("{") - line.count("}")
            i += 1
            while i < n and depth > 0:
                block.append(lines[i].rstrip())
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
            # Strip trailing blank lines
            while block and not block[-1].strip():
                block.pop()
            end_line = start_line + max(0, len(block) - 1)
            blocks.append((name, block, start_line, end_line))
        else:
            i += 1

    return blocks
