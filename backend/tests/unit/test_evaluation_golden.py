from pathlib import Path

from app.domains.evaluation.golden import (
    evaluate_golden_case,
    load_golden_suite,
    summarise_suite,
)
from app.domains.evaluation.metrics import AnswerQualityMetrics


def _suite_path() -> Path:
    return Path(__file__).resolve().parents[1] / "golden" / "repo_intelligence_suite.json"


def test_golden_suite_covers_personas_and_modes():
    cases = load_golden_suite(_suite_path())
    summary = summarise_suite(cases)

    assert summary["total_cases"] >= 8
    assert {"engineer", "recruiter", "pm"} <= set(summary["persona_counts"])
    assert {
        "implementation",
        "onboarding",
        "workspace_comparison",
        "project_status",
        "risk_review",
        "change_review",
        "recruiter_summary",
    } <= set(summary["mode_counts"])


def test_golden_case_evaluation_enforces_expectations():
    case = load_golden_suite(_suite_path())[0]
    result = evaluate_golden_case(
        case=case,
        answer="`app/auth.py` shows the implementation, but there is no RBAC.",
        metrics=AnswerQualityMetrics(
            mode="implementation",
            search_substrate="postgres_fts",
            searched_layers=4,
            missing_evidence_count=0,
            citation_count=1,
            grounded_anchor_present=True,
            negative_claims_bounded=False,
            false_not_present_risk=True,
            verifier_issues_count=0,
            verifier_retry_requested=False,
            verifier_rewritten=False,
        ),
    )

    assert result.passed is False
    assert "unbounded_negative" in result.failures
