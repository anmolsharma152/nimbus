import json
import os
from collections import Counter

import pytest

from app.agent import run_agent_commands
from app.models import EventType
from app.workspace import SubprocessWorkspace, UnifiedWorkspace
from evals.eval_runner import CASES, format_scorecard, run_case, run_suite, write_file_command


class ScriptedLLM:
    """Stands in for LLMChatSession: replays canned replies and records the prompts it received."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []
        self.tier_calls = Counter()

    async def send_message(self, prompt, on_fallback=None):
        self.prompts.append(prompt)
        self.tier_calls["scripted"] += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def cmd(command):
    return "```json\n" + json.dumps({"command": command}) + "\n```"


def subprocess_workspace(task_id):
    return UnifiedWorkspace(task_id, impl=SubprocessWorkspace(task_id))


FIXES = {
    "factorial": "def factorial(n):\n    if n < 0:\n        raise ValueError('negative')\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n",
    "slugify": "import re\n\ndef slugify(text):\n    return re.sub(r'[^a-z0-9]+', '-', text.strip().lower()).strip('-')\n",
    "calculator": "def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n",
}
FIX_FILES = {"factorial": "math_lib.py", "slugify": "string_utils.py", "calculator": "calculator.py"}


def solving_llm(case_name):
    return ScriptedLLM([
        cmd("ls"),
        cmd(write_file_command(FIX_FILES[case_name], FIXES[case_name])),
        cmd("git diff"),
        "Fixed it.",
    ])


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_each_case_is_solvable_and_scored_by_hidden_tests(case):
    result = await run_case(case, lambda: solving_llm(case.name), subprocess_workspace)

    assert result.passed, result.details
    assert result.outcome == "completed"
    assert result.iterations_used == 4 and result.commands_run == 3
    assert result.patch_generated and result.test_exit_code == 0
    assert result.llm_calls == {"scripted": 4}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_unfixed_fixture_fails(case):
    result = await run_case(case, lambda: ScriptedLLM(["Nothing to do."]), subprocess_workspace)
    assert not result.passed
    assert result.outcome == "completed"
    assert result.test_exit_code != 0


@pytest.mark.asyncio
async def test_agent_cannot_pass_by_writing_the_hidden_test():
    case = next(c for c in CASES if c.name == "calculator")
    (hidden_name,) = case.hidden_files
    fake_test = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
    llm = ScriptedLLM([cmd(write_file_command(hidden_name, fake_test)), "Done."])

    result = await run_case(case, lambda: llm, subprocess_workspace)
    assert result.patch_generated  # the agent did change the tree...
    assert not result.passed       # ...but the real hidden test still runs against the buggy code


@pytest.mark.asyncio
async def test_llm_failure_is_reported_and_workspace_cleaned_up():
    workspaces = []

    def tracking_factory(task_id):
        ws = subprocess_workspace(task_id)
        workspaces.append(ws)
        return ws

    result = await run_case(CASES[0], lambda: ScriptedLLM([RuntimeError("all tiers down")]), tracking_factory)
    assert result.outcome == "error" and not result.passed
    assert "all tiers down" in result.details
    assert workspaces[0].impl.base_dir is None or not os.path.exists(workspaces[0].impl.base_dir)


@pytest.mark.asyncio
async def test_iteration_limit_is_reported():
    result = await run_case(
        CASES[0], lambda: ScriptedLLM([cmd("true")] * 3), subprocess_workspace, max_iterations=3
    )
    assert result.outcome == "max_iterations"
    assert result.iterations_used == 3 and not result.passed


@pytest.mark.asyncio
async def test_suite_scorecard_aggregates_results():
    card = await run_suite(CASES[:2], lambda: ScriptedLLM(["Nothing to do."]), subprocess_workspace)
    assert card["total_cases"] == 2 and card["passed_cases"] == 0
    assert card["llm_calls"] == {"scripted": 2}
    assert "Pass rate: 0.0% (0/2)" in format_scorecard(card)


# --- The shared agent loop itself ---

class FakeWorkspace:
    def __init__(self):
        self.commands = []

    async def aexecute_command(self, command, workdir=None, timeout=300):
        self.commands.append(command)
        return 0, "x" * 20000

    async def aget_file_base64(self, path):
        return None


@pytest.mark.asyncio
async def test_agent_loop_recovers_from_malformed_json_and_truncates_output():
    llm = ScriptedLLM(["```json\n{\"command\": broken}\n```", cmd("cat big"), "All done."])
    ws, events, stats = FakeWorkspace(), [], {}

    async def emit(event_type, payload):
        events.append((event_type, payload))

    outcome = await run_agent_commands(llm, ws, "goal", emit, max_iterations=5, stats=stats)

    assert outcome == "completed"
    assert ws.commands == ["cat big"]
    assert llm.prompts[1].startswith("Error: Failed to parse or execute command")
    assert "[output truncated for length]" in llm.prompts[2] and len(llm.prompts[2]) < 10200
    assert stats == {"iterations": 3, "commands": 1}
    assert events[-1] == (EventType.LOG, {"message": "Agent completed: All done."})


@pytest.mark.asyncio
async def test_agent_loop_stops_when_cancelled():
    llm = ScriptedLLM([cmd("true")] * 5)
    checks = iter([False, True])

    async def should_stop():
        return next(checks)

    async def emit(event_type, payload):
        pass

    outcome = await run_agent_commands(llm, FakeWorkspace(), "goal", emit, 5, {}, should_stop=should_stop)
    assert outcome == "cancelled"
    assert len(llm.prompts) == 1
