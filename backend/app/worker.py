import asyncio
import json
from typing import Optional
import httpx
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession
from google import genai
from google.genai import types

from .db import async_session
from .models import Task, TaskEvent, EventType, TaskStatus
from .settings import settings
from .workspace import DockerWorkspace
from .github_client import create_draft_pr
from .llm import LLMChatSession


async def log_event(db: AsyncSession, task_id: int, event_type: EventType, payload_dict: dict):
    """Persists a task event in PostgreSQL and broadcasts it to the API WebSocket gateway."""
    event = TaskEvent(task_id=task_id, event_type=event_type, payload=json.dumps(payload_dict))
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # Post to the main API so it broadcasts via WebSockets
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"http://localhost:8000/api/internal/tasks/{task_id}/events",
                json={
                    "type": str(event_type.value).lower(),
                    "payload": json.dumps(payload_dict),
                    "timestamp": event.created_at.isoformat()
                },
                timeout=5.0
            )
    except Exception as e:
        print(f"Failed to broadcast event: {e}")


async def run_agent_loop(
    ctx,
    task_id: int,
    prompt: str,
    repo_url: Optional[str] = None,
    git_branch: Optional[str] = None
):
    print(f"Worker picked up task {task_id}: {prompt} (repo: {repo_url}, branch: {git_branch})")
    
    has_any_llm_key = bool(settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY)
    if not has_any_llm_key:
        print("No LLM API keys configured (GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY). Aborting.")
        async with async_session() as db:
            task = await db.get(Task, task_id)
            if task:
                task.status = TaskStatus.FAILED
                await db.commit()
                await log_event(
                    db,
                    task_id,
                    EventType.LOG,
                    {"message": "No LLM API keys configured in environment (GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY)."}
                )
                await log_event(db, task_id, EventType.STATUS, {"status": "failed"})
        return

    branch_name = git_branch or f"nimbus/task-{task_id}"
    workspace = DockerWorkspace(task_id=task_id)
    
    async with async_session() as db:
        task = await db.get(Task, task_id)
        if not task:
            return
        
        task.status = TaskStatus.RUNNING
        task.git_branch = branch_name
        await db.commit()
        await log_event(db, task_id, EventType.STATUS, {"status": "running"})
        await log_event(
            db,
            task_id,
            EventType.LOG,
            {"message": f"Agent initialized. Setting up Docker workspace on branch '{branch_name}'..."}
        )

        try:
            _, setup_out = await workspace.asetup(
                repo_url=repo_url,
                branch_name=branch_name,
                github_token=settings.GITHUB_TOKEN
            )
            if setup_out:
                await log_event(db, task_id, EventType.LOG, {"message": setup_out})
                
            await log_event(
                db,
                task_id,
                EventType.LOG,
                {"message": "Docker workspace ready in /workspace/repo. Starting 3-tier LLM reasoning loop..."}
            )

            system_instruction = (
                "You are Nimbus, an autonomous cloud software engineer. You operate inside an isolated Linux workspace "
                "with git, python3, and build tools pre-installed. The current working directory is /workspace/repo.\n\n"
                "Your objective is to inspect the codebase, make necessary code modifications, run tests to verify your fix, "
                "and ensure the repository is left in a clean, working state.\n\n"
                "To execute a bash command (e.g. to inspect files, edit code via scripts or tools, run tests, or view git diff), "
                "output a JSON block strictly formatted as:\n"
                "```json\n{\n  \"command\": \"<your bash command here>\"\n}\n```\n\n"
                "Guidelines:\n"
                "- Run commands sequentially. Wait for the command output before emitting your next action.\n"
                "- Use `git status` and `git diff` to verify your changes.\n"
                "- Run test suites or verification scripts to prove correctness.\n"
                "- When finished, summarize your changes in clear markdown without emitting further JSON command blocks."
            )

            llm_session = LLMChatSession(
                system_instruction=system_instruction,
                temperature=0.1
            )

            # Agent Loop
            current_prompt = (
                f"Task Goal:\n{prompt}\n\n"
                f"Repository: {repo_url or 'Local workspace repository'}\n"
                f"Active Branch: {branch_name}\n"
                "Begin by listing files or inspecting the project structure."
            )
            max_iterations = settings.MAX_AGENT_ITERATIONS
            
            for iteration in range(max_iterations):
                # Check for cancellation before turn
                await db.refresh(task)
                if task.status == TaskStatus.CANCELLED:
                    await log_event(db, task_id, EventType.LOG, {"message": "Task execution cancelled by user."})
                    return

                async def handle_fallback_notice(msg: str):
                    await log_event(db, task_id, EventType.LOG, {"message": msg})

                text = await llm_session.send_message(current_prompt, on_fallback=handle_fallback_notice)
                
                # Check if LLM emitted a command block
                if "```json" in text and "\"command\":" in text:
                    try:
                        json_str = text.split("```json")[1].split("```")[0].strip()
                        cmd_obj = json.loads(json_str)
                        command = cmd_obj.get("command", "")
                        
                        await log_event(db, task_id, EventType.COMMAND, {"command": command})
                        
                        # Execute in workspace asynchronously
                        exit_code, output = await workspace.aexecute_command(command)
                        
                        # Limit output length to prevent context explosion
                        if len(output) > 10000:
                            output = output[:10000] + "\n...[output truncated for length]"
                            
                        result_str = f"[Exit code: {exit_code}]\n{output}"
                        await log_event(db, task_id, EventType.RESULT, {"output": result_str})
                        
                        current_prompt = f"Command output:\n{result_str}"
                    except Exception as e:
                        error_msg = f"Failed to parse or execute command: {e}"
                        await log_event(db, task_id, EventType.RESULT, {"output": error_msg})
                        current_prompt = f"Error: {error_msg}. Please check your JSON format and try again."
                else:
                    # Final summary output
                    await log_event(db, task_id, EventType.LOG, {"message": f"Agent completed: {text}"})
                    break
            
            # Post-execution: capture diff and create PR / commit
            diff_text = await workspace.aget_diff()
            if diff_text:
                task.patch_diff = diff_text
                await log_event(
                    db,
                    task_id,
                    EventType.LOG,
                    {"message": f"Generated patch diff ({len(diff_text)} chars). Committing changes..."}
                )
                await workspace.acommit_changes(f"Nimbus: {prompt[:60]}")
                
                # Push branch and open Draft PR if repo_url and token exist
                if repo_url and settings.GITHUB_TOKEN:
                    await log_event(db, task_id, EventType.LOG, {"message": f"Pushing branch '{branch_name}' to GitHub..."})
                    push_code, push_out = await workspace.apush_branch(branch_name, repo_url, settings.GITHUB_TOKEN)
                    if push_code == 0:
                        pr_url = await create_draft_pr(
                            repo_url=repo_url,
                            title=f"Nimbus Agent: {prompt[:60]}",
                            body=f"### Automated Pull Request by Nimbus\n\n**Task #{task_id}**\n\n**Prompt:**\n{prompt}\n\n### Changes Generated:\n```diff\n{diff_text[:3000]}\n```",
                            head_branch=branch_name,
                            token=settings.GITHUB_TOKEN
                        )
                        if pr_url:
                            task.pr_url = pr_url
                            await log_event(db, task_id, EventType.LOG, {"message": f"Draft PR opened successfully: {pr_url}"})
                        else:
                            await log_event(db, task_id, EventType.LOG, {"message": "Branch pushed, but Draft PR creation failed."})
                    else:
                        await log_event(db, task_id, EventType.LOG, {"message": f"Failed to push branch: {push_out}"})

            task.status = TaskStatus.COMPLETED
            await db.commit()
            await log_event(db, task_id, EventType.STATUS, {"status": "completed"})

        except Exception as e:
            print(f"Error in agent loop: {e}")
            await log_event(db, task_id, EventType.LOG, {"message": f"Agent failed with exception: {e}"})
            task.status = TaskStatus.FAILED
            await db.commit()
            await log_event(db, task_id, EventType.STATUS, {"status": "failed"})
        finally:
            await workspace.acleanup()

def normalize_redis_url(url: Optional[str]) -> str:
    """Sanitizes and normalizes Redis connection strings (handles quotes, cli snippets, empty strings)."""
    if not url:
        return "redis://localhost:6379/0"
    
    cleaned = url.strip().strip("'\"")
    # If copied from `redis-cli -u rediss://...`
    if "-u " in cleaned:
        cleaned = cleaned.split("-u ")[-1].split(" ")[0].strip("'\"")
    elif " " in cleaned:
        for part in cleaned.split():
            if part.startswith(("redis://", "rediss://")):
                cleaned = part.strip("'\"")
                break

    if not cleaned.startswith(("redis://", "rediss://")):
        return "redis://localhost:6379/0"
    
    return cleaned


# Setup arq settings with sanitized Redis URL
redis_settings = RedisSettings.from_dsn(normalize_redis_url(settings.REDIS_URL))

async def enqueue_task(
    task_id: int,
    prompt: str,
    repo_url: Optional[str] = None,
    git_branch: Optional[str] = None
):
    try:
        pool = await create_pool(redis_settings)
        await pool.enqueue_job('run_agent_loop', task_id, prompt, repo_url, git_branch)
        await pool.close()
    except Exception as e:
        print(f"Failed to enqueue task {task_id}: {e}")

class WorkerSettings:
    functions = [run_agent_loop]
    redis_settings = redis_settings
