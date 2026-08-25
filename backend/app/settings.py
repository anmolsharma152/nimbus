from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://nimbus_user:nimbus_password@localhost:5555/nimbus_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    GEMINI_API_KEY: str | None = None
    GITHUB_TOKEN: str | None = None
    DEFAULT_FIXTURE_REPO: str = "https://github.com/octocat/Hello-World.git"

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],
        extra="ignore"
    )

settings = Settings()
