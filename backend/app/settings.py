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
        description="Google Gemini API key for agent reasoning."
    )
    GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Gemini LLM model identifier."
    )
    GITHUB_TOKEN: str | None = Field(
        default=None,
        description="GitHub personal access token for cloning and PR creation."
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
