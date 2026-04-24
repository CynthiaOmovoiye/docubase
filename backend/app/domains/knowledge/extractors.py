"""
Knowledge extraction strategies for document sources.

Each extractor takes a path + content string and produces a list of chunk dicts
ready for embedding and storage.

Extractors do NOT run policy checks — that is done by the pipeline before calling
any extractor. All content arriving here has already cleared policy.

Supported source types:
  - PDF (pre-extracted text) → documentation chunks split by section
  - Markdown / plain text    → documentation chunks split by section
  - Google Drive exports     → documentation chunks split by section

Each returned dict has keys matching the Chunk model:
  chunk_type, content, source_ref, chunk_metadata, start_line, end_line, segment_id
"""

import re
from pathlib import PurePosixPath

from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_CHUNK_CHARS = 2000
_OVERLAP_CHARS = 200

# Documentation / markdown extensions
_DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt"}

# Google Drive virtual filenames: ``Name.ext [driveFileId]`` — strip id for suffix detection.
_VIRTUAL_DRIVE_FILE_ID_SUFFIX = re.compile(r"\s*\[[a-zA-Z0-9_\-]{10,100}\]\s*$")


def _leaf_basename_without_virtual_drive_id(path: str) -> str:
    """
    ``pathlib.PurePosixPath`` treats ``Resume.pdf [abc…]`` as suffix ``.pdf [abc…]``, so PDFs
    miss ``.pdf`` classification and raw/structure text is chunked as generic documentation.
    """
    leaf = path.replace("\\", "/").split("/")[-1]
    return _VIRTUAL_DRIVE_FILE_ID_SUFFIX.sub("", leaf.strip())


def _try_recover_pdf_bytes_from_latin1_string(s: str) -> bytes | None:
    """If a PDF was decoded as Latin-1 into a str, recover bytes for pypdf."""
    t = s.lstrip("\ufeff \n\r\t")
    if len(t) < 5 or not t.startswith("%PDF"):
        return None
    try:
        return t.encode("latin-1")
    except UnicodeEncodeError:
        return None


def _is_binary_content(text: str) -> bool:
    """
    True when the string is almost certainly binary data masquerading as text.

    Two independent signals, either of which is sufficient to reject:
    1. High density of Unicode replacement chars (\\ufffd) or low-ASCII control
       bytes — typical of UTF-8 decode errors on raw binary.
    2. Low ratio of "readable prose" characters — catches pypdf output on PDFs
       with broken/non-standard CMap tables, where the result is wrong-but-valid
       Unicode (not replacement chars) so signal #1 misses it.
    """
    if not text:
        return True
    # Signal 1: replacement chars + control bytes
    bad = sum(1 for c in text if c == "\ufffd" or (ord(c) < 32 and c not in "\t\n\r\v\f"))
    if bad > max(3, len(text) // 100):
        return True
    # Signal 2: readable character ratio (same logic as text_extract._readable_char_ratio)
    def _ok(c: str) -> bool:
        cp = ord(c)
        return (
            c in " \t\n\r\v\f"
            or 0x20 <= cp <= 0x7E
            or 0xA0 <= cp <= 0x024F
            or 0x2000 <= cp <= 0x206F
            or 0x4E00 <= cp <= 0x9FFF
        )
    ratio = sum(1 for c in text if _ok(c)) / len(text)
    return ratio < 0.70


def _extract_pdf_as_documentation(path: str, content: str) -> list[dict]:
    """
    PDFs arrive as pre-extracted plaintext from connectors; repair raw-PDF strings if needed.
    """
    from app.connectors.pdf.text_extract import (
        extract_readable_pdf_text_from_bytes,
        pdf_syntax_noise_score,
    )

    body = content
    recovered = _try_recover_pdf_bytes_from_latin1_string(body)
    if recovered is not None:
        text = extract_readable_pdf_text_from_bytes(recovered, name=path)
        if text:
            body = text
        else:
            logger.warning("ingestion_pdf_rejected_or_unparsed", path=path)
            return []
    elif pdf_syntax_noise_score(body) > 0.025:
        logger.warning(
            "ingestion_pdf_high_syntax_noise",
            path=path,
            score=round(pdf_syntax_noise_score(body), 5),
        )
        return []

    if _is_binary_content(body):
        logger.warning("ingestion_pdf_binary_content_rejected", path=path)
        return []

    return _extract_documentation(path, body)


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
    leaf = _leaf_basename_without_virtual_drive_id(path)
    suffix = PurePosixPath(leaf).suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf_as_documentation(path, content)

    # Markdown, plain text, and any unrecognised type → documentation chunks
    return _extract_documentation(path, content)


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
            label = section_title or PurePosixPath(_leaf_basename_without_virtual_drive_id(path)).name
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


