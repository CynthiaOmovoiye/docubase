from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.domains.answering.verifier import AnswerVerificationResult
from app.domains.retrieval.packets import RetrievalEvidencePacket

_BACKTICK_RE = re.compile(r"`([^`\n]{1,160})`")
_PLAIN_FILE_RE = re.compile(
    r"\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b|\b[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|jsx|json|yaml|yml|sql|md|toml|go|java|rb|php|rs)\b"
)
_SECTION_HEADER_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
_BOUNDED_NEGATIVE_RE = re.compile(
    r"\b(did not find grounded evidence|could not find grounded evidence|couldn't verify|can't verify)\b",
    re.IGNORECASE,
)
_STRONG_NEGATIVE_RE = re.compile(
    r"\b(there is no|there are no|does not use|doesn't use|not present|is absent|without any?|without an?)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class AnswerQualityMetrics:
    mode: str
    search_substrate: str | None
    searched_layers: int
    missing_evidence_count: int
    citation_count: int
    grounded_anchor_present: bool
    negative_claims_bounded: bool
    false_not_present_risk: bool
    verifier_issues_count: int
    verifier_retry_requested: bool
    verifier_rewritten: bool
    workspace_project_count: int | None = None
    workspace_labels_complete: bool | None = None
    cross_project_leakage_detected: bool | None = None

    def to_log_dict(self) -> dict:
        return asdict(self)


def build_single_project_quality_metrics(
    *,
    answer: str,
    packet: RetrievalEvidencePacket | None,
    verification: AnswerVerificationResult | None,
    retry_requested: bool,
) -> AnswerQualityMetrics:
    allowed_files, allowed_symbols = _build_allowed_refs(packet)
    citation_count = _count_supported_citations(answer, allowed_files, allowed_symbols)
    grounded_anchor_present = _contains_grounded_anchor(answer, allowed_files, allowed_symbols)

    return AnswerQualityMetrics(
        mode=packet.mode.value if packet else "deterministic_fallback",
        search_substrate=packet.search_substrate if packet else None,
        searched_layers=len(packet.searched_layers) if packet else 0,
        missing_evidence_count=len(packet.missing_evidence) if packet else 0,
        citation_count=citation_count,
        grounded_anchor_present=grounded_anchor_present,
        negative_claims_bounded=not _STRONG_NEGATIVE_RE.search(answer) or bool(_BOUNDED_NEGATIVE_RE.search(answer)),
        false_not_present_risk=bool(_STRONG_NEGATIVE_RE.search(answer) and not _BOUNDED_NEGATIVE_RE.search(answer)),
        verifier_issues_count=len(verification.issues) if verification else 0,
        verifier_retry_requested=retry_requested,
        verifier_rewritten=bool(verification.rewritten if verification else False),
    )


def build_workspace_quality_metrics(
    *,
    answer: str,
    project_contexts: list[dict],
    verification: AnswerVerificationResult,
    retry_requested: bool,
) -> AnswerQualityMetrics:
    headers = {match.group(1).strip() for match in _SECTION_HEADER_RE.finditer(answer)}
    expected_names = [str(project.get("name") or "Unnamed project") for project in project_contexts]

    return AnswerQualityMetrics(
        mode="workspace_comparison",
        search_substrate="postgres_fts",
        searched_layers=sum(
            len(packet.searched_layers)
            for packet in (
                project.get("evidence_packet")
                for project in project_contexts
            )
            if packet is not None
        ),
        missing_evidence_count=sum(
            len((project.get("evidence_packet").missing_evidence if project.get("evidence_packet") else []))
            for project in project_contexts
        ),
        citation_count=sum(
            _count_supported_citations(
                answer,
                *_build_allowed_refs(project.get("evidence_packet")),
            )
            for project in project_contexts
            if project.get("evidence_packet") is not None
        ),
        grounded_anchor_present=any(
            _contains_grounded_anchor(
                answer,
                *_build_allowed_refs(project.get("evidence_packet")),
            )
            for project in project_contexts
            if project.get("evidence_packet") is not None
        ),
        negative_claims_bounded=not _STRONG_NEGATIVE_RE.search(answer) or bool(_BOUNDED_NEGATIVE_RE.search(answer)),
        false_not_present_risk=bool(_STRONG_NEGATIVE_RE.search(answer) and not _BOUNDED_NEGATIVE_RE.search(answer)),
        verifier_issues_count=len(verification.issues),
        verifier_retry_requested=retry_requested,
        verifier_rewritten=verification.rewritten,
        workspace_project_count=len(project_contexts),
        workspace_labels_complete=all(name in headers for name in expected_names),
        cross_project_leakage_detected=any(issue.startswith("cross_project_leakage") for issue in verification.issues),
    )


def _build_allowed_refs(
    packet: RetrievalEvidencePacket | None,
) -> tuple[set[str], set[str]]:
    if packet is None:
        return set(), set()

    file_refs: set[str] = set()
    for file_ref in packet.files:
        file_refs.add(_normalise(file_ref.path))
        file_refs.add(_normalise(file_ref.path.rsplit("/", 1)[-1]))
    for span in packet.spans:
        if span.path:
            file_refs.add(_normalise(span.path))
            file_refs.add(_normalise(span.path.rsplit("/", 1)[-1]))

    symbol_refs: set[str] = set()
    for symbol in packet.symbols:
        symbol_refs.add(_normalise(symbol.symbol_name))
        symbol_refs.add(_normalise(symbol.qualified_name))
        symbol_refs.add(_normalise(symbol.qualified_name.rsplit(".", 1)[-1]))
    return file_refs, symbol_refs


def _count_supported_citations(
    answer: str,
    allowed_files: set[str],
    allowed_symbols: set[str],
) -> int:
    file_refs, symbol_refs = _extract_explicit_refs(answer)
    citations = {
        ref for ref in file_refs
        if ref in allowed_files
    }
    citations.update(
        ref for ref in symbol_refs
        if ref in allowed_symbols or ref in allowed_files
    )
    return len(citations)


def _contains_grounded_anchor(
    answer: str,
    allowed_files: set[str],
    allowed_symbols: set[str],
) -> bool:
    lowered = answer.lower()
    for ref in allowed_files | allowed_symbols:
        if ref and ref.lower() in lowered:
            return True
    return False


def _extract_explicit_refs(answer: str) -> tuple[set[str], set[str]]:
    file_refs = {_normalise(match.group(0)) for match in _PLAIN_FILE_RE.finditer(answer)}
    symbol_refs: set[str] = set()
    for match in _BACKTICK_RE.finditer(answer):
        token = match.group(1).strip()
        if _looks_like_file_ref(token):
            file_refs.add(_normalise(token))
        elif _looks_like_symbol_ref(token):
            symbol_refs.add(_normalise(token))
    return file_refs, symbol_refs


def _looks_like_file_ref(token: str) -> bool:
    normalised = _normalise(token)
    return bool(normalised and ("/" in normalised or _PLAIN_FILE_RE.fullmatch(normalised)))


def _looks_like_symbol_ref(token: str) -> bool:
    normalised = _normalise(token)
    return bool(
        normalised
        and not _looks_like_file_ref(normalised)
        and (
            "_" in normalised
            or "." in normalised
            or "(" in normalised
            or any(char.isupper() for char in normalised[1:])
        )
    )


def _normalise(value: str) -> str:
    return value.strip().strip("`").strip()
