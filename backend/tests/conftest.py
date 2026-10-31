import os

# Must be set before any `app` import: keeps the developer's real .env out of the test run
os.environ["NIMBUS_IGNORE_DOTENV"] = "1"

import pytest

from app import workspace


@pytest.fixture(autouse=True)
def reset_shared_docker_client():
    """Each test gets a fresh Docker client cache so per-test `docker.from_env` patches apply."""
    workspace._docker_client = None
    yield
    workspace._docker_client = None
