import pytest

from app import workspace


@pytest.fixture(autouse=True)
def reset_shared_docker_client():
    """Each test gets a fresh Docker client cache so per-test `docker.from_env` patches apply."""
    workspace._docker_client = None
    yield
    workspace._docker_client = None
