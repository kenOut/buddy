from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Buddy Onboarding API"
    api_v1_prefix: str = "/api/v1"

    # Defaults to a local SQLite file so the backend runs with zero setup.
    # Swap for a Supabase/Postgres connection string (asyncpg driver) in .env
    # once database/schema.sql has been applied to that project.
    database_url: str = "sqlite+aiosqlite:///./buddy.db"

    cors_origins: str = "http://localhost:3000"
    demo_employee_email: str = "michael.mensah@buddy.dev"

    # Manager Portal login — a single shared password (not per-manager
    # accounts), matching this project's existing no-session-auth design
    # for everything else. Override both in production; the defaults
    # exist only so local dev works with zero setup.
    admin_password: str = "kowri-admin"
    admin_session_secret: str = "dev-only-insecure-secret-change-me"
    admin_session_ttl_seconds: int = 60 * 60 * 12  # 12 hours

    # Phase 3A — Adaptive Capability Intelligence. "mock" needs no
    # credentials and is what local dev/tests run against by default, so
    # the app stays fully runnable with zero external AI setup. A real
    # provider can be added later by implementing the AIProvider protocol
    # (services/ai_provider.py) and switching this value — nothing else
    # in the call chain needs to change.
    ai_provider: str = "mock"
    ai_api_key: str | None = None
    ai_prompt_version: str = "v1"
    ai_evaluation_version: str = "v1"

    # Phase 8C — Workspace Access Automation. Same reasoning as
    # ai_provider above: "mock" needs no credentials, so the app stays
    # fully runnable with zero external setup. A real Google Drive
    # provider can be added later by implementing the WorkspaceProvider
    # protocol (services/workspace_provider.py) and switching this value.
    workspace_provider: str = "mock"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
