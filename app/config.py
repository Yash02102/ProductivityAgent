from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, AnyUrl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)


    # App
    APP_ENV: str = "dev" # dev|staging|prod
    APP_DEBUG: bool = False
    APP_API_KEY: SecretStr | None = None # for protecting the API


    # GitLab
    GITLAB_URL: AnyUrl
    GITLAB_TOKEN: SecretStr


    # Jira
    JIRA_INSTANCE_URL: AnyUrl
    JIRA_API_TOKEN: SecretStr
    JIRA_USERNAME: str
    JIRA_IS_CLOUD: bool = True

    #code analysis
    cs_code_analyzer: str | None = None

    # LLM (optional)
    LLM_MODEL: str | None = None
    LLM_BASE_URL: AnyUrl | None = None
    LLM_API_KEY: SecretStr | None = None


    # Storage
    DATABASE_URL: AnyUrl | None = None # e.g., postgres://...


    # Queue
    REDIS_URL: AnyUrl | None = None


    # Timeouts
    HTTP_TIMEOUT_SECS: int = 30


settings = Settings()