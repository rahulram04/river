"""Server-side settings. No client-facing environment variables contain Jira secrets."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./river-dev.db"
    jira_mode: str = "mock"
    jira_base_url: str = "https://rahulrram04.atlassian.net"
    jira_email: str = ""
    jira_api_token: str = ""
    jira_allowed_project_keys: str = "KAN"
    web_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    initial_play_credits: int = Field(default=1000, ge=1, le=100000)
    session_ttl_hours: int = Field(default=168, ge=1, le=720)

    @model_validator(mode="after")
    def validate_jira(self):
        if self.jira_mode not in {"mock", "live"}:
            raise ValueError("JIRA_MODE must be mock or live")
        if self.jira_mode == "live" and (not self.jira_email or not self.jira_api_token):
            raise ValueError("Live Jira requires JIRA_EMAIL and JIRA_API_TOKEN")
        if not self.jira_base_url.startswith("https://"):
            raise ValueError("JIRA_BASE_URL must be an HTTPS URL")
        return self

    @property
    def allowed_projects(self) -> set[str]:
        return {k.strip().upper() for k in self.jira_allowed_project_keys.split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
