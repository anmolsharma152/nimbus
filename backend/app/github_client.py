import asyncio
import re
import logging
from dataclasses import dataclass
from typing import Optional, Tuple
import httpx

logger = logging.getLogger(__name__)


def parse_github_repo(repo_url: str) -> Optional[Tuple[str, str]]:
    """
    Extracts (owner, repo) from a GitHub URL or 'owner/repo' string.
    Ensures URLs without github.com or invalid strings are rejected.
    
    Examples:
      - https://github.com/owner/repo.git -> ('owner', 'repo')
      - https://github.com/owner/repo/ -> ('owner', 'repo')
      - git@github.com:owner/repo.git -> ('owner', 'repo')
      - owner/repo -> ('owner', 'repo')
    """
    if not repo_url or not isinstance(repo_url, str):
        return None

    cleaned = repo_url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    # Match https://github.com/owner/repo, http://github.com/owner/repo, git@github.com:owner/repo, or owner/repo
    pattern = r"^(?:https?://github\.com/|git@github\.com:)?([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)$"
    match = re.match(pattern, cleaned)
    if match:
        owner, repo = match.group(1), match.group(2)
        # Avoid false positives where domain was matched as owner (e.g. gitlab.com/owner)
        if "." in owner and not cleaned.startswith(("http", "git@")):
            return None
        return owner, repo
    return None


GITHUB_API = "https://api.github.com"


def _headers(token: Optional[str]) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Nimbus-Agent",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@dataclass
class RepoAccess:
    full_name: str
    default_branch: str
    can_push: bool
    allow_forking: bool


async def get_repo_access(repo_url: str, token: Optional[str]) -> Tuple[Optional[RepoAccess], Optional[str]]:
    """Looks up the repo as the task owner. Returns (access, None) or (None, user-facing error)."""
    parsed = parse_github_repo(repo_url)
    if not parsed:
        return None, f"Could not parse a GitHub repository from {repo_url}."
    owner, repo = parsed
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=_headers(token))
    except httpx.HTTPError as e:
        logger.warning("GitHub repo lookup failed: %s", type(e).__name__)
        return None, "Could not reach GitHub to check repository access. Please try again."
    if resp.status_code in (401, 403, 404):
        return None, (
            f"Repository {owner}/{repo} was not found or your GitHub account cannot access it "
            f"(HTTP {resp.status_code})."
        )
    if resp.status_code != 200:
        return None, f"GitHub returned HTTP {resp.status_code} while checking {owner}/{repo}."
    data = resp.json()
    return RepoAccess(
        full_name=data.get("full_name") or f"{owner}/{repo}",
        default_branch=data.get("default_branch") or "main",
        can_push=bool((data.get("permissions") or {}).get("push")) and bool(token),
        allow_forking=data.get("allow_forking", True) is not False,
    ), None


async def ensure_fork(
    access: RepoAccess,
    token: str,
    wait_seconds: float = 60.0,
    poll_interval: float = 3.0,
) -> Tuple[Optional[str], Optional[str]]:
    """Forks the repo into the token owner's account (or reuses their fork); returns (fork full_name, error)."""
    if not access.allow_forking:
        return None, f"{access.full_name} does not allow forking, and you have no write access to it."
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{access.full_name}/forks",
                json={"default_branch_only": True},
                headers=_headers(token),
            )
            if resp.status_code not in (200, 202):
                return None, f"Could not fork {access.full_name} (HTTP {resp.status_code})."
            fork_name = resp.json().get("full_name")
            if not fork_name:
                return None, f"GitHub did not return a fork name for {access.full_name}."
            # Forks are created asynchronously: the repo exists before its branches are copied
            loop = asyncio.get_running_loop()
            deadline = loop.time() + wait_seconds
            while True:
                check = await client.get(
                    f"{GITHUB_API}/repos/{fork_name}/branches", params={"per_page": 1}, headers=_headers(token)
                )
                if check.status_code == 200 and check.json():
                    return fork_name, None
                if loop.time() >= deadline:
                    return None, f"Fork {fork_name} was not ready after {int(wait_seconds)}s."
                await asyncio.sleep(poll_interval)
    except httpx.HTTPError as e:
        logger.warning("GitHub fork request failed: %s", type(e).__name__)
        return None, f"Could not reach GitHub to fork {access.full_name}."


async def create_draft_pr(
    repo_url: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: str,
    token: Optional[str] = None,
    head_owner: Optional[str] = None,
) -> Optional[str]:
    """
    Opens a draft PR from head_branch (in head_owner's fork when given) into base_branch,
    which callers take from the repo's default branch. Returns the PR URL, or None.
    """
    if not token:
        logger.warning("GitHub token not provided. Skipping PR creation.")
        return None

    parsed = parse_github_repo(repo_url)
    if not parsed:
        logger.error("Could not parse GitHub repo from URL: %s", repo_url)
        return None

    owner, repo = parsed
    payload = {
        "title": title,
        "body": body,
        "head": f"{head_owner}:{head_branch}" if head_owner else head_branch,
        "base": base_branch,
        "draft": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls", json=payload, headers=_headers(token)
            )
    except httpx.HTTPError as e:
        logger.error("Exception while creating Draft PR: %s", type(e).__name__)
        return None
    if resp.status_code == 201:
        return resp.json().get("html_url")
    logger.warning("Failed to create Draft PR on GitHub (HTTP %s)", resp.status_code)
    return None
