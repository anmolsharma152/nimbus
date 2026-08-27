import pytest
from evals.eval_runner import NimbusEvalRunner


def test_eval_runner_synthetic_execution():
    runner = NimbusEvalRunner()
    scorecard = runner.run_synthetic_benchmark()

    assert scorecard["total_cases"] == 3
    assert scorecard["passed_cases"] == 3
    assert scorecard["pass_rate_percentage"] == 100.0
    assert scorecard["average_turns"] <= 5.0
    assert len(scorecard["results"]) == 3


def test_eval_runner_live_workspace_benchmark():
    runner = NimbusEvalRunner()
    scorecard = runner.run_live_workspace_eval()

    assert scorecard["total_cases"] == 1
    assert scorecard["passed_cases"] == 1
    assert scorecard["pass_rate_percentage"] == 100.0
    assert scorecard["results"][0]["patch_generated"] is True
    assert scorecard["results"][0]["test_exit_code"] == 0
