"""
Shared PDF → human-readable text for ingestion (pypdf first, PyMuPDF fallback).

This mirrors the common “Drive → download PDF bytes → PdfReader → page.extract_text()”
pattern described in public write-ups (e.g. PyPDF2-style loops per page). We use
**Drive API** ``files.get(alt=media)`` with OAuth rather than ``webViewLink`` + gdown,
which is more reliable for server-side sync.

**pypdf** (maintained fork of PyPDF2) sometimes returns xref-table / trailer text on
certain producer PDFs; that output is mostly digits/spaces and incorrectly passes a
naive “printable ratio” check. We detect xref-style lines and fall back to **PyMuPDF**
(``import fitz``) when needed.
"""

from __future__ import annotations

import io
import re

from app.core.logging import get_logger

logger = get_logger(__name__)

_PDF_HEADER = b"%PDF"
# WPS, some scanners, and other tools write a few bytes (or a BOM) before the PDF header.
# If we require ``data[:4] == b'%PDF'`` only, we skip pypdf and can accidentally UTF-8-decode
# the file into mojibake chunks (the failure seen in the ``chunks`` table for Drive PDFs).
_MAX_LEADING_GARBAGE_BEFORE_PDF = 65_535


def align_pdf_bytes(data: bytes) -> bytes | None:
    """
    Return a byte slice that starts at the first standard ``%PDF`` header, or None.

    Many real-world PDFs (e.g. WPS Writer) are valid but do not start at byte 0 with ``%PDF``.
    """
    if not data or len(data) < 5:
        return None
    if data.startswith(_PDF_HEADER):
        return data
    end = min(len(data), _MAX_LEADING_GARBAGE_BEFORE_PDF)
    i = data.find(_PDF_HEADER, 0, end)
    if i < 0:
        return None
    if i > 0:
        logger.info("pdf_leading_bytes_stripped_before_header", offset=i, new_len=len(data) - i)
    return data[i:]


# PDF object / structure tokens — high counts mean extract_text leaked structure, not body text.
_PDF_NOISE_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"\bendobj\b",
        r"\b\d+\s+\d+\s+R\b",  # indirect refs like "12 0 R"
        r"/Type\s*/",
        r"/StructElem",
        r"/ParentTree",
        r"<\</",
        r"\bstream\r?\n",
        r"\bendstream\b",
        r"/Root\s",
        r"/Size\s",
        r"startxref",
        r"trailer\s*<<",
        r"%%EOF",
    )
)

# Xref subsection lines (offset + generation + in-use "n" or free "f")
_XREF_SUBSECTION_LINE = re.compile(r"^\d{6,12} \d{1,6} [nf]\s*$")


def pdf_syntax_noise_score(text: str) -> float:
    """
    Higher = more likely raw PDF / structure dump (not usable prose).

    Scale is roughly 0 (clean) … 0.1+ (reject).
    """
    if not text or not text.strip():
        return 1.0
    n = len(text)
    hits = sum(len(p.findall(text)) for p in _PDF_NOISE_PATTERNS)
    ctrl = sum(1 for c in text if ord(c) < 32 and c not in "\n\r\t\f\v")
    return (hits * 4 + ctrl) / max(n, 1)


def xref_subsection_line_ratio(text: str) -> float:
    """
    Lines like ``0000060954 00000 n`` are xref table entries, not resume prose.

    pypdf can surface these as "text" on some PDFs; they look "printable" because
    they are mostly digits.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0.0
    hits = sum(1 for ln in lines if _XREF_SUBSECTION_LINE.match(ln))
    return hits / len(lines)


def _looks_like_xref_table_or_tail(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    low = t.lower()
    r = xref_subsection_line_ratio(t)
    if r >= 0.08:
        return True
    if r >= 0.02 and "startxref" in low and "%%eof" in low.replace(" ", ""):
        return True
    return "trailer<<" in t.replace(" ", "") and r >= 0.02


def _readable_char_ratio(text: str) -> float:
    """
    Fraction of characters that look like human-readable prose.

    Accepts ASCII printable, common whitespace, Latin extended A/B (accented
    chars), general punctuation, and CJK ideographs.  Rejects content dominated
    by Unicode replacement chars (U+FFFD), private-use glyphs, or other
    non-prose code points — the signature of pypdf decoding failures on PDFs
    with broken or non-standard CMap tables.
    """
    if not text:
        return 0.0

    def _ok(c: str) -> bool:
        cp = ord(c)
        if c in " \t\n\r\v\f":
            return True
        if 0x20 <= cp <= 0x7E:  # printable ASCII
            return True
        if 0xA0 <= cp <= 0x024F:  # Latin-1 supplement + extended A/B (é ñ ü …)
            return True
        if 0x2000 <= cp <= 0x206F:  # general punctuation (curly quotes, em-dash …)
            return True
        return 0x4E00 <= cp <= 0x9FFF  # CJK unified ideographs

    return sum(1 for c in text if _ok(c)) / len(text)


def _extract_pages_pypdf(reader: object, *, extraction_mode: str) -> str:
    """Same idea as the classic PyPDF2 loop: one extract_text() per page."""
    parts: list[str] = []
    for page_num, page in enumerate(reader.pages, start=1):
        try:
            try:
                raw = page.extract_text(extraction_mode=extraction_mode)
            except TypeError:
                raw = page.extract_text()
        except Exception as e:
            logger.warning(
                "pdf_page_extract_error",
                page=page_num,
                mode=extraction_mode,
                error=str(e),
            )
            continue
        text = (raw or "").strip()
        if text:
            parts.append(f"--- Page {page_num} ---\n{text}")
    return "\n\n".join(parts).strip()


def _extract_pymupdf(data: bytes, *, name: str) -> str | None:
    """
    PyMuPDF (``fitz``) — often recovers real body text when pypdf returns xref/tailer junk.
    """
    try:
        import fitz
    except ImportError:
        logger.warning("pymupdf_not_installed")
        return None
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        logger.debug("pymupdf_open_failed", name=name, error=str(e))
        return None
    parts: list[str] = []
    try:
        for i in range(len(doc)):
            try:
                raw = doc[i].get_text()
            except Exception as e:
                logger.warning("pymupdf_page_error", name=name, page=i, error=str(e))
                continue
            text = (raw or "").strip()
            if text:
                parts.append(f"--- Page {i + 1} ---\n{text}")
    finally:
        doc.close()
    return "\n\n".join(parts).strip() or None


def _accept_extracted_prose(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    # pypdf must never "extract" a raw file header into the output string
    if "%PDF" in (text.lstrip()[:200]):
        return False
    if _looks_like_xref_table_or_tail(text):
        logger.debug("pdf_reject_xref_dump", sample=text[:120].replace("\n", " "))
        return False
    if pdf_syntax_noise_score(text) > 0.025:
        return False
    return not _readable_char_ratio(text) < 0.70


def extract_readable_pdf_text_from_bytes(data: bytes, *, name: str = "") -> str | None:
    """
    Extract readable UTF-8 from a PDF byte blob.

    1) pypdf ``plain`` and ``layout``; pick the lower structure-noise candidate.
    2) If that fails validation (including xref/tailer dumps), try PyMuPDF.
    """
    data = align_pdf_bytes(data) or b""
    if len(data) < 5 or not data.startswith(b"%PDF"):
        return None

    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf_not_installed")
        return None

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception as e:
        logger.warning("pdf_reader_open_failed", name=name, error=str(e))
        return None

    plain = _extract_pages_pypdf(reader, extraction_mode="plain")
    plain_score = pdf_syntax_noise_score(plain) if plain else 1.0

    layout = ""
    layout_score = 1.0
    try:
        layout = _extract_pages_pypdf(reader, extraction_mode="layout")
        layout_score = pdf_syntax_noise_score(layout) if layout else 1.0
    except Exception as e:
        logger.debug("pdf_layout_extract_unavailable", name=name, error=str(e))

    candidates: list[tuple[str, float]] = []
    if plain:
        candidates.append((plain, plain_score))
    if layout:
        candidates.append((layout, layout_score))
    if not candidates:
        logger.warning("pdf_no_text_extracted", name=name)
        fitz_only = _extract_pymupdf(data, name=name)
        return fitz_only if _accept_extracted_prose(fitz_only) else None

    chosen, score = min(candidates, key=lambda x: x[1])
    if _accept_extracted_prose(chosen):
        return chosen

    logger.info("pdf_pypdf_rejected_trying_pymupdf", name=name, pypdf_noise=round(score, 5))
    fitz_text = _extract_pymupdf(data, name=name)
    if _accept_extracted_prose(fitz_text):
        return fitz_text

    logger.warning("pdf_extraction_all_strategies_rejected", name=name, pypdf_chars=len(chosen or ""))
    return None


def extract_readable_pdf_text_from_path(file_path: str) -> str | None:
    """Read a PDF from disk and extract the same way as Drive bytes."""
    try:
        with open(file_path, "rb") as handle:
            data = handle.read()
    except OSError as e:
        logger.warning("pdf_read_failed", path=file_path, error=str(e))
        return None
    return extract_readable_pdf_text_from_bytes(data, name=file_path)
