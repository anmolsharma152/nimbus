from unittest.mock import patch

from pydantic import SecretStr

from app.settings import Settings, secret_value, settings

CANARY = "canary-secret-7f3a"

SECRET_FIELDS = (
    "DATABASE_URL",
    "REDIS_URL",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GITHUB_TOKEN",
    "GITHUB_CLIENT_SECRET",
    "JWT_SECRET_KEY",
)


def _canary_settings() -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL=f"postgresql://nimbus_user:{CANARY}@localhost:5432/nimbus_db",
        REDIS_URL=f"rediss://default:{CANARY}@redis.example:6379",
        GEMINI_API_KEY=CANARY,
        GROQ_API_KEY=CANARY,
        OPENROUTER_API_KEY=CANARY,
        GITHUB_TOKEN=CANARY,
        GITHUB_CLIENT_SECRET=CANARY,
        JWT_SECRET_KEY=CANARY,
    )


def test_secret_fields_are_masked_in_repr_and_str():
    s = _canary_settings()
    assert CANARY not in repr(s)
    assert CANARY not in str(s)
    for field in SECRET_FIELDS:
        assert isinstance(getattr(s, field), SecretStr), field


def test_failed_mock_patch_does_not_print_secrets():
    """Regression: mock's 'does not have the attribute' error embeds repr(settings)."""
    s = _canary_settings()
    try:
        with patch.object(s, "NOT_A_SETTING", 1):
            pass
    except AttributeError as e:
        assert CANARY not in str(e)
    else:
        raise AssertionError("expected AttributeError")


def test_secret_value_unwraps_secrets_and_passes_plain_values():
    s = _canary_settings()
    assert secret_value(s.GROQ_API_KEY) == CANARY
    assert secret_value("plain") == "plain"
    assert secret_value(None) is None


def test_test_suite_does_not_load_dotenv():
    assert settings.model_config.get("env_file") is None
