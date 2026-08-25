import re
import logging
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


async def create_draft_pr(
    repo_url: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
    token: Optional[str] = None
) -> Optional[str]:
    """
    Creates a draft Pull Request on GitHub.
    Returns the HTML URL of the PR if successful, else None.
    """
    if not token:
        logger.warning("GitHub token not provided. Skipping PR creation.")
        return None

    parsed = parse_github_repo(repo_url)
    if not parsed:
        logger.error(f"Could not parse GitHub repo from URL: {repo_url}")
        return None

    owner, repo = parsed
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Nimbus-Agent"
    }
    payload = {
        "title": title,
        "body": body,
        "head": head_branch,
        "base": base_branch,
        "draft": True
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(api_url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code == 201:
                pr_data = resp.json()
                return pr_data.get("html_url")
            elif resp.status_code == 422 and base_branch == "main":
                # Fallback to master if default branch is master
                payload["base"] = "master"
                resp2 = await client.post(api_url, json=payload, headers=headers, timeout=15.0)
                if resp2.status_code == 201:
                    return resp2.json().get("html_url")
                logger.warning(f"Failed to create PR against master branch (HTTP {resp2.status_code})")
                return None
            else:
                logger.warning(f"Failed to create Draft PR on GitHub (HTTP {resp.status_code})")
                return None
    except Exception as e:
        logger.error(f"Exception while creating Draft PR: {e}")
        return None
