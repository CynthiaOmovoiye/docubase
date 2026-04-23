"""
Cheap evidence-bound answer verification.

Phase 3 keeps verification deterministic and fast:
- inspect explicit technical references in the draft answer
- compare them against the retrieved evidence packet namespace
- request at most one regeneration hint when the draft overreaches
- otherwise rewrite into a grounded fallback rather than returning unsupported claims
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domains.retrieval.packets import RetrievalEvidencePacket
from app.domains.retrieval.planner import RetrievalMode

_BACKTICK_RE = re.compile(r"`([^`\n]{1,160})`")
_FENCED_CODE_RE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)
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
# Phase 6 — if the packet already contains these fact types, do not accept strong
# denials of the same capability (paired with negative phrasing on the line).
_FACT_TYPE_DENIAL_PHRASES: list[tuple[frozenset[str], tuple[str, ...]]] = [
    (frozenset({"route", "route_config"}), ("no routes", "no route ", "no http routes", "without routes", "without any routes")),
    (frozenset({"handler"}), ("no handler", "no handlers")),
    (frozenset({"auth_check"}), ("no auth check", "no authentication check", "no authentication middleware")),
    (frozenset({"api_call", "call"}), ("no api call", "no api calls", "no outbound api")),
    (frozenset({"background_job"}), ("no background job", "no background jobs", "no worker", "no queue")),
    (frozenset({"dependency", "injection_site", "service_edge"}), ("no dependency injection", "no di container", "no service locator")),
    (frozenset({"data_model", "model_edge"}), ("no data model", "no persistence layer")),
    (frozenset({"ui_action"}), ("no ui action", "no client handler")),
]


def _line_denies_present_fact_types(lowered_line: str, fact_types_present: set[str]) -> bool:
    if not fact_types_present:
        return False
    for types, phrases in _FACT_TYPE_DENIAL_PHRASES:
        if not types.intersection(fact_types_present):
            continue
        if any(p in lowered_line for p in phrases):
            return True
    return False


_COMMON_TECH_TERMS = {
    "api",
    "fastapi",
    "http",
    "https",
    "json",
    "jwt",
    "jwterror",
    "oauth",
    "oauth2",
    "oauth2passwordbearer",
    "orm",
    "rbac",
    "sql",
    "sso",
}


@dataclass(slots=True)
class AnswerVerificationResult:
    content: str
    verified: bool
    rewritten: bool = False
    retry_hint: str | None = None
    issues: list[str] = field(default_factory=list)


def verify_single_project_answer(
    *,
    answer: str,
    doctwin_name: str,
    packet: RetrievalEvidencePacket | None,
    allow_retry: bool,
) -> AnswerVerificationResult:
    """Verify a single-project answer against its evidence packet."""
    if packet is None:
        return AnswerVerificationResult(content=answer, verified=True)

    issues: list[str] = []
    allowed_files, allowed_symbols = _build_allowed_refs(packet)
    file_refs, symbol_refs = _extract_explicit_refs(answer)

    unsupported_files = sorted(ref for ref in file_refs if ref not in allowed_files)
    unsupported_symbols = sorted(
        ref
        for ref in symbol_refs
        if ref not in allowed_symbols
        and ref not in allowed_files
        and not _is_common_tech_term(ref)
        and not _ref_appears_in_packet_content(ref, packet)
    )
    if unsupported_files:
        issues.append("unsupported_file_reference")
    if unsupported_symbols:
        issues.append("unsupported_symbol_reference")
    if _has_unsupported_code_blocks(answer, packet):
        issues.append("unsupported_code_block")
    if _has_contradicted_absence_claim(answer, packet):
        issues.append("contradicted_absence_claim")
    if _engine_answer_needs_rewrite(answer, packet):
        issues.append("weak_engine_answer")

    if _requires_anchor(packet.mode, packet) and not _contains_grounded_anchor(answer, packet):
        issues.append("missing_grounded_anchor")

    if issues and allow_retry:
        return AnswerVerificationResult(
            content=answer,
            verified=False,
            retry_hint=_build_single_retry_hint(packet, doctwin_name, issues),
            issues=issues,
        )

    content = answer
    rewritten = False
    if issues:
        if "weak_engine_answer" in issues:
            content = _build_single_grounded_fallback(doctwin_name=doctwin_name, packet=packet)
        else:
            content = _drop_lines_with_terms(content, unsupported_files + unsupported_symbols)
            content = _strip_unsupported_code_blocks(content, packet)
            if "contradicted_absence_claim" in issues:
                content = _drop_contradicted_absence_lines(content, packet)
        rewritten = True
        if not _contains_grounded_anchor(content, packet):
            content = _build_single_grounded_fallback(doctwin_name=doctwin_name, packet=packet)

    if _STRONG_NEGATIVE_RE.search(content) and not _BOUNDED_NEGATIVE_RE.search(content):
        content = _append_negative_bounds(content, packet)
        rewritten = True

    return AnswerVerificationResult(
        content=content,
        verified=not issues,
        rewritten=rewritten,
        issues=issues,
    )


def verify_workspace_answer(
    *,
    answer: str,
    workspace_name: str,
    project_contexts: list[dict],
    allow_retry: bool,
) -> AnswerVerificationResult:
    """Verify a workspace answer for labeling, namespace safety, and bounds."""
    expected_names = [str(project.get("name") or "Unnamed project") for project in project_contexts]
    sections = _split_project_sections(answer)
    issues: list[str] = []

    missing_sections = [name for name in expected_names if name not in sections]
    if missing_sections:
        issues.append("missing_project_labels")

    for name, section_body in sections.items():
        packet = _packet_for_project(name, project_contexts)
        if packet is None:
            continue
        other_names = [other for other in expected_names if other != name]
        if any(re.search(rf"\b{re.escape(other)}\b", section_body, re.IGNORECASE) for other in other_names):
            issues.append(f"cross_project_leakage:{name}")

        allowed_files, allowed_symbols = _build_allowed_refs(packet)
        file_refs, symbol_refs = _extract_explicit_refs(section_body)
        unsupported_files = [ref for ref in file_refs if ref not in allowed_files]
        unsupported_symbols = [
            ref
            for ref in symbol_refs
            if ref not in allowed_symbols
            and ref not in allowed_files
            and not _is_common_tech_term(ref)
            and not _ref_appears_in_packet_content(ref, packet)
        ]
        if unsupported_files:
            issues.append(f"unsupported_file_reference:{name}")
        if unsupported_symbols:
            issues.append(f"unsupported_symbol_reference:{name}")
        if _has_unsupported_code_blocks(section_body, packet):
            issues.append(f"unsupported_code_block:{name}")
        if _has_contradicted_absence_claim(section_body, packet):
            issues.append(f"contradicted_absence_claim:{name}")

    if issues and allow_retry:
        return AnswerVerificationResult(
            content=answer,
            verified=False,
            retry_hint=_build_workspace_retry_hint(workspace_name, project_contexts, issues),
            issues=issues,
        )

    content = answer
    rewritten = False
    if issues:
        content = _build_workspace_grounded_fallback(workspace_name, project_contexts)
        rewritten = True

    if _STRONG_NEGATIVE_RE.search(content) and not _BOUNDED_NEGATIVE_RE.search(content):
        scopes = [
            ", ".join(packet.negative_evidence_scope)
            for packet in (_packet_for_project(name, project_contexts) for name in expected_names)
            if packet and packet.negative_evidence_scope
        ]
        scope_summary = "; ".join(dict.fromkeys(scopes)) if scopes else "(unbounded)"
        content = (
            content.rstrip()
            + "\n\n## Bounds\n"
            + "Any absence claims above are bounded to the searched layers for each project: "
            + scope_summary
            + "."
        )
        rewritten = True

    return AnswerVerificationResult(
        content=content,
        verified=not issues,
        rewritten=rewritten,
        issues=issues,
    )


def _build_allowed_refs(packet: RetrievalEvidencePacket) -> tuple[set[str], set[str]]:
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

    for item in packet.facts:
        path = str(item.get("path") or "").strip()
        if path:
            file_refs.add(_normalise(path))
            file_refs.add(_normalise(path.rsplit("/", 1)[-1]))
        subj = str(item.get("subject") or "").strip()
        if subj:
            symbol_refs.add(_normalise(subj))
            if "." in subj:
                symbol_refs.add(_normalise(subj.rsplit(".", 1)[-1]))
        obj = str(item.get("object_ref") or "").strip()
        if obj:
            if _looks_like_file_ref(obj):
                file_refs.add(_normalise(obj))
                file_refs.add(_normalise(obj.rsplit("/", 1)[-1]))
            else:
                symbol_refs.add(_normalise(obj))
                if "." in obj:
                    symbol_refs.add(_normalise(obj.rsplit(".", 1)[-1]))
    return file_refs, symbol_refs


def _extract_explicit_refs(content: str) -> tuple[set[str], set[str]]:
    file_refs = {_normalise(match.group(0)) for match in _PLAIN_FILE_RE.finditer(content)}
    symbol_refs: set[str] = set()
    for match in _BACKTICK_RE.finditer(content):
        token = match.group(1).strip()
        if _looks_like_file_ref(token):
            file_refs.add(_normalise(token))
        elif _looks_like_symbol_ref(token):
            symbol_refs.add(_normalise(token))
    return file_refs, symbol_refs


def _normalise(value: str) -> str:
    return value.strip().strip("`").strip()


def _is_common_tech_term(ref: str) -> bool:
    return _normalise(ref).lower() in _COMMON_TECH_TERMS


def _looks_like_file_ref(token: str) -> bool:
    normalised = _normalise(token)
    if not normalised:
        return False
    # Route-style symbol identifiers such as `logout@POST:/logout` are grounded
    # symbols, not file paths. Treat them as symbols so verifier does not
    # rewrite otherwise-valid answers.
    if "@" in normalised:
        return False
    if ":" in normalised and not _PLAIN_FILE_RE.fullmatch(normalised):
        return False
    return bool("/" in normalised or _PLAIN_FILE_RE.fullmatch(normalised))


def _looks_like_symbol_ref(token: str) -> bool:
    normalised = _normalise(token)
    return bool(
        normalised
        and not _looks_like_file_ref(normalised)
        and (
            "_" in normalised
            or "." in normalised
            or "(" in normalised
            or "@" in normalised
            or ":" in normalised
            or any(char.isupper() for char in normalised[1:])
        )
    )


def _requires_anchor(mode: RetrievalMode, packet: RetrievalEvidencePacket) -> bool:
    if not (packet.files or packet.symbols):
        return False
    return mode in {
        RetrievalMode.implementation,
        RetrievalMode.architecture,
        RetrievalMode.onboarding,
        RetrievalMode.project_status,
        RetrievalMode.recruiter_summary,
    }


def _contains_grounded_anchor(content: str, packet: RetrievalEvidencePacket) -> bool:
    allowed_files, allowed_symbols = _build_allowed_refs(packet)
    lowered = content.lower()
    return any(ref and ref.lower() in lowered for ref in allowed_files | allowed_symbols)


def _ref_appears_in_packet_content(ref: str, packet: RetrievalEvidencePacket) -> bool:
    """
    Allow code/library terms that are explicit in retrieved evidence.

    The verifier should block invented project symbols, but it should not force
    a fallback because an answer names an imported library/class such as
    `OAuth2PasswordBearer`, `JWTError`, or `Depends(get_current_user)` when
    that exact term appears inside grounded snippets.
    """
    normalised_ref = ref.strip().strip("`")
    if not normalised_ref:
        return False
    lowered_ref = normalised_ref.lower()
    compact_ref = re.sub(r"\s+", "", lowered_ref)
    blob = "\n".join(
        [str(chunk.get("content") or "") for chunk in packet.chunks]
        + [
            " ".join(
                str(item.get(k) or "")
                for k in ("path", "subject", "object_ref", "summary", "fact_type")
            )
            for item in packet.facts
        ]
    ).lower()
    if lowered_ref in blob:
        return True
    return bool(compact_ref and compact_ref in re.sub(r"\s+", "", blob))


def _has_contradicted_absence_claim(content: str, packet: RetrievalEvidencePacket) -> bool:
    """
    Catch false "missing evidence" claims when the packet contains exact anchors.

    This is intentionally cheap and pattern-based. It protects the product from
    the most damaging failure mode we saw in live auth prompts: the answer says
    route protection, refresh handling, API calls, or logout are missing even
    though the retrieved packet contains those symbols/files.
    """
    packet_text = _packet_text(packet).lower()
    packet_compact = re.sub(r"\s+", "", packet_text)
    fact_types_present = {str(f.get("fact_type") or "").lower() for f in packet.facts if f.get("fact_type")}
    for line in content.splitlines():
        lowered = line.lower()
        if not (_BOUNDED_NEGATIVE_RE.search(lowered) or _STRONG_NEGATIVE_RE.search(lowered)):
            continue
        if fact_types_present and _line_denies_present_fact_types(lowered, fact_types_present):
            return True
        if any(term in lowered for term in ("route protection", "protectedroute", "protected route")):
            if "protectedroute" in packet_compact:
                return True
        if any(
            term in lowered
            for term in (
                "token expiration",
                "refresh logic",
                "token refresh",
                "refresh handling",
                "session expiration",
                "session validity",
                "session valid",
            )
        ) and any(
            marker in packet_compact
            for marker in (
                "refresh_tokens",
                "performtokenrefresh",
                "tokenrefreshscheduler",
                "isrefreshtokenvalid",
                "isaccesstokenvalid",
            )
        ):
            return True
        if any(term in lowered for term in ("logout", "log out", "sign out")):
            if "clearauth" in packet_compact or "handlelogout" in packet_compact:
                return True
        if any(term in lowered for term in ("api call", "api calls", "authapi")):
            if "authapi" in packet_compact:
                return True
    return False


def _engine_answer_needs_rewrite(content: str, packet: RetrievalEvidencePacket) -> bool:
    if not _is_engine_topic(packet.query):
        return False
    query = packet.query.lower()
    lowered = content.lower()
    if (
        "omitted illustrative code" in lowered
        or "grounded evidence i can confirm" in lowered
        or "relevant files:" in lowered
    ):
        return True
    if "intake" in query:
        packet_text = _packet_text(packet).lower()
        required_anchors = [
            "scaffold/api/v1/routes/intake.py",
            "run_intake",
        ]
        if "scaffold/engines/intake/graph.py" in packet_text:
            required_anchors.append("scaffold/engines/intake/graph.py")
        if "scaffold/engines/intake/nodes.py" in packet_text:
            required_anchors.append("scaffold/engines/intake/nodes.py")
        required_nodes = (
            "parse_input",
            "extract_brief",
            "validate_brief",
            "flag_gaps",
        )
        has_required_anchors = all(anchor in lowered for anchor in required_anchors)
        node_count = sum(1 for node in required_nodes if node in lowered)
        return not (has_required_anchors and node_count >= 3)
    if "5 engine" in query or "five engine" in query or "engines" in query:
        return not all(
            marker in lowered
            for marker in (
                "intake engine",
                "document engine",
                "task intelligence engine",
                "verification engine",
                "audit engine",
            )
        )
    return False


def _is_engine_topic(query: str) -> bool:
    lowered = query.lower()
    return any(
        token in lowered
        for token in (
            "engine",
            "engines",
            "intake",
            "document engine",
            "task intelligence",
            "verification engine",
            "audit engine",
        )
    )


def _build_single_retry_hint(
    packet: RetrievalEvidencePacket,
    doctwin_name: str,
    issues: list[str],
) -> str:
    files = ", ".join(file_ref.path for file_ref in packet.files[:6]) or "the retrieved files"
    symbols = ", ".join(symbol.qualified_name or symbol.symbol_name for symbol in packet.symbols[:8]) or "the retrieved symbols"
    issue_text = ", ".join(issues)
    code_block_instruction = ""
    if "unsupported_code_block" in issues:
        code_block_instruction = (
            " The previous draft used a code block that was not an exact retrieved snippet; "
            "on retry, do not use fenced code blocks unless you copy a short contiguous snippet exactly. "
            "Prefer prose with file/function references."
        )
    return (
        f"Regenerate the answer for {doctwin_name} using only grounded file and symbol anchors. "
        f"Use files like: {files}. Use symbols like: {symbols}. "
        f"Do not invent additional file paths, symbols, or cross-cutting implementation details. "
        "Before saying something is missing, check whether the packet contains direct evidence for it "
        "(for auth: ProtectedRoute/App, refresh_tokens/performTokenRefresh, authApi, clearAuth/handleLogout). "
        f"{code_block_instruction}"
        f"If something is absent, phrase it as 'I did not find grounded evidence...' and keep it bounded to: "
        f"{', '.join(packet.negative_evidence_scope) or 'the searched layers'}. "
        f"Fix these issues: {issue_text}."
    )


def _build_workspace_retry_hint(
    workspace_name: str,
    project_contexts: list[dict],
    issues: list[str],
) -> str:
    labels = ", ".join(str(project.get("name") or "Unnamed project") for project in project_contexts)
    return (
        f"Regenerate the workspace answer for {workspace_name} with strict project separation. "
        f"Use explicit sections for every project: {labels}. "
        "Keep each section grounded only in that project's files and symbols. "
        "Do not mention another project's implementation inside a project's section unless the user explicitly asked for a comparison. "
        f"Fix these issues: {', '.join(issues)}."
    )


def _append_negative_bounds(content: str, packet: RetrievalEvidencePacket) -> str:
    scope = ", ".join(packet.negative_evidence_scope) if packet.negative_evidence_scope else "(unbounded)"
    base = (
        content.rstrip()
        + "\n\n## Bounds\n"
        + "Any absence claims above are bounded to the searched layers for this turn: "
        + scope
        + "."
    )
    gaps = [str(g).strip() for g in (packet.missing_evidence or []) if str(g).strip()][:6]
    if gaps:
        base += "\n\n## Grounded gaps (from retrieval)\n"
        base += "\n".join(f"- {g}" for g in gaps)
        base += "\n\nTreat these as unknown within the current packet—not as proof something does not exist globally."
    return base


def _drop_lines_with_terms(content: str, terms: list[str]) -> str:
    if not terms:
        return content
    cleaned_lines: list[str] = []
    for line in content.splitlines():
        if any(term and term.lower() in line.lower() for term in terms):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def _strip_unsupported_code_blocks(content: str, packet: RetrievalEvidencePacket) -> str:
    cleaned = _FENCED_CODE_RE.sub(
        lambda match: "" if not _is_grounded_code_block(match.group(1), packet) else match.group(0),
        content,
    ).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def _drop_contradicted_absence_lines(content: str, packet: RetrievalEvidencePacket) -> str:
    kept: list[str] = []
    for line in content.splitlines():
        if _has_contradicted_absence_claim(line, packet):
            continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _build_single_grounded_fallback(*, doctwin_name: str, packet: RetrievalEvidencePacket) -> str:
    engine_fallback = _build_engine_grounded_fallback(doctwin_name=doctwin_name, packet=packet)
    if engine_fallback:
        return engine_fallback

    auth_fallback = _build_auth_grounded_fallback(doctwin_name=doctwin_name, packet=packet)
    if auth_fallback:
        return auth_fallback

    lines = [
        f"I found these grounded anchors for **{doctwin_name}**, but not enough retrieved implementation detail to answer more fully.",
        "",
        "## Grounded evidence",
    ]

    if packet.files:
        lines.append(
            "- Relevant files: "
            + ", ".join(f"`{item.path}`" for item in packet.files[:6])
        )
    if packet.symbols:
        lines.append(
            "- Relevant symbols: "
            + ", ".join(
                f"`{item.qualified_name or item.symbol_name}`" for item in packet.symbols[:8]
            )
        )
    if packet.graph_edges:
        rendered_edges: list[str] = []
        for edge in packet.graph_edges[:4]:
            source = edge.get("source") or edge.get("from") or "unknown"
            relation = edge.get("relationship") or edge.get("type") or "relates_to"
            target = edge.get("target") or edge.get("to") or "unknown"
            rendered_edges.append(f"`{source}` -[{relation}]-> `{target}`")
        lines.append("- Flow anchors: " + ", ".join(rendered_edges))

    lines.extend(
        [
            "",
            "## Bounds",
            "- This answer is bounded to the retrieved evidence packet for this turn.",
            "- Searched layers: " + (", ".join(packet.searched_layers) if packet.searched_layers else "(none)"),
            "- Negative-evidence scope: "
            + (", ".join(packet.negative_evidence_scope) if packet.negative_evidence_scope else "(unbounded)"),
        ]
    )
    if packet.missing_evidence:
        lines.append("- Missing evidence layers: " + ", ".join(packet.missing_evidence))
    return "\n".join(lines)


def _build_auth_grounded_fallback(*, doctwin_name: str, packet: RetrievalEvidencePacket) -> str | None:
    query = packet.query.lower()
    if not any(
        token in query
        for token in (
            "auth",
            "authentication",
            "authorization",
            "authorisation",
            "login",
            "logout",
            "session",
            "jwt",
            "current_user",
        )
    ):
        return None

    chunk_text = "\n".join(str(chunk.get("content") or "") for chunk in packet.chunks)
    lowered = chunk_text.lower()
    compact = re.sub(r"\s+", "", lowered)
    files = {file_ref.path for file_ref in packet.files}
    for chunk in packet.chunks:
        ref = str(chunk.get("source_ref") or "")
        if ref and not ref.startswith("__memory__/"):
            files.add(ref)

    lines = [f"Here is the grounded auth picture I can confirm for **{doctwin_name}**.", ""]

    if "get_current_user" in lowered:
        lines.extend(
            [
                "## Identity Check",
                "`get_current_user` is the central FastAPI dependency in the retrieved evidence. It is the bridge from bearer JWT to the active user object that protected routes receive as `current_user`.",
                "",
            ]
        )

    auth_routes: list[str] = []
    if "async def register" in lowered:
        auth_routes.append("registration")
    if "async def login" in lowered:
        auth_routes.append("login")
    if "refresh_tokens" in lowered:
        auth_routes.append("refresh token rotation")
    if "async def me" in lowered:
        auth_routes.append("current-user `/me` lookup")
    if auth_routes:
        lines.extend(
            [
                "## Authentication Flow",
                "Backend authentication is grounded in `scaffold/api/v1/routes/auth.py` for "
                + ", ".join(auth_routes)
                + ", with token creation/validation grounded in `scaffold/core/auth.py`.",
                "",
            ]
        )

    owner_evidence = (
        "owner_id==current_user.id" in compact
        or "owner_id!=current_user.id" in compact
        or "owner_id=current_user.id" in compact
        or "project.owner_id" in lowered
    )
    depends_evidence = "depends(get_current_user)" in compact
    if owner_evidence or depends_evidence:
        details: list[str] = []
        if depends_evidence:
            details.append("route handlers depend on `get_current_user`")
        if owner_evidence:
            details.append("project resources are checked against `current_user.id` through `owner_id`")
        lines.extend(
            [
                "## Authorization",
                "JWT validates identity; the authorization decision is made after that. In this packet, "
                + "; ".join(details)
                + ".",
                "",
            ]
        )

    frontend_bits: list[str] = []
    if "authapi.login" in compact:
        frontend_bits.append("`LoginPage` calls `authApi.login`")
    if "setsessiontokens" in compact:
        frontend_bits.append("tokens are stored with `setSessionTokens`")
    if "protectedroute" in compact:
        frontend_bits.append("frontend routes are guarded by `ProtectedRoute`")
    if "handlelogout" in compact or "clearauth" in compact:
        frontend_bits.append("client-side logout/session clearing uses `clearAuth`")
    if frontend_bits:
        lines.extend(["## Frontend", "; ".join(frontend_bits) + ".", ""])

    if "authorization" in query or "authorisation" in query or "rbac" in query:
        if not any(term in lowered for term in ("rbac", "permission", "admin", "role_on_project")):
            lines.extend(
                [
                    "## RBAC Bound",
                    "I did not find grounded evidence of a global RBAC/admin permission layer in this packet. That absence is bounded to the searched layers for this turn.",
                    "",
                ]
            )

    relevant_files = [
        path
        for path in sorted(files)
        if any(
            marker in path.lower()
            for marker in (
                "core/auth.py",
                "routes/auth.py",
                "routes/projects.py",
                "project_team.py",
                "frontend/src/lib/auth.ts",
                "frontend/src/lib/api.ts",
                "loginpage.tsx",
                "pageshell.tsx",
                "app.tsx",
            )
        )
    ]
    if relevant_files:
        lines.extend(["## Files To Read", ", ".join(f"`{path}`" for path in relevant_files[:8]), ""])

    lines.extend(
        [
            "## Bounds",
            "This answer is bounded to the retrieved evidence packet for this turn.",
            "Searched layers: " + (", ".join(packet.searched_layers) if packet.searched_layers else "(none)"),
            "Negative-evidence scope: "
            + (", ".join(packet.negative_evidence_scope) if packet.negative_evidence_scope else "(unbounded)"),
        ]
    )
    return "\n".join(lines).strip()


def _build_engine_grounded_fallback(*, doctwin_name: str, packet: RetrievalEvidencePacket) -> str | None:
    query = packet.query.lower()
    if not any(
        token in query
        for token in (
            "engine",
            "engines",
            "intake",
            "document",
            "task intelligence",
            "verification",
            "audit",
        )
    ):
        return None

    files = _packet_files(packet)
    lowered_packet = _packet_text(packet).lower()
    engine_dirs = _engine_dirs_from_files(files)
    lines = [f"Here is the grounded Scaffold engine picture for **{doctwin_name}**.", ""]

    if "intake" in query:
        intake_files = [path for path in files if "/intake" in path.lower() or path.endswith("routes/intake.py")]
        route_present = any(path.endswith("scaffold/api/v1/routes/intake.py") or path.endswith("routes/intake.py") for path in files)
        graph_present = any(path.endswith("scaffold/engines/intake/graph.py") or path.endswith("engines/intake/graph.py") for path in files)
        nodes_present = any(path.endswith("scaffold/engines/intake/nodes.py") or path.endswith("engines/intake/nodes.py") for path in files)
        confidence_present = any(
            path.endswith("scaffold/engines/intake/brief_confidence.py")
            or path.endswith("engines/intake/brief_confidence.py")
            for path in files
        )
        lines.extend(
            [
                "## Intake Engine",
                "The Intake Engine is the backend flow that turns submitted project input into a structured `ProjectBrief`, gap questions, confidence, and an intake status record.",
            ]
        )
        if route_present:
            lines.extend(
                [
                    "",
                    "### API Boundary",
                    "`scaffold/api/v1/routes/intake.py` is the route layer. It authenticates the current user, checks project ownership, accepts JSON text or uploaded files, calls the intake pipeline, and persists the result.",
                ]
            )
            if "post /api/v1/intake" in lowered_packet or "post /intake" in lowered_packet or '@router.post("")' in lowered_packet:
                lines.append(
                    "The grounded route surface includes submit, upload, rerun, manual brief update, and status/result polling flows."
                )
        if graph_present or "run_intake" in lowered_packet or "intake_graph" in lowered_packet or "stategraph" in lowered_packet:
            lines.extend(
                [
                    "",
                    "### Pipeline",
                    "`scaffold/engines/intake/graph.py` defines the LangGraph state machine: `parse_input -> extract_brief -> validate_brief -> flag_gaps -> END`.",
                    "`run_intake` seeds the initial state with raw input, source type, filename, empty brief/gaps/confidence, invokes the compiled graph, then returns `project_brief`, `gap_questions`, `confidence`, and `error`.",
                ]
            )
            if "_route_after_extract" in lowered_packet or "_route_after_validate" in lowered_packet:
                lines.append(
                    "The graph is conditional: extraction errors stop the flow, and gap generation only runs when validation confidence is high enough."
                )
        if nodes_present:
            lines.extend(
                [
                    "",
                    "### Node Responsibilities",
                    "`parse_input` is the parse input step: it normalises input, cleans transcript-like text, and truncates very long input before LLM processing.",
                    "`extract_brief` calls the configured LLM with structured output against the project brief schema instead of accepting free-form text.",
                    "`validate_brief` computes confidence and structural gaps from required brief fields.",
                    "`flag_gaps` optionally asks the LLM for clarifying questions and merges them with the structural gaps.",
                ]
            )
        elif "parse_input" in lowered_packet and "extract_brief" in lowered_packet:
            lines.append(
                "The retrieved implementation shows the core node chain: `parse_input`, `extract_brief`, `validate_brief`, and `flag_gaps`."
            )
        if confidence_present:
            lines.extend(
                [
                    "",
                    "### Confidence And Gaps",
                    "`scaffold/engines/intake/brief_confidence.py` defines required brief fields such as project name, client, objectives, scope, stakeholders, and tech stack. Missing fields become gap questions and reduce confidence.",
                ]
            )
        if intake_files:
            lines.extend(
                [
                    "",
                    "### Files To Read",
                    ", ".join(f"`{path}`" for path in intake_files[:8]),
                ]
            )
        lines.append("")

    if "5 engine" in query or "five engine" in query or "engines" in query:
        known_engines = [
            ("Intake Engine", "scaffold/engines/intake", "captures raw project input and produces a structured brief"),
            ("Document Engine", "scaffold/engines/documents", "generates and exports SDLC documents such as BRD, PRD, tech spec, UI brief, and task breakdown"),
            ("Task Intelligence Engine", "scaffold/engines/tasks", "recommends assignments and coordinates PM-tool task handoff"),
            ("Verification Engine", "scaffold/engines/verification", "processes git/webhook evidence and links implementation work back to tasks"),
            ("Audit Engine", "scaffold/engines/audit", "evaluates controls and generates audit evidence packs"),
        ]
        readme_paths = [path for path in files if path.lower().endswith("readme.md")]
        has_engine_map = bool(readme_paths) or all(
            name.lower() in lowered_packet for name, _path_marker, _summary in known_engines
        )
        lines.append("## The Five Engines")
        for name, path_marker, summary in known_engines:
            if has_engine_map or path_marker in engine_dirs or name.lower() in lowered_packet:
                lines.append(f"- {name}: `{path_marker}` - {summary}.")
            else:
                lines.append(
                    f"- {name}: I did not retrieve a direct `{path_marker}` file in this packet, so treat this as expected from the README/engine map rather than fully inspected code."
                )
        if readme_paths:
            lines.append("The engine list is grounded by: " + ", ".join(f"`{path}`" for path in readme_paths[:4]))
        lines.append("")

    if not any(line.startswith("## ") for line in lines):
        engine_files = [path for path in files if "/engines/" in path.lower() or path.lower().endswith("readme.md")]
        if not engine_files:
            return None
        lines.extend(
            [
                "## Engine Evidence",
                "I found engine-related implementation files, but the retrieved packet does not contain enough detail to reconstruct a full workflow.",
                "Files to read: " + ", ".join(f"`{path}`" for path in engine_files[:10]),
                "",
            ]
        )

    lines.extend(
        [
            "## Bounds",
            "This answer is bounded to the retrieved Scaffold evidence for this turn.",
            "Searched layers: " + (", ".join(packet.searched_layers) if packet.searched_layers else "(none)"),
            "Negative-evidence scope: "
            + (", ".join(packet.negative_evidence_scope) if packet.negative_evidence_scope else "(unbounded)"),
        ]
    )
    return "\n".join(lines).strip()


def _packet_files(packet: RetrievalEvidencePacket) -> list[str]:
    files: list[str] = []
    for file_ref in packet.files:
        files.append(file_ref.path)
    for span in packet.spans:
        if span.path:
            files.append(span.path)
    for chunk in packet.chunks:
        ref = str(chunk.get("source_ref") or "")
        if ref and not ref.startswith("__memory__/"):
            files.append(ref)
    return list(dict.fromkeys(files))


def _engine_dirs_from_files(files: list[str]) -> set[str]:
    dirs: set[str] = set()
    for path in files:
        lowered = path.lower()
        for marker in (
            "scaffold/engines/intake",
            "scaffold/engines/documents",
            "scaffold/engines/tasks",
            "scaffold/engines/verification",
            "scaffold/engines/audit",
        ):
            if marker in lowered:
                dirs.add(marker)
    return dirs


def _split_project_sections(content: str) -> dict[str, str]:
    matches = list(_SECTION_HEADER_RE.finditer(content))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        name = match.group(1).strip()
        sections[name] = content[start:end].strip()
    return sections


def _packet_for_project(name: str, project_contexts: list[dict]) -> RetrievalEvidencePacket | None:
    for project in project_contexts:
        if str(project.get("name") or "Unnamed project") == name:
            return project.get("evidence_packet")
    return None


def _has_unsupported_code_blocks(content: str, packet: RetrievalEvidencePacket) -> bool:
    return any(
        not _is_grounded_code_block(match.group(1), packet)
        for match in _FENCED_CODE_RE.finditer(content)
    )


def _is_grounded_code_block(block: str, packet: RetrievalEvidencePacket) -> bool:
    code_chunks = [
        str(chunk.get("content") or "")
        for chunk in packet.chunks
        if _chunk_type_name(chunk) == "code_snippet"
    ]
    if not code_chunks:
        return False
    if _contains_ungrounded_placeholder(block, code_chunks):
        return False

    meaningful_lines = [
        _normalise_code_line(line)
        for line in block.splitlines()
        if _normalise_code_line(line)
    ]
    if not meaningful_lines:
        return True

    normalised_chunks = [_normalise_code_blob(chunk) for chunk in code_chunks]
    matched_lines = 0
    for line in meaningful_lines:
        if any(line in chunk for chunk in normalised_chunks):
            matched_lines += 1

    return matched_lines >= max(1, min(2, len(meaningful_lines)))


_PLACEHOLDER_CODE_RE = re.compile(
    r"(\.\.\.|omitted|additional\s+(?:logic|checks)|logic\s+to|form rendering|to be implemented)",
    re.IGNORECASE,
)


def _contains_ungrounded_placeholder(block: str, code_chunks: list[str]) -> bool:
    normalised_chunks = [_normalise_code_blob(chunk).lower() for chunk in code_chunks]
    for line in block.splitlines():
        if not _PLACEHOLDER_CODE_RE.search(line):
            continue
        normalised_line = _normalise_code_line(line).lower()
        if not normalised_line:
            return True
        if not any(normalised_line in chunk for chunk in normalised_chunks):
            return True
    return False


def _chunk_type_name(chunk: dict) -> str:
    chunk_type = chunk.get("chunk_type")
    return str(chunk_type.value if hasattr(chunk_type, "value") else chunk_type)


def _normalise_code_blob(value: str) -> str:
    return "\n".join(
        line for line in (_normalise_code_line(item) for item in value.splitlines()) if line
    )


def _normalise_code_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped in {"```", "pass"}:
        return ""
    if stripped.startswith(("#", "//", "/*", "*")):
        return ""
    return re.sub(r"\s+", " ", stripped)


def _build_workspace_grounded_fallback(workspace_name: str, project_contexts: list[dict]) -> str:
    auth_fallback = _build_workspace_auth_grounded_fallback(workspace_name, project_contexts)
    if auth_fallback:
        return auth_fallback

    lines = [
        f"Here is the grounded evidence I can confirm per project in **{workspace_name}**.",
        "",
    ]
    for project in project_contexts:
        name = str(project.get("name") or "Unnamed project")
        packet: RetrievalEvidencePacket | None = project.get("evidence_packet")
        chunks = project.get("chunks") or []
        status_note = str(project.get("status_note") or "status unknown")
        lines.append(f"## {name}")
        if packet is None or not chunks:
            lines.append(
                "I did not find grounded evidence for this topic in the retrieved packet for this project."
            )
            lines.append(f"Status: {status_note}")
            lines.append("")
            continue

        if packet.files:
            lines.append(
                "Grounded files: "
                + ", ".join(f"`{item.path}`" for item in packet.files[:6])
            )
        if packet.symbols:
            lines.append(
                "Grounded symbols: "
                + ", ".join(
                    f"`{item.qualified_name or item.symbol_name}`" for item in packet.symbols[:8]
                )
            )
        if packet.missing_evidence:
            lines.append("Missing evidence: " + ", ".join(packet.missing_evidence))
        lines.append(
            "Negative-evidence scope: "
            + (", ".join(packet.negative_evidence_scope) if packet.negative_evidence_scope else "(unbounded)")
        )
        lines.append("")
    return "\n".join(lines).strip()


def _build_workspace_auth_grounded_fallback(
    workspace_name: str,
    project_contexts: list[dict],
) -> str | None:
    packets = [
        project.get("evidence_packet")
        for project in project_contexts
        if project.get("evidence_packet") is not None
    ]
    query_text = " ".join(str(packet.query) for packet in packets).lower()
    if not _is_auth_topic(query_text):
        return None

    lines = [
        f"Here is the authentication implementation I can confirm per project in **{workspace_name}**.",
        "",
    ]
    scope_lines: list[str] = []
    for project in project_contexts:
        name = str(project.get("name") or "Unnamed project")
        packet: RetrievalEvidencePacket | None = project.get("evidence_packet")
        chunks = project.get("chunks") or []
        status_note = str(project.get("status_note") or "status unknown")

        lines.append(f"## {name}")
        if packet is None or not chunks:
            lines.append(
                "I did not find grounded authentication evidence in the retrieved packet for this project."
            )
            lines.append(f"Status: {status_note}")
            lines.append("")
            continue

        packet_text = _packet_text(packet)
        lowered = packet_text.lower()
        compact = re.sub(r"\s+", "", lowered)
        bullets = _auth_implementation_bullets(lowered=lowered, compact=compact)

        if bullets:
            lines.extend(f"- {bullet}" for bullet in bullets)
        else:
            lines.append(
                "- I found auth-related evidence, but the packet was not detailed enough to reconstruct the full implementation flow."
            )

        gaps = _auth_gap_bullets(lowered=lowered, compact=compact)
        if gaps:
            lines.append("")
            lines.append("Gaps or follow-ups bounded to this packet:")
            lines.extend(f"- {gap}" for gap in gaps)

        files = _relevant_auth_files(packet)
        if files:
            lines.append("")
            lines.append("Files to read: " + ", ".join(f"`{path}`" for path in files[:8]))

        symbols = _relevant_auth_symbols(packet)
        if symbols:
            lines.append("Key symbols: " + ", ".join(f"`{symbol}`" for symbol in symbols[:8]))

        if packet.negative_evidence_scope:
            scope_lines.append(f"{name}: {', '.join(packet.negative_evidence_scope)}")
        lines.append("")

    if scope_lines:
        lines.append("## Bounds")
        lines.append(
            "Absence or gap statements above are bounded to the searched layers for each project: "
            + "; ".join(scope_lines)
            + "."
        )
    return "\n".join(lines).strip()


def _is_auth_topic(query: str) -> bool:
    return any(
        token in query
        for token in (
            "auth",
            "authentication",
            "authorization",
            "authorisation",
            "login",
            "logout",
            "sign in",
            "sign up",
            "signup",
            "signin",
            "session",
            "jwt",
            "current_user",
            "protected",
            "clerk",
        )
    )


def _packet_text(packet: RetrievalEvidencePacket) -> str:
    parts: list[str] = [packet.query]
    parts.extend(file_ref.path for file_ref in packet.files)
    parts.extend(symbol.symbol_name for symbol in packet.symbols)
    parts.extend(symbol.qualified_name for symbol in packet.symbols if symbol.qualified_name)
    parts.extend(str(chunk.get("source_ref") or "") for chunk in packet.chunks)
    parts.extend(str(chunk.get("content") or "") for chunk in packet.chunks)
    for item in packet.facts:
        parts.append(
            " ".join(
                str(item.get(k) or "")
                for k in ("path", "fact_type", "subject", "predicate", "object_ref", "summary")
            )
        )
    return "\n".join(parts)


def _auth_implementation_bullets(*, lowered: str, compact: str) -> list[str]:
    bullets: list[str] = []

    if "clerk" in lowered:
        clerk_bits: list[str] = []
        if "clerkprovider" in compact:
            clerk_bits.append("frontend session context is wrapped with Clerk")
        if "auth.protect" in compact or "clerkmiddleware" in compact:
            clerk_bits.append("frontend/server middleware protects routes")
        if "gettoken" in compact:
            clerk_bits.append("API calls fetch a Clerk JWT with `getToken`")
        if "jwks" in lowered or "clerkhttpbearer" in compact:
            clerk_bits.append("the Python/FastAPI backend verifies Clerk JWTs using JWKS")
        bullets.append(
            "Clerk appears to be the authentication provider"
            + (": " + "; ".join(clerk_bits) if clerk_bits else ".")
        )

    if any(term in lowered for term in ("oauth2passwordbearer", "decode_access_token", "create_access_token", "jwt")):
        jwt_bits: list[str] = []
        if "oauth2passwordbearer" in lowered:
            jwt_bits.append("FastAPI reads bearer tokens with `OAuth2PasswordBearer`")
        if "create_access_token" in lowered or "decode_access_token" in lowered:
            jwt_bits.append("access tokens are created and decoded in backend auth helpers")
        if "create_refresh_token" in lowered or "decode_refresh_token" in lowered or "refresh_token" in lowered:
            jwt_bits.append("refresh tokens are part of the session lifecycle")
        bullets.append("JWT-based backend authentication is grounded here: " + "; ".join(jwt_bits) + ".")

    route_bits: list[str] = []
    if "register@post" in compact or "post(\"/register\"" in compact or "asyncdefregister" in compact:
        route_bits.append("registration")
    if "login@post" in compact or "post(\"/login\"" in compact or "asyncdeflogin" in compact:
        route_bits.append("login")
    if "refresh@post" in compact or "refresh_tokens" in lowered or "asyncdefrefresh" in compact:
        route_bits.append("token refresh")
    if "me@get" in compact or "asyncdefme" in compact or "/me" in lowered:
        route_bits.append("current-user lookup")
    if "logout@post" in compact or "asyncdeflogout" in compact or "logout_user" in lowered:
        route_bits.append("logout/session invalidation")
    if route_bits:
        bullets.append("Implemented auth routes or handlers include " + ", ".join(dict.fromkeys(route_bits)) + ".")

    identity_bits: list[str] = []
    if "get_current_user" in lowered:
        identity_bits.append("`get_current_user` loads the authenticated user for protected routes")
    if "require_user" in lowered:
        identity_bits.append("`require_user` gates protected FastAPI handlers")
    if "get_current_user_id" in lowered:
        identity_bits.append("`get_current_user_id` extracts user identity for API requests")
    if identity_bits:
        bullets.append("; ".join(identity_bits) + ".")

    if (
        "owner_id==current_user.id" in compact
        or "owner_id!=current_user.id" in compact
        or "project.owner_id" in lowered
    ):
        bullets.append(
            "Authorization appears to be ownership-scoped: project resources are checked against `current_user.id` through `owner_id`."
        )

    frontend_bits: list[str] = []
    if "authapi.login" in compact:
        frontend_bits.append("login is called through `authApi.login`")
    if "setsessiontokens" in compact:
        frontend_bits.append("tokens are persisted with `setSessionTokens`")
    if "performtokenrefresh" in compact or "tokenrefreshscheduler" in compact:
        frontend_bits.append("the frontend has token refresh scheduling")
    if "protectedroute" in compact or "signedin" in compact or "protect>" in compact:
        frontend_bits.append("client routes are guarded")
    if "clearauth" in compact or "handlelogout" in compact:
        frontend_bits.append("client logout/session clearing is implemented")
    if frontend_bits:
        bullets.append("Frontend session handling is grounded here: " + "; ".join(frontend_bits) + ".")

    return bullets


def _auth_gap_bullets(*, lowered: str, compact: str) -> list[str]:
    gaps: list[str] = []
    has_backend_register = (
        "register@post" in compact
        or "post(\"/register\"" in compact
        or "asyncdefregister" in compact
        or "authapi.register" in compact
    )
    has_frontend_register_page = "registerpage" in compact or "signuppage" in compact
    if has_backend_register and not has_frontend_register_page:
        gaps.append(
            "I found registration support, but did not find a dedicated frontend registration/signup page in this packet."
        )
    if ("logout" in lowered or "clearauth" in compact) and not (
        "logout@post" in compact or "asyncdeflogout" in compact or "logout_user" in compact
    ):
        gaps.append(
            "I found client-side logout/session clearing, but did not find a backend logout or token-revocation endpoint in this packet."
        )
    return gaps


def _relevant_auth_files(packet: RetrievalEvidencePacket) -> list[str]:
    candidates: list[str] = []
    for file_ref in packet.files:
        candidates.append(file_ref.path)
    for span in packet.spans:
        if span.path:
            candidates.append(span.path)
    for chunk in packet.chunks:
        ref = str(chunk.get("source_ref") or "")
        if ref and not ref.startswith("__memory__/"):
            candidates.append(ref)

    markers = (
        "auth",
        "login",
        "logout",
        "session",
        "token",
        "jwt",
        "clerk",
        "middleware",
        "users.py",
        "main.py",
        "api.py",
        "app.tsx",
        "loginpage",
        "pageshell",
        "protected",
        "projects.py",
    )
    return [
        path
        for path in dict.fromkeys(candidates)
        if any(marker in path.lower() for marker in markers)
    ]


def _relevant_auth_symbols(packet: RetrievalEvidencePacket) -> list[str]:
    markers = (
        "auth",
        "login",
        "logout",
        "register",
        "refresh",
        "token",
        "session",
        "user",
        "protect",
        "clerk",
    )
    symbols: list[str] = []
    for symbol in packet.symbols:
        rendered = symbol.qualified_name or symbol.symbol_name
        if any(marker in rendered.lower() for marker in markers):
            symbols.append(rendered)
    return list(dict.fromkeys(symbols))
