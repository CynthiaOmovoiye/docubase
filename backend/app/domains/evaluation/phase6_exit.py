"""Phase 6 verification exit signals (minimal stub)."""


def evaluate_phase6_verification_exit_signals(
    *,
    verified: bool,
    issues: list[str],
) -> dict:
    return {
        "phase6_exit_pass": bool(verified) and not issues,
        "issue_count": len(issues),
    }
