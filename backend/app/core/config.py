from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# P5 — Production Security Hardening. Every *_secret/*_password/
# *_url field below that is security-critical now follows one shared
# pattern (see `_fail_closed_in_production`): the field itself defaults
# to `None` ("not configured"), and the validator decides what that
# means depending on `environment` — filled in with the matching
# well-known dev-only value here outside production (zero-setup local
# dev/test, unchanged from every earlier phase), or a hard startup
# failure in production. These dev-only values are never used, and
# never even referenced, in production.
_DEV_ADMIN_PASSWORD = "kowri-admin"
_DEV_ADMIN_SESSION_SECRET = "dev-only-insecure-secret-change-me"
_DEV_EMPLOYEE_SESSION_SECRET = "dev-only-insecure-employee-session-secret-change-me"
_DEV_INVITATION_TOKEN_SECRET = "dev-only-insecure-invitation-secret-change-me"
_DEV_PROVISIONING_API_KEY = "dev-only-insecure-provisioning-key-change-me"
_DEV_APP_BASE_URL = "http://localhost:3000"
_DEV_CORS_ORIGINS = "http://localhost:3000"

# field name -> (dev-only default, environment variable name for the
# error message). One shared validator below walks this table rather
# than repeating six near-identical `model_validator`s (P2.1/P3 each
# introduced one of these individually; P5 consolidates them — same
# behavior, one place to read it).
_PRODUCTION_REQUIRED_FIELDS: dict[str, tuple[str, str]] = {
    "admin_password": (_DEV_ADMIN_PASSWORD, "ADMIN_PASSWORD"),
    "admin_session_secret": (_DEV_ADMIN_SESSION_SECRET, "ADMIN_SESSION_SECRET"),
    "employee_session_secret": (_DEV_EMPLOYEE_SESSION_SECRET, "EMPLOYEE_SESSION_SECRET"),
    "invitation_token_secret": (_DEV_INVITATION_TOKEN_SECRET, "INVITATION_TOKEN_SECRET"),
    "provisioning_api_key": (_DEV_PROVISIONING_API_KEY, "PROVISIONING_API_KEY"),
    "app_base_url": (_DEV_APP_BASE_URL, "APP_BASE_URL"),
    "cors_origins": (_DEV_CORS_ORIGINS, "CORS_ORIGINS"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Buddy Onboarding API"
    api_v1_prefix: str = "/api/v1"

    # P2.1 — Provisioning Security Hardening. Governs every fail-closed
    # check below; nothing else in the app branches on this besides
    # is_sqlite_database's own production/demo-seed distinctions.
    # Set ENVIRONMENT=production in a real deployment.
    environment: str = "development"

    # Defaults to a local SQLite file so the backend runs with zero setup.
    # Swap for a Supabase/Postgres connection string (asyncpg driver) in .env
    # once database/schema.sql has been applied to that project.
    database_url: str = "sqlite+aiosqlite:///./buddy.db"

    # P5 — Production Security Hardening. `None` -> filled in with the
    # existing local dev origin outside production; required (fail
    # closed) in production — see _fail_closed_in_production. A
    # production deployment must name its real frontend origin(s)
    # explicitly; it must never fall back to a wildcard (this app sends
    # allow_credentials=True for cookie-based auth, and
    # `allow_origins=["*"]` together with credentials is both browser-
    # rejected and a real security antipattern where it isn't).
    cors_origins: str | None = None

    demo_employee_email: str = "michael.mensah@buddy.dev"

    # P5 — Production Security Hardening. Optional, comma-separated
    # list of Host header values this app will accept (wired to
    # Starlette's TrustedHostMiddleware in main.py). Defaults to "*"
    # (accept any Host) rather than failing closed like the secrets
    # above: unlike a leaked secret, an unset value here is not itself
    # a silent vulnerability — many deployments already terminate TLS
    # and validate the Host header at a reverse proxy/load balancer in
    # front of this app, and forcing an application-level allowlist in
    # that case would be redundant, not protective, and could break a
    # deployment this project has no visibility into. Set explicitly
    # (e.g. "buddy.kowri.example") when this app is reachable directly.
    trusted_hosts: str = "*"

    # P5 — Production Security Hardening. A blunt, deliberately simple
    # backstop against obviously-abusive multi-megabyte request bodies
    # reaching application/service logic at all (Section 14) — not a
    # replacement for real per-field validation, which Pydantic already
    # provides per-schema. 2MB comfortably fits the largest legitimate
    # payload this app sends (quest/mission freeform text + JSON
    # evidence), with real headroom.
    max_request_body_bytes: int = 2 * 1024 * 1024

    # P5 — Production Security Hardening. `None` means "use the
    # sensible per-environment default" (enabled outside production,
    # disabled in production) — set explicitly (true/false) to override
    # either way. See main.py for how this drives docs_url/redoc_url/
    # openapi_url.
    enable_api_docs: bool | None = None

    # Manager Portal login — a single shared password (not per-manager
    # accounts), matching this project's existing no-session-auth design
    # for everything else.
    admin_password: str | None = None
    admin_session_secret: str | None = None
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

    # P1 — Identity & Invitation Foundation. Two independent secrets, kept
    # distinct from admin_session_secret above and from each other: the
    # invitation secret keys the HMAC that hashes a raw invitation token
    # at rest (see invitation_service._hash_token), the employee-session
    # secret signs the cookie issued after a successful exchange (see
    # core/employee_auth.py) — a leak of any one of the three secrets
    # never implicates the other two.
    invitation_token_secret: str | None = None
    invitation_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days to accept an invitation
    employee_session_secret: str | None = None
    employee_session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # P2 — Provisioning Boundary. The service-to-service credential for
    # POST /provisioning/employees — a distinct trust boundary from both
    # admin_password (a human manager, via a signed cookie) and the
    # employee session secrets above (an individual employee, also via a
    # signed cookie).
    provisioning_api_key: str | None = None

    # P3 — Email Provider Foundation. "mock" needs no credentials and is
    # what local dev/tests run against by default, so the app stays
    # fully runnable with zero external email setup — same reasoning as
    # ai_provider/workspace_provider above. Never silently falls back to
    # "mock" if something else is configured but not implemented; see
    # email_provider.get_email_provider's own explicit failure instead.
    email_provider: str = "mock"

    # P3.1 — Real Gmail SMTP Welcome Email Delivery. Only read/required
    # when email_provider == "smtp" (see _require_smtp_config_when_
    # selected below) — every field stays optional at the type level so
    # "mock" (the default, every dev/test process) never needs any of
    # this configured. smtp_port defaults to 587 (STARTTLS) since that's
    # correct for Gmail SMTP and virtually every other real provider;
    # the other four have no safe default (there is no "dev-only insecure
    # SMTP credential" the way there is for this app's own session
    # secrets — a wrong SMTP credential just fails at send time, not a
    # security hole, so there's nothing to protect by inventing one).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    email_from_name: str = "Heimdall"

    # The public base URL the welcome email's "Meet Heimdall" CTA is
    # built against (`{app_base_url}/onboarding/invite/{token}`).
    app_base_url: str | None = None

    @model_validator(mode="after")
    def _fail_closed_in_production(self) -> "Settings":
        """P5 — Production Security Hardening. Consolidates what P2.1
        and P3 each introduced separately (one validator per secret)
        into a single check over every security-critical field in
        `_PRODUCTION_REQUIRED_FIELDS`: a `None` value is filled in with
        the matching well-known dev-only default outside production
        (unchanged zero-setup local dev/test behavior), or collected
        into a single, loud startup failure in production — one
        `ValueError` naming every missing environment variable, never
        any configured value, so an operator sees exactly what to set
        without any secret ever appearing in the error itself.

        Raised at Settings construction (app startup, and every
        `get_settings()` call before anything else runs) rather than
        deep inside whichever request handler first needed the field —
        a misconfigured production deployment must fail to start, not
        serve traffic first and 401 unpredictably later.
        """
        production = self.environment == "production"
        missing_env_vars: list[str] = []
        for field, (dev_value, env_var_name) in _PRODUCTION_REQUIRED_FIELDS.items():
            if getattr(self, field) is None:
                if production:
                    missing_env_vars.append(env_var_name)
                else:
                    setattr(self, field, dev_value)
        if missing_env_vars:
            raise ValueError(
                "Missing required production configuration: "
                + ", ".join(missing_env_vars)
                + ". Set these in the environment before starting in production."
            )
        return self

    @model_validator(mode="after")
    def _require_smtp_config_when_selected(self) -> "Settings":
        """P3.1 — Real Gmail SMTP Welcome Email Delivery. Unlike
        `_fail_closed_in_production` above, this fires in EVERY
        environment, not just production — choosing EMAIL_PROVIDER=smtp
        always means "I intend to really send email," so there is no
        "dev-safe default" to silently fall back to; doing so would mean
        the app reports `email_sent=true` while nothing was actually
        sent, exactly the false-positive this phase's brief calls out as
        dangerous. EMAIL_PROVIDER stays "mock" by default (never smtp),
        so this never fires for a process that hasn't explicitly opted
        in.
        """
        if self.email_provider == "smtp":
            missing = [
                name
                for name, value in (
                    ("SMTP_HOST", self.smtp_host),
                    ("SMTP_USERNAME", self.smtp_username),
                    ("SMTP_PASSWORD", self.smtp_password),
                    ("EMAIL_FROM", self.email_from),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "EMAIL_PROVIDER=smtp requires: " + ", ".join(missing) + ". Set these in the environment."
                )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in (self.cors_origins or "").split(",") if origin.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def api_docs_enabled(self) -> bool:
        if self.enable_api_docs is not None:
            return self.enable_api_docs
        return self.environment != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
