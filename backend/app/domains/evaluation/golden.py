"""Load and evaluate golden chat cases for regression-style checks."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domains.evaluation.metrics import AnswerQualityMetrics


@dataclass(frozen=True, slots=True)
class GoldenCase:
    id: str
    persona: str
    mode: str
    query: str = ""


@dataclass(frozen=True, slots=True)
class GoldenEvalResult:
    passed: bool
    failures: list[str]


def load_golden_suite(path: Path) -> list[GoldenCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        msg = "golden suite root must be a JSON array"
        raise ValueError(msg)
    cases: list[GoldenCase] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cases.append(
            GoldenCase(
                id=str(item["id"]),
                persona=str(item["persona"]),
                mode=str(item["mode"]),
                query=str(item.get("query", "")),
            )
        )
    return cases


def summarise_suite(cases: list[GoldenCase]) -> dict[str, Any]:
    persona_counts = Counter(c.persona for c in cases)
    mode_counts = Counter(c.mode for c in cases)
    return {
        "total_cases": len(cases),
        "persona_counts": dict(persona_counts),
        "mode_counts": dict(mode_counts),
    }


def evaluate_golden_case(
    *,
    case: GoldenCase,
    answer: str,
    metrics: AnswerQualityMetrics,
) -> GoldenEvalResult:
    _ = (case, answer)
    failures: list[str] = []
    if metrics.false_not_present_risk and not metrics.negative_claims_bounded:
        failures.append("unbounded_negative")
    return GoldenEvalResult(passed=len(failures) == 0, failures=failures)
