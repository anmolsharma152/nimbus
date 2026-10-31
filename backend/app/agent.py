"""The agent's command loop, shared by the worker and the eval harness.

The LLM replies with a ```json {"command": ...}``` block; the command runs in the workspace and its
output becomes the next prompt. A reply without a command block is the final summary.
"""

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional, Sequence

from .models import EventType

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are Nimbus, an autonomous cloud software engineer. You operate inside an isolated Linux workspace "
    "with git, python3, and standard tools pre-installed. The current working directory is /workspace/repo.\n\n"
    "Your objective is to inspect the codebase, make real code modifications on disk, run tests to verify your fix, "
    "and ensure the repository is left in a clean, working state with passing assertions.\n\n"
    "To execute a bash command (e.g. to inspect files, write code via `cat << 'EOF' > file.py`, run tests, or view git diff), "
    "output a JSON block strictly formatted as:\n"
    "```json\n{\n  \"command\": \"<your bash command here>\",\n  \"screenshot\": \"<optional relative path to generated .png file>\",\n  \"caption\": \"<optional screenshot caption>\"\n}\n```\n\n"
    "CRITICAL Rules:\n"
    "1. You MUST execute bash commands to write your actual code and test files to disk (e.g. using `cat << 'EOF' > ...` or python). Do NOT just describe code in text.\n"
    "2. Directly inspect relevant source files with `find`, `grep`, or `cat`.\n"
    "3. Do NOT run heavy full-stack package installations (`pip install -r requirements.txt`). Instead, write focused tests using standard library unittest, pytest, or mocks (`unittest.mock`).\n"
    "4. Visual Verification: If your task touches UI, HTML, CSS, or rendering, you may generate image snapshots (e.g. via python Pillow/matplotlib/playwright) and include `\"screenshot\": \"preview.png\"` in your JSON.\n"
    "5. Run `git diff` to verify that your changes are written to disk.\n"
    "6. ONLY after your code changes are written and verified with git diff, summarize your completed work in markdown without emitting further JSON command blocks."
)

STALL_TIMEOUT_SECONDS = 90  # if no LLM tier responds, fail cleanly instead of eating the task time limit
MAX_OUTPUT_CHARS = 10000  # command output fed back to the LLM, to prevent context explosion

EmitFn = Callable[[EventType, dict], Awaitable[None]]


def initial_prompt(
    prompt: str,
    repo_url: Optional[str],
    branch_name: str,
    follow_ups: Sequence[str] = (),
    continuing: Optional[bool] = None,
) -> str:
    """continuing: True = earlier changes were restored, False = restoring them failed,
    None = fresh start (first run, or a retry that redoes everything)."""
    parts = [f"Task Goal:\n{prompt}\n"]
    if follow_ups:
        earlier, latest = list(follow_ups[:-1]), follow_ups[-1]
        for i, message in enumerate(earlier, 1):
            parts.append(f"Earlier follow-up {i}:\n{message}\n")
        parts.append(f"Latest follow-up (do this now):\n{latest}\n")
        if continuing:
            parts.append("The work from earlier turns is already in the working tree (uncommitted); build on it.\n")
        else:
            lost = "Earlier changes could not be restored, so the" if continuing is False else "The"
            parts.append(
                f"{lost} working tree is a clean checkout: do what the goal and earlier follow-ups ask, "
                "then the latest follow-up.\n"
            )
    parts.append(
        f"Repository: {repo_url or 'Local workspace repository'}\n"
        f"Active Branch: {branch_name}\n"
        "Begin by listing files or inspecting the project structure."
    )
    return "\n".join(parts)


async def run_agent_commands(
    llm_session,
    workspace,
    first_prompt: str,
    emit: EmitFn,
    max_iterations: int,
    stats: dict,
    should_stop: Optional[Callable[[], Awaitable[bool]]] = None,
    stall_timeout: float = STALL_TIMEOUT_SECONDS,
) -> str:
    """Runs LLM turns until a final summary. Returns "completed", "cancelled" or "max_iterations".

    Raises RuntimeError when no LLM tier answers within `stall_timeout`. Updates stats["iterations"]
    and stats["commands"].
    """
    current_prompt = first_prompt

    async def handle_fallback_notice(msg: str):
        await emit(EventType.LOG, {"message": msg})

    for iteration in range(max_iterations):
        stats["iterations"] = iteration + 1
        if should_stop and await should_stop():
            return "cancelled"

        try:
            text = await asyncio.wait_for(
                llm_session.send_message(current_prompt, on_fallback=handle_fallback_notice),
                timeout=stall_timeout
            )
        except asyncio.TimeoutError:
            timeout_msg = (
                f"Agent timed out: No LLM response received within {stall_timeout} seconds. "
                "All providers may be overloaded or rate-limited. Please retry the task later."
            )
            await emit(EventType.LOG, {"message": timeout_msg})
            raise RuntimeError(timeout_msg)

        # Check if LLM emitted a command block
        if "```json" in text and "\"command\":" in text:
            try:
                json_str = text.split("```json")[1].split("```")[0].strip()
                cmd_obj = json.loads(json_str)
                command = cmd_obj.get("command", "")
                screenshot_file = cmd_obj.get("screenshot")
                screenshot_caption = cmd_obj.get("caption") or f"Visual snapshot of {screenshot_file}"

                await emit(EventType.COMMAND, {"command": command})

                stats["commands"] = stats.get("commands", 0) + 1
                exit_code, output = await workspace.aexecute_command(command)

                # Capture visual screenshot artifact if requested
                if screenshot_file:
                    b64_img = await workspace.aget_file_base64(screenshot_file)
                    if b64_img:
                        await emit(EventType.RESULT, {
                            "screenshot": f"data:image/png;base64,{b64_img}",
                            "filename": screenshot_file.split("/")[-1],
                            "caption": screenshot_caption
                        })

                if len(output) > MAX_OUTPUT_CHARS:
                    output = output[:MAX_OUTPUT_CHARS] + "\n...[output truncated for length]"

                result_str = f"[Exit code: {exit_code}]\n{output}"
                await emit(EventType.RESULT, {"output": result_str, "exit_code": exit_code})

                current_prompt = f"Command output:\n{result_str}"
            except Exception as e:
                error_msg = f"Failed to parse or execute command: {e}"
                await emit(EventType.RESULT, {"output": error_msg})
                current_prompt = f"Error: {error_msg}. Please check your JSON format and try again."
        else:
            # Final summary output
            await emit(EventType.LOG, {"message": f"Agent completed: {text}"})
            return "completed"

    return "max_iterations"
