"""Rate limiting and task concurrency control for multi-tenant isolation."""

import datetime
import inspect
import asyncio
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from .models import User, Task, TaskStatus


async def _extract_scalar(result) -> int:
    """Helper to safely extract integer count from SQLAlchemy Result or Mock Result."""
    if result is None:
        return 0
    scalar_fn = getattr(result, "scalar", None)
    if callable(scalar_fn):
        val = scalar_fn()
        if inspect.isawaitable(val):
            val = await val
        try:
            return int(val) if val is not None else 0
        except (ValueError, TypeError):
            return 0
    return 0


async def check_task_submission_limits(
    user: Optional[User],
    db: AsyncSession
):
    """
    Enforces per-user concurrency quotas and sliding window rate limits.
    Prevents noisy neighbors from monopolizing worker sandboxes.
    """
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    one_hour_ago = now - datetime.timedelta(hours=1)

    if user:
        # Tier quotas
        is_pro = (user.tier or "free").lower() == "pro"
        max_concurrent = 10 if is_pro else 3
        max_per_hour = 100 if is_pro else 20

        # 1. Check concurrent running/pending tasks
        active_res = await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == user.id,
                Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
            )
        )
        active_count = await _extract_scalar(active_res)
        if active_count >= max_concurrent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Concurrency quota exceeded ({active_count}/{max_concurrent} active tasks). Please wait for ongoing tasks to complete."
            )

        # 2. Check hourly submission rate
        hourly_res = await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id == user.id,
                Task.created_at >= one_hour_ago
            )
        )
        hourly_count = await _extract_scalar(hourly_res)
        if hourly_count >= max_per_hour:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Hourly rate limit exceeded ({hourly_count}/{max_per_hour} tasks/hour). Please try again later."
            )
    else:
        # Anonymous / unauthenticated limits
        active_res = await db.execute(
            select(func.count(Task.id)).where(
                Task.user_id.is_(None),
                Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
            )
        )
        active_count = await _extract_scalar(active_res)
        if active_count >= 2:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Anonymous task capacity reached. Please sign in with GitHub for dedicated quota."
            )
