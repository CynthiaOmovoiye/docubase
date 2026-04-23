from app.domains.evaluation.latency import build_chat_latency_report


def test_chat_latency_report_flags_over_budget_stages():
    report = build_chat_latency_report(
        retrieval_ms=4000,
        generation_ms=2000,
        verification_ms=1200,
        total_ms=13000,
        workspace_scope=False,
    )

    assert report.budget_exceeded is True
    assert set(report.exceeded_budgets) == {"retrieval", "verification", "total"}


def test_workspace_latency_uses_workspace_total_budget():
    report = build_chat_latency_report(
        retrieval_ms=2000,
        generation_ms=6000,
        verification_ms=500,
        total_ms=15000,
        workspace_scope=True,
    )

    assert report.budget_exceeded is False
    assert report.total_budget_ms > 12000
