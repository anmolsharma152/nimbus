import re
from typing import Optional, Tuple
import httpx


def parse_github_repo(repo_url: str) -> Optional[Tuple[str, str]]:
    """
    Extracts (owner, repo) from a GitHub URL or 'owner/repo' string.
    Examples:
      - https://github.com/owner/repo.git -> ('owner', 'repo')
      - https://github.com/owner/repo -> ('owner', 'repo')
      - owner/repo -> ('owner', 'repo')
    """
    if not repo_url:
        return None

    cleaned = repo_url.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    pattern = r"(?:https?://github\.com/|git@github\.com:)?([^/]+)/([^/]+)$"
    match = re.search(pattern, cleaned)
    if match:
        return match.group(1), match.group(2)
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
    Creates a draft Pull Request on GitHub. Returns the HTML URL of the PR if successful, else None.
    """
    if not token:
        print("GitHub token not provided. Skipping PR creation.")
        return None

    parsed = parse_github_repo(repo_url)
    if not parsed:
        print(f"Could not parse GitHub repo from URL: {repo_url}")
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
            else:
                # If base 'main' fails, try fallback 'master'
                if resp.status_code == 422 and base_branch == "main":
                    payload["base"] = "master"
                    resp2 = await client.post(api_url, json=payload, headers=headers, timeout=15.0)
                    if resp2.status_code == 201:
                        return resp2.json().get("html_url")
                    print(f"Failed to create PR against master: {resp2.status_code} {resp2.text}")
                print(f"Failed to create PR: {resp.status_code} {resp.text}")
                return None
    except Exception as e:
        print(f"Exception while creating PR: {e}")
        return None
