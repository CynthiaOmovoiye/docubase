"""
Policy and safety rules.

This is a first-class domain, not a utility module.
All decisions about what can be indexed, retrieved, or surfaced run through here.

Three-tier model:
  ALWAYS_BLOCKED   — enforced at ingestion, cannot be overridden by any config
  OPT_IN           — off by default, user can enable per twin (e.g., code snippets)
  ALWAYS_AVAILABLE — always eligible for indexing and retrieval

Principle: policy enforcement is explicit and auditable.
It is NOT mixed into connector logic, ingestion logic, or answer generation.

Path-traversal note: is_file_blocked receives a relative path from the
connector (e.g. "config/.env.production").  It checks every path *component*
independently so patterns like ".env.*" block the file regardless of how deep
it sits in the directory tree.
"""

import fnmatch
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ─── Patterns that are ALWAYS blocked regardless of config ────────────────────
#
# Each pattern is matched against:
#   1. The bare filename  (e.g. ".env.production" → matched as ".env.production")
#   2. Every individual path component (including the filename)
#
# All patterns are matched case-insensitively.

ALWAYS_BLOCKED_FILENAME_PATTERNS: list[str] = [
    # Environment / config files
    ".env",
    ".env.*",
    "*.env",
    "*.env.*",
    # PEM / key material
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.pkcs8",
    "*.jks",
    "*.keystore",
    # SSH private keys (with and without extension)
    "id_rsa",
    "id_rsa.*",
    "id_ecdsa",
    "id_ecdsa.*",
    "id_ed25519",
    "id_ed25519.*",
    "id_dsa",
    "id_dsa.*",
    # Common credential / secret files
    "secrets.*",
    "credentials.*",
    ".netrc",
    ".htpasswd",
    # AWS
    "credentials",          # ~/.aws/credentials bare filename
    # Package manager tokens
    ".npmrc",
    ".yarnrc",
    ".pypirc",
    ".gitconfig",           # may contain remote credentials
    # Docker
    "config.json",          # matched only when the parent dir is ".docker" — see path check below
    # Generic token / secret filenames
    "*.token",
    "*_token",
    "*_secret",
    "*_private",
    "private_key.*",
]

# Additional full-path patterns (matched against the entire lowercased path)
ALWAYS_BLOCKED_PATH_PATTERNS: list[str] = [
    ".aws/credentials",
    ".aws/config",
    ".docker/config.json",
    ".ssh/*",
]

# Directory names that are ALWAYS blocked — any file whose path contains one of
# these as a directory component will be rejected.  This prevents AI agent working
# directories, IDE state, and local tooling from being indexed as project knowledge.
#
# Checked as exact matches against each path component (case-insensitive), so
# both `.claude/CLAUDE.md` and `docs/.claude/context.json` are blocked.
ALWAYS_BLOCKED_DIR_NAMES: frozenset[str] = frozenset({
    # Claude Code
    ".claude",
    # Cursor IDE
    ".cursor",
    # Aider
    ".aider",
    # Copilot / IDE assistant workspace files
    ".copilot",
    # Continue.dev
    ".continue",
    # Codeium
    ".codeium",
    # TabNine
    ".tabnine",
    # Sourcegraph Cody
    ".sourcegraph",
    # Windsurf / Cascade
    ".windsurf",
})

# Regex patterns that indicate a line contains a secret value.
#
# Keep these intentionally value-oriented.  Earlier versions treated any
# ``password: ...`` shape as sensitive, which incorrectly dropped normal
# typed auth code such as ``password: str`` from ingestion.  That made the
# repository intelligence layer blind to the very files that explain auth.
SECRET_LINE_PATTERNS: list[re.Pattern] = [
    re.compile(r'(?i)\b(api_key|api-key|apikey)\b\s*[=:]\s*["\']?[\w\-]{20,}'),
    re.compile(r'(?i)\b(secret|password|passwd|pwd)\b\s*=\s*["\']?.{8,}'),
    re.compile(r'(?i)\b(token|auth_token|access_token)\b\s*=\s*["\']?[\w\-]{20,}'),
    re.compile(r'(?i)\b(secret|password|passwd|pwd)\b\s*:\s*["\'][^"\']{8,}["\']'),
    re.compile(r'(?i)\b(token|auth_token|access_token)\b\s*:\s*["\'][\w\-]{20,}["\']'),
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),           # OpenAI-style key pattern
    re.compile(r'sk-or-v1-[a-zA-Z0-9_-]{20,}'),  # OpenRouter API key
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),            # classic ghp_ PAT shape
    re.compile(r'glpat-[a-zA-Z0-9\-]{20,}'),       # classic glpat- PAT shape
    re.compile(r'-----BEGIN (RSA |EC )?PRIVATE KEY-----'),
    re.compile(r'AKIA[0-9A-Z]{16}'),               # AWS Access Key ID
]


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    tier: str  # "always_blocked" | "opt_in_blocked" | "allowed"


def is_file_blocked(filepath: str) -> PolicyDecision:
    """
    Check whether a file path is always blocked from ingestion.

    Always-blocked files are never read, never indexed, never referenced.
    This check runs before any connector fetches content.

    Strategy:
    - Normalise the path to forward-slash POSIX form and lowercase it.
    - Check the full lowercased path against ALWAYS_BLOCKED_PATH_PATTERNS.
    - Check every individual path component (directory names AND filename)
      against ALWAYS_BLOCKED_FILENAME_PATTERNS so that
      "infra/.env.staging" is caught even though the directory is "infra".
    """
    # Normalise: use POSIX separators, strip leading ./ or /
    normalised = PurePosixPath(filepath.replace("\\", "/"))
    full_lower = str(normalised).lower().lstrip("/")

    def _blocked(pattern: str, subject: str) -> bool:
        return fnmatch.fnmatch(subject, pattern.lower())

    # 1. Check the full path against path-level patterns
    for pattern in ALWAYS_BLOCKED_PATH_PATTERNS:
        if _blocked(pattern, full_lower):
            logger.info("file_blocked_by_policy", filepath=filepath, pattern=pattern)
            return PolicyDecision(
                allowed=False,
                reason=f"File matches always-blocked path pattern: {pattern}",
                tier="always_blocked",
            )

    # 2. Check every path component (including the filename) against
    #    filename patterns.  This ensures config/.env.production is blocked
    #    because ".env.production" (a component) matches ".env.*".
    components = [p for p in normalised.parts if p not in (".", "/")]
    for component in components:
        comp_lower = component.lower()
        for pattern in ALWAYS_BLOCKED_FILENAME_PATTERNS:
            if _blocked(pattern, comp_lower):
                logger.info(
                    "file_blocked_by_policy",
                    filepath=filepath,
                    component=component,
                    pattern=pattern,
                )
                return PolicyDecision(
                    allowed=False,
                    reason=f"File component {component!r} matches always-blocked pattern: {pattern}",
                    tier="always_blocked",
                )

    # 3. Check directory components against the AI-agent / tooling blocklist.
    #    Applies to all components except the final filename so that a *file*
    #    named ".claude" is not inadvertently blocked (unlikely but correct).
    dir_components = components[:-1] if len(components) > 1 else []
    for dir_comp in dir_components:
        if dir_comp.lower() in ALWAYS_BLOCKED_DIR_NAMES:
            logger.info(
                "file_blocked_by_policy",
                filepath=filepath,
                blocked_dir=dir_comp,
            )
            return PolicyDecision(
                allowed=False,
                reason=f"Directory {dir_comp!r} is an always-blocked AI-agent/tooling directory",
                tier="always_blocked",
            )

    return PolicyDecision(allowed=True, reason="file allowed", tier="allowed")


def scan_content_for_secrets(content: str) -> list[str]:
    """
    Scan text content for lines that appear to contain secret values.

    Returns a list of flagged reasons. Empty list = clean.
    Called during ingestion to prevent accidental secret indexing.
    """
    flagged = []
    for line_num, line in enumerate(content.splitlines(), start=1):
        for pattern in SECRET_LINE_PATTERNS:
            if pattern.search(line):
                flagged.append(f"Possible secret on line {line_num}: matches {pattern.pattern[:40]}")
                break  # one flag per line is enough
    return flagged


def can_surface_code_snippet(allow_code_snippets: bool) -> PolicyDecision:
    """
    Determine whether a code snippet chunk can be returned in a response.

    Even when allowed, the retrieval layer must scope to relevant sections only.
    Full file dumps are never permitted.
    """
    if allow_code_snippets:
        return PolicyDecision(
            allowed=True,
            reason="Code snippets enabled for this twin",
            tier="opt_in",
        )
    return PolicyDecision(
        allowed=False,
        reason="Code snippets are disabled for this twin. Enable in twin config.",
        tier="opt_in_blocked",
    )


def redact_sensitive_content(content: str) -> str:
    """
    Redact lines that match secret patterns before any content reaches the LLM.

    This is the last line of defence — content should already be clean
    if ingestion-time scanning worked correctly.
    """
    clean_lines = []
    for line in content.splitlines():
        is_sensitive = any(p.search(line) for p in SECRET_LINE_PATTERNS)
        if is_sensitive:
            clean_lines.append("[REDACTED — possible sensitive value]")
        else:
            clean_lines.append(line)
    return "\n".join(clean_lines)
