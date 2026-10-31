import asyncio
import json
import datetime
import logging
import time
from typing import Optional
import httpx
from arq import create_pool
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.future import select
import shlex

from .db import async_session
from .models import User, UserCredential, Task, TaskEvent, EventType, TaskStatus
from .settings import settings, secret_value
from .security import decrypt_secret, internal_api_token
from .workspace import UnifiedWorkspace, get_docker_client, reap_orphaned_containers, reap_orphaned_volumes
from .github_client import create_draft_pr
from .llm import LLMChatSession
from .agent import SYSTEM_INSTRUCTION, initial_prompt, run_agent_commands
from .events import event_bus
from .logging_config import configure_logging, task_id_var

logger = logging.getLogger(__name__)


async def log_event(db: AsyncSession, task_id: int, event_type: EventType, payload_dict: dict):
    """Persists a task event in PostgreSQL and broadcasts it to Redis Event Bus and API gateway."""
    event = TaskEvent(task_id=task_id, event_type=event_type, payload=json.dumps(payload_dict))
    db.add(event)
    await db.commit()
    await db.refresh(event)

    ev_type_str = str(event_type.value).lower() if hasattr(event_type, "value") else str(event_type).lower()
    ts_str = (event.created_at.isoformat() + "Z") if event.created_at else (datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z")

    # 1. Publish to Redis Event Bus (real-time fanout to all API replicas)
    try:
        await event_bus.publish_event(task_id, ev_type_str, payload_dict, ts_str, event_id=event.id)
    except Exception as e:
        logger.warning("Failed to publish task event to Redis: %s", e)

    # 2. HTTP fallback to internal endpoint
    try:
        api_base = settings.API_INTERNAL_URL or "http://localhost:8000"
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{api_base.rstrip('/')}/api/internal/tasks/{task_id}/events",
                json={
                    "id": event.id,
                    "type": ev_type_str,
                    "payload": json.dumps(payload_dict),
                    "timestamp": ts_str
                },
                headers={"X-Nimbus-Internal-Token": internal_api_token()}
            )
    except Exception as e:
        # Best effort: Redis pub/sub is the primary path to the API
        logger.debug("Internal event POST failed: %s", e)


async def run_agent_loop(
    ctx,
    task_id: int,
    prompt: str,
    repo_url: Optional[str] = None,
    git_branch: Optional[str] = None
):
    """Runs one agent task under the TASK_TIMEOUT_SECONDS wall-clock limit (also used without arq)."""
    task_token = task_id_var.set(task_id)
    stats: dict = {"status": "unknown"}
    start = time.perf_counter()
    try:
        await asyncio.wait_for(
            _execute_agent_task(task_id, prompt, repo_url, git_branch, stats),
            timeout=settings.TASK_TIMEOUT_SECONDS
        )
    except TimeoutError:
        # The task already marked itself FAILED and removed its workspace while being cancelled
        stats["reason"] = "time_limit"
        logger.warning("Task exceeded %ss time limit", settings.TASK_TIMEOUT_SECONDS)
    finally:
        _log_task_summary(stats, time.perf_counter() - start)
        task_id_var.reset(task_token)


def _log_task_summary(stats: dict, duration_s: float):
    """One machine-readable line per task: the source for dashboards and alerting."""
    llm_session = stats.pop("_llm", None)
    summary = {
        "event": "task_finished",
        "duration_s": round(duration_s, 2),
        "iterations": stats.get("iterations", 0),
        "commands": stats.get("commands", 0),
        "patch_chars": stats.get("patch_chars", 0),
        "pr_opened": stats.get("pr_opened", False),
        "reason": stats.get("reason"),
    }
    if llm_session is not None:
        summary["llm_calls"] = dict(llm_session.tier_calls)
        summary["llm_failures"] = dict(llm_session.tier_failures)
        summary["llm_seconds"] = round(llm_session.llm_seconds, 2)
    # `status` is a LogRecord-safe name; keep it last so it reads well in text logs
    summary["task_status"] = stats.get("status")
    logger.info("Task finished: %s", summary["task_status"], extra=summary)


async def _execute_agent_task(
    task_id: int,
    prompt: str,
    repo_url: Optional[str] = None,
    git_branch: Optional[str] = None,
    stats: Optional[dict] = None
):
    stats = stats if stats is not None else {}
    # Prompt length only: task prompts can contain private details
    logger.info(
        "Worker picked up task",
        extra={"event": "task_started", "repo_url": repo_url, "branch": git_branch, "prompt_chars": len(prompt)}
    )
    
    branch_name = git_branch or f"nimbus/task-{task_id}"
    workspace = UnifiedWorkspace(task_id=task_id)
    
    async with async_session() as db:
        task = await db.get(Task, task_id)
        if not task:
            stats["status"] = "missing"
            return

        # Look up user details and decrypt vault credentials
        user = None
        user_github_token = None
        user_gemini_key = None
        user_groq_key = None
        user_openrouter_key = None
        git_user_name = "Nimbus Agent"
        git_user_email = "agent@nimbus.ai"

        if task.user_id:
            user = await db.get(User, task.user_id)
            if user:
                git_user_name = user.display_name or user.username
                git_user_email = user.email or f"{user.username}@users.noreply.github.com"
                if user.github_token:
                    user_github_token = decrypt_secret(user.github_token)

                # Fetch any BYOK provider keys from UserCredential vault
                creds_res = await db.execute(select(UserCredential).where(UserCredential.user_id == user.id))
                creds = creds_res.scalars().all()
                for c in creds:
                    decrypted = decrypt_secret(c.encrypted_value)
                    if c.provider == "github_pat" and decrypted:
                        user_github_token = decrypted
                    elif c.provider == "gemini" and decrypted:
                        user_gemini_key = decrypted
                    elif c.provider == "groq" and decrypted:
                        user_groq_key = decrypted
                    elif c.provider == "openrouter" and decrypted:
                        user_openrouter_key = decrypted

        final_github_token = user_github_token or secret_value(settings.GITHUB_TOKEN)
        has_any_llm_key = bool(
            user_gemini_key or user_groq_key or user_openrouter_key or
            settings.GEMINI_API_KEY or settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY
        )

        if not has_any_llm_key:
            logger.warning("No LLM API keys configured (user BYOK or server environment); failing task")
            stats.update(status="failed", reason="no_llm_key")
            task.status = TaskStatus.FAILED
            await db.commit()
            await log_event(
                db,
                task_id,
                EventType.LOG,
                {"message": "No LLM API keys configured. Please configure an API key in Settings or environment."}
            )
            await log_event(db, task_id, EventType.STATUS, {"status": "failed"})
            return
        
        task.status = TaskStatus.RUNNING
        task.git_branch = branch_name
        await db.commit()
        await log_event(db, task_id, EventType.STATUS, {"status": "running"})
        await log_event(
            db,
            task_id,
            EventType.LOG,
            {"message": f"Agent initialized for @{git_user_name}. Provisioning isolated workspace on branch '{branch_name}'..."}
        )

        try:
            setup_code, setup_out = await workspace.asetup(
                repo_url=repo_url,
                branch_name=branch_name,
                github_token=final_github_token
            )
            if setup_code != 0:
                raise RuntimeError(f"Workspace setup failed: {setup_out}")
            if setup_out:
                await log_event(db, task_id, EventType.LOG, {"message": setup_out})

            # Configure user author identity inside the sandbox
            await workspace.aexecute_command(f"git config user.name {shlex.quote(git_user_name)}")
            await workspace.aexecute_command(f"git config user.email {shlex.quote(git_user_email)}")
                
            await log_event(
                db,
                task_id,
                EventType.LOG,
                {"message": f"Docker workspace ready in /workspace/repo (Author: {git_user_name} <{git_user_email}>). Starting 3-tier LLM reasoning loop..."}
            )

            llm_session = LLMChatSession(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.1,
                gemini_api_key=user_gemini_key,
                groq_api_key=user_groq_key,
                openrouter_api_key=user_openrouter_key
            )
            stats["_llm"] = llm_session

            async def emit(event_type: EventType, payload: dict):
                await log_event(db, task_id, event_type, payload)

            async def cancelled_by_user() -> bool:
                await db.refresh(task)
                return task.status == TaskStatus.CANCELLED

            outcome = await run_agent_commands(
                llm_session,
                workspace,
                initial_prompt(prompt, repo_url, branch_name),
                emit,
                max_iterations=settings.MAX_AGENT_ITERATIONS,
                stats=stats,
                should_stop=cancelled_by_user,
            )
            if outcome == "cancelled":
                stats["status"] = "cancelled"
                await log_event(db, task_id, EventType.LOG, {"message": "Task execution cancelled by user."})
                return
            
            # Post-execution: capture diff and create PR / commit
            diff_text = await workspace.aget_diff()
            if diff_text:
                task.patch_diff = diff_text
                stats["patch_chars"] = len(diff_text)
                await log_event(
                    db,
                    task_id,
                    EventType.LOG,
                    {"message": f"Generated patch diff ({len(diff_text)} chars). Committing changes..."}
                )
                await workspace.acommit_changes(f"Nimbus: {prompt[:60]}")
                
                # Push branch and open Draft PR if repo_url and token exist
                if repo_url and final_github_token:
                    await log_event(db, task_id, EventType.LOG, {"message": f"Pushing branch '{branch_name}' to GitHub..."})
                    push_code, push_out = await workspace.apush_branch(
                        branch_name, repo_url, final_github_token,
                        message=f"Nimbus: {prompt[:60]}",
                        author_name=git_user_name,
                        author_email=git_user_email
                    )
                    if push_code == 0:
                        author_tag = f"@{user.username}" if user else "Nimbus Agent"
                        pr_url = await create_draft_pr(
                            repo_url=repo_url,
                            title=f"Nimbus Agent: {prompt[:60]}",
                            body=f"### Automated Pull Request by Nimbus\n\n**Task #{task_id}**\n**Author:** {author_tag}\n\n**Prompt:**\n{prompt}\n\n### Changes Generated:\n```diff\n{diff_text[:3000]}\n```",
                            head_branch=branch_name,
                            token=final_github_token
                        )
                        if pr_url:
                            task.pr_url = pr_url
                            stats["pr_opened"] = True
                            await log_event(db, task_id, EventType.LOG, {"message": f"Draft PR opened successfully: {pr_url}"})
                        else:
                            await log_event(db, task_id, EventType.LOG, {"message": "Branch pushed, but Draft PR creation failed."})
                    else:
                        await log_event(db, task_id, EventType.LOG, {"message": f"Failed to push branch: {push_out}"})

            task.status = TaskStatus.COMPLETED
            await db.commit()
            stats["status"] = "completed"
            await log_event(db, task_id, EventType.STATUS, {"status": "completed"})

        except Exception as e:
            logger.exception("Agent loop failed")
            stats.update(status="failed", reason=type(e).__name__)
            await log_event(db, task_id, EventType.LOG, {"message": f"Agent failed with exception: {e}"})
            task.status = TaskStatus.FAILED
            await db.commit()
            await log_event(db, task_id, EventType.STATUS, {"status": "failed"})
        except asyncio.CancelledError:
            # Time limit, arq job timeout, or worker shutdown: never leave the task stuck in RUNNING
            stats.update(status="failed", reason=stats.get("reason") or "interrupted")
            limit_min = round(settings.TASK_TIMEOUT_SECONDS / 60)
            await log_event(db, task_id, EventType.LOG, {
                "message": f"Agent stopped before finishing: task time limit ({limit_min} min) reached or worker shut down."
            })
            task.status = TaskStatus.FAILED
            await db.commit()
            await log_event(db, task_id, EventType.STATUS, {"status": "failed"})
            raise
        finally:
            # Shielded so a second cancellation can't abort container removal midway
            await asyncio.shield(workspace.acleanup())

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
redis_settings = RedisSettings.from_dsn(normalize_redis_url(secret_value(settings.REDIS_URL)))

async def enqueue_task(
    task_id: int,
    prompt: str,
    repo_url: Optional[str] = None,
    git_branch: Optional[str] = None
):
    enqueued = False
    try:
        pool = await create_pool(redis_settings)
        await pool.enqueue_job('run_agent_loop', task_id, prompt, repo_url, git_branch)
        await pool.close()
        enqueued = True
        logger.info("Task %s enqueued to Redis queue", task_id)
    except Exception as e:
        logger.warning("Redis queue unavailable (%s); running task %s in-process", e, task_id)
    
    if not enqueued:
        # Launch agent loop directly in async event loop background task
        asyncio.create_task(run_agent_loop(None, task_id, prompt, repo_url, git_branch))

async def reap_orphaned_workspaces(ctx):
    """Removes task containers that outlived the task time limit (e.g. after a worker crash)."""
    client = get_docker_client()
    if client is None:
        return 0
    max_age = settings.TASK_TIMEOUT_SECONDS + 600
    removed = await asyncio.to_thread(reap_orphaned_containers, client, max_age)
    # Volumes after containers: a volume still attached to a container can't be removed
    removed += await asyncio.to_thread(reap_orphaned_volumes, client, max_age)
    if removed:
        logger.info("Reaped %s orphaned workspace container(s)/volume(s)", removed)
    return removed


async def worker_startup(ctx):
    configure_logging()


class WorkerSettings:
    functions = [run_agent_loop]
    on_startup = worker_startup
    redis_settings = redis_settings
    # Backstop only: run_agent_loop enforces TASK_TIMEOUT_SECONDS itself and fails the task cleanly
    job_timeout = settings.TASK_TIMEOUT_SECONDS + 120
    # A cancelled agent run is marked FAILED; re-running it from scratch is the user's call (Retry button)
    max_tries = 1
    cron_jobs = [
        cron(reap_orphaned_workspaces, minute=set(range(0, 60, 10)), run_at_startup=True)
    ]
