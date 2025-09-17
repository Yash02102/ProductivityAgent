from pathlib import Path

from pydantic import AnyUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_cs_code_analyzer() -> str | None:
    """Return the built C# analyzer path if available."""
    root = Path(__file__).resolve().parent.parent
    candidates = [
        root / "language_parsers" / "csharp" / "bin" / "Release" / "net8.0" / "CSharpCodeParser.dll",
        root / "language_parsers" / "csharp" / "bin" / "Debug" / "net8.0" / "CSharpCodeParser.dll",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # App
    APP_ENV: str = "dev"  # dev|staging|prod
    APP_DEBUG: bool = False
    APP_API_KEY: SecretStr | None = None  # for protecting the API

    # GitLab
    GITLAB_URL: AnyUrl
    GITLAB_TOKEN: SecretStr

    # Jira
    JIRA_INSTANCE_URL: AnyUrl
    JIRA_API_TOKEN: SecretStr
    JIRA_USERNAME: str
    JIRA_IS_CLOUD: bool = True

    # Code analysis
    cs_code_analyzer: str | None = _default_cs_code_analyzer()

    # LLM (optional)
    LLM_MODEL: str | None = None
    LLM_BASE_URL: AnyUrl | None = None
    LLM_API_KEY: SecretStr | None = None

    # Storage
    DATABASE_URL: AnyUrl | None = None  # e.g., postgres://...

    # Queue
    REDIS_URL: AnyUrl | None = None

    # Timeouts
    HTTP_TIMEOUT_SECS: int = 30


settings = Settings()
