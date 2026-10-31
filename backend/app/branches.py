"""Validation for the branch an agent task pushes to.

Tasks only ever create a new branch. A user-supplied name must be a valid git ref and must not
be a default or long-lived branch; the push itself also refuses to touch a branch that already
exists on the remote (see `workspace.push_script`), which covers each repo's actual default.
"""

import re
from typing import Optional

MAX_BRANCH_LENGTH = 100

# Common default / long-lived branch names, compared case-insensitively
PROTECTED_BRANCHES = frozenset({
    "main", "master", "trunk", "develop", "development", "dev", "default",
    "staging", "stage", "production", "prod", "release", "stable", "gh-pages", "head",
})
PROTECTED_PREFIXES = ("release/", "releases/", "hotfix/", "refs/")

_ALLOWED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def validate_task_branch(name: Optional[str]) -> Optional[str]:
    """Returns the cleaned branch name (None if not given); raises ValueError if it is not allowed."""
    if name is None:
        return None
    name = name.strip()
    if not name:
        return None
    if len(name) > MAX_BRANCH_LENGTH:
        raise ValueError(f"Branch name is longer than {MAX_BRANCH_LENGTH} characters.")
    if (
        not _ALLOWED.match(name)
        or ".." in name
        or "//" in name
        or name.endswith(("/", ".", ".lock"))
        or "/." in name
    ):
        raise ValueError("Branch name is not a valid git branch name.")
    lowered = name.lower()
    if lowered in PROTECTED_BRANCHES or lowered.startswith(PROTECTED_PREFIXES):
        raise ValueError(
            f"Branch '{name}' is a default or protected branch; Nimbus only pushes to new branches."
        )
    return name
