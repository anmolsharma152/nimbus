from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://nimbus_user:nimbus_password@localhost:5432/nimbus_db",
        description="Async PostgreSQL database connection string."
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for arq job queue."
    )
    GEMINI_API_KEY: str | None = Field(
        default=None,
        description="Google Gemini API key for Tier 1 primary agent reasoning."
    )
    GEMINI_MODEL: str = Field(
        default="gemini-3.6-flash",
        description="Gemini LLM model identifier (Tier 1)."
    )
    GROQ_API_KEY: str | None = Field(
        default=None,
        description="Groq API key for Tier 2 secondary agent fallback."
    )
    GROQ_MODEL: str = Field(
        default="openai/gpt-oss-120b",
        description="Groq clean model identifier (Tier 2)."
    )
    OPENROUTER_API_KEY: str | None = Field(
        default=None,
        description="OpenRouter API key for Tier 3 tertiary agent fallback."
    )
    OPENROUTER_MODEL: str = Field(
        default="cohere/north-mini-code:free",
        description="OpenRouter free model identifier (Tier 3)."
    )
    GITHUB_TOKEN: str | None = Field(
        default=None,
        description="GitHub personal access token for cloning and PR creation."
    )
    GITHUB_CLIENT_ID: str | None = Field(
        default=None,
        description="GitHub OAuth App Client ID."
    )
    GITHUB_CLIENT_SECRET: str | None = Field(
        default=None,
        description="GitHub OAuth App Client Secret."
    )
    JWT_SECRET_KEY: str = Field(
        default="nimbus-super-secure-jwt-key-2026-change-in-prod",
        description="Secret key for signing session JWT tokens."
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Algorithm for signing session JWT tokens."
    )
    JWT_EXPIRE_MINUTES: int = Field(
        default=10080,
        description="Session JWT token validity in minutes (7 days)."
    )
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Frontend web application base URL for OAuth redirects."
    )
    MAX_AGENT_ITERATIONS: int = Field(
        default=20,
        description="Maximum turns allowed for an agent task."
    )
    API_INTERNAL_URL: str = Field(
        default="http://localhost:8000",
        description="Base URL for internal WebSocket broadcast gateway."
    )
    DB_ECHO: bool = Field(
        default=False,
        description="Enable raw SQL logging."
    )

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        extra="ignore"
    )


settings = Settings()
