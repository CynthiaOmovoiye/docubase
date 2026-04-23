from app.domains.evaluation.evaluator import _parse_scores


def test_parse_scores_includes_usefulness_dimension():
    scores = _parse_scores(
        """
        {
          "completeness": 4,
          "groundedness": 5,
          "technical_depth": 4,
          "format_quality": 4,
          "context_precision": 5,
          "faithfulness": 5,
          "usefulness": 4,
          "reasoning": "Grounded and useful."
        }
        """
    )

    assert scores["usefulness"] == 4
    assert scores["reasoning"] == "Grounded and useful."
