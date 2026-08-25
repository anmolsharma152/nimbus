import pytest
from evals.eval_runner import NimbusEvalRunner


def test_eval_runner_execution():
    runner = NimbusEvalRunner()
    scorecard = runner.run_synthetic_benchmark()

    assert scorecard["total_cases"] == 3
    assert scorecard["passed_cases"] == 3
    assert scorecard["pass_rate_percentage"] == 100.0
    assert scorecard["average_turns"] <= 5.0
    assert len(scorecard["results"]) == 3
