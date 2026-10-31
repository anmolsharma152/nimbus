"""Eval harness: runs the real agent loop (app/agent.py) on small fixture repos and scores the result.

Each case seeds a repo with a bug or missing feature, gives the agent the task prompt, then checks
the outcome with hidden tests the agent never sees. They are written only after the agent finishes,
overwriting any same-named file, so the agent cannot pass by editing them.

    uv run python evals/eval_runner.py                 # all cases, server LLM keys from .env
    uv run python evals/eval_runner.py --case factorial --json scorecard.json

This calls the configured LLM providers (GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY) and
may consume paid quota. Tests drive the harness with a scripted LLM instead (tests/test_evals.py).
"""

import argparse
import asyncio
import base64
import dataclasses
import json
import os
import shlex
import sys
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent import SYSTEM_INSTRUCTION, initial_prompt, run_agent_commands  # noqa: E402
from app.workspace import SubprocessWorkspace, UnifiedWorkspace  # noqa: E402

EVAL_TASK_ID_BASE = 900000  # keeps eval workspaces/containers apart from real task ids


@dataclasses.dataclass
class EvalCase:
    name: str
    prompt: str
    files: Dict[str, str]
    hidden_files: Dict[str, str]
    check: str  # run after the agent finishes; exit code 0 means the case passed


@dataclasses.dataclass
class EvalResult:
    case_name: str
    passed: bool
    outcome: str  # completed | max_iterations | error | timeout
    iterations_used: int
    commands_run: int
    duration_seconds: float
    patch_generated: bool
    patch_chars: int
    test_exit_code: Optional[int]
    llm_calls: Dict[str, int]
    details: str


CASES: List[EvalCase] = [
    EvalCase(
        name="factorial",
        prompt="factorial(0) raises an error in math_lib.py. Fix it so factorial(0) returns 1, keeping other results the same.",
        files={
            "math_lib.py": (
                "def factorial(n):\n"
                "    if n < 0:\n"
                "        raise ValueError('negative')\n"
                "    if n == 1:\n"
                "        return 1\n"
                "    return n * factorial(n - 1)\n"
            ),
        },
        hidden_files={
            "test_hidden_factorial.py": (
                "import unittest\n"
                "from math_lib import factorial\n\n"
                "class T(unittest.TestCase):\n"
                "    def test_values(self):\n"
                "        self.assertEqual([factorial(i) for i in range(6)], [1, 1, 2, 6, 24, 120])\n\n"
                "    def test_negative(self):\n"
                "        with self.assertRaises(ValueError):\n"
                "            factorial(-1)\n"
            ),
        },
        check="python3 -m unittest -q test_hidden_factorial",
    ),
    EvalCase(
        name="slugify",
        prompt=(
            "Implement slugify(text) in string_utils.py: lowercase, trim, replace each run of "
            "non-alphanumeric characters with a single '-', and strip leading/trailing '-'."
        ),
        files={
            "string_utils.py": "def slugify(text):\n    raise NotImplementedError\n",
        },
        hidden_files={
            "test_hidden_slugify.py": (
                "import unittest\n"
                "from string_utils import slugify\n\n"
                "class T(unittest.TestCase):\n"
                "    def test_cases(self):\n"
                "        self.assertEqual(slugify('Hello World'), 'hello-world')\n"
                "        self.assertEqual(slugify('  Nimbus -- Agent!  '), 'nimbus-agent')\n"
                "        self.assertEqual(slugify('a__b..c'), 'a-b-c')\n"
                "        self.assertEqual(slugify('---'), '')\n"
            ),
        },
        check="python3 -m unittest -q test_hidden_slugify",
    ),
    EvalCase(
        name="calculator",
        prompt="The test in test_calculator.py fails. Find and fix the bug in calculator.py.",
        files={
            "calculator.py": (
                "def add(a, b):\n    return a - b\n\n"
                "def mul(a, b):\n    return a * b\n"
            ),
            "test_calculator.py": (
                "import unittest\n"
                "from calculator import add\n\n"
                "class T(unittest.TestCase):\n"
                "    def test_add(self):\n"
                "        self.assertEqual(add(2, 3), 5)\n"
            ),
        },
        hidden_files={
            "test_hidden_calculator.py": (
                "import unittest\n"
                "from calculator import add, mul\n\n"
                "class T(unittest.TestCase):\n"
                "    def test_ops(self):\n"
                "        self.assertEqual(add(-4, 10), 6)\n"
                "        self.assertEqual(mul(3, 4), 12)\n"
            ),
        },
        check="python3 -m unittest -q test_hidden_calculator",
    ),
]


def write_file_command(path: str, content: str) -> str:
    encoded = base64.b64encode(content.encode()).decode()
    return f"mkdir -p \"$(dirname {shlex.quote(path)})\" && printf %s {encoded} | base64 -d > {shlex.quote(path)}"


async def seed_repo(workspace, files: Dict[str, str]):
    for path, content in files.items():
        code, out = await workspace.aexecute_command(write_file_command(path, content))
        if code != 0:
            raise RuntimeError(f"Could not seed {path}: {out}")
    code, out = await workspace.aexecute_command("git add -A && git commit -q -m 'Eval fixture'")
    if code != 0:
        raise RuntimeError(f"Could not commit fixture: {out}")


async def run_case(
    case: EvalCase,
    llm_factory: Callable[[], Any],
    workspace_factory: Callable[[int], Any],
    task_id: int = EVAL_TASK_ID_BASE,
    max_iterations: int = 20,
    timeout_seconds: float = 600,
    stall_timeout: float = 90,
) -> EvalResult:
    stats: Dict[str, Any] = {}
    events: List[Any] = []
    llm = llm_factory()
    workspace = workspace_factory(task_id)
    start = time.monotonic()
    outcome, details, check_code, diff = "error", "", None, ""

    async def emit(event_type, payload):
        events.append((event_type, payload))

    try:
        code, out = await workspace.asetup(repo_url=None, branch_name=f"eval/{case.name}")
        if code != 0:
            raise RuntimeError(f"Workspace setup failed: {out}")
        await seed_repo(workspace, case.files)

        try:
            outcome = await asyncio.wait_for(
                run_agent_commands(
                    llm, workspace, initial_prompt(case.prompt, None, f"eval/{case.name}"), emit,
                    max_iterations=max_iterations, stats=stats, stall_timeout=stall_timeout,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            outcome, details = "timeout", f"Case exceeded {timeout_seconds}s"

        # Score even unfinished runs: the code on disk is what would have been pushed
        diff = await workspace.aget_diff()
        for path, content in case.hidden_files.items():
            await workspace.aexecute_command(write_file_command(path, content))
        check_code, check_out = await workspace.aexecute_command(case.check, timeout=120)
        if not details:
            details = check_out[-500:]
    except Exception as e:
        outcome, details = "error", f"{type(e).__name__}: {e}"
    finally:
        await workspace.acleanup()

    return EvalResult(
        case_name=case.name,
        passed=check_code == 0 and bool(diff),
        outcome=outcome,
        iterations_used=stats.get("iterations", 0),
        commands_run=stats.get("commands", 0),
        duration_seconds=round(time.monotonic() - start, 3),
        patch_generated=bool(diff),
        patch_chars=len(diff),
        test_exit_code=check_code,
        llm_calls=dict(getattr(llm, "tier_calls", {}) or {}),
        details=details,
    )


async def run_suite(
    cases: List[EvalCase],
    llm_factory: Callable[[], Any],
    workspace_factory: Callable[[int], Any],
    **kwargs,
) -> Dict[str, Any]:
    results = []
    for i, case in enumerate(cases):
        results.append(await run_case(case, llm_factory, workspace_factory, task_id=EVAL_TASK_ID_BASE + i, **kwargs))
    return scorecard(results)


def scorecard(results: List[EvalResult]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    llm_calls: Counter = Counter()
    for r in results:
        llm_calls.update(r.llm_calls)
    return {
        "total_cases": total,
        "passed_cases": passed,
        "pass_rate_percentage": round(passed / total * 100, 2) if total else 0.0,
        "average_turns": round(sum(r.iterations_used for r in results) / total, 2) if total else 0.0,
        "average_duration_sec": round(sum(r.duration_seconds for r in results) / total, 3) if total else 0.0,
        "llm_calls": dict(llm_calls),
        "results": [dataclasses.asdict(r) for r in results],
    }


def format_scorecard(card: Dict[str, Any]) -> str:
    lines = ["Nimbus agent eval", "=" * 60]
    for r in card["results"]:
        mark = "PASS" if r["passed"] else "FAIL"
        lines.append(
            f"[{mark}] {r['case_name']}: {r['outcome']}, turns {r['iterations_used']}, "
            f"commands {r['commands_run']}, {r['duration_seconds']}s, patch {r['patch_chars']} chars"
        )
        if not r["passed"] and r["details"]:
            lines.append("       " + r["details"].strip().splitlines()[-1][:200])
    lines += [
        "=" * 60,
        f"Pass rate: {card['pass_rate_percentage']}% ({card['passed_cases']}/{card['total_cases']})",
        f"Avg turns: {card['average_turns']}   Avg duration: {card['average_duration_sec']}s",
        f"LLM calls by tier: {card['llm_calls'] or '-'}",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", help="run only this case (repeatable)")
    parser.add_argument("--max-iterations", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=600, help="per-case wall-clock limit in seconds")
    parser.add_argument("--subprocess", action="store_true", help="force SubprocessWorkspace even if Docker is available")
    parser.add_argument("--json", help="also write the scorecard to this file")
    args = parser.parse_args(argv)

    from app.llm import LLMChatSession
    from app.logging_config import configure_logging
    from app.settings import settings

    configure_logging()
    if not (settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY):
        print("No LLM API key configured (GEMINI_API_KEY / GROQ_API_KEY / OPENROUTER_API_KEY).", file=sys.stderr)
        return 2

    cases = [c for c in CASES if not args.case or c.name in args.case]
    if not cases:
        print(f"No such case. Available: {', '.join(c.name for c in CASES)}", file=sys.stderr)
        return 2

    def workspace_factory(task_id: int):
        return UnifiedWorkspace(task_id, impl=SubprocessWorkspace(task_id) if args.subprocess else None)

    card = asyncio.run(run_suite(
        cases,
        lambda: LLMChatSession(system_instruction=SYSTEM_INSTRUCTION, temperature=0.1),
        workspace_factory,
        max_iterations=args.max_iterations,
        timeout_seconds=args.timeout,
    ))
    print(format_scorecard(card))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(card, f, indent=2)
    return 0 if card["passed_cases"] == card["total_cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
