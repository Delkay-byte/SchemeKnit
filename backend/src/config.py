"""
SchemeKnit Production Configuration

Environment-based settings. All secrets come from .env.
"""

import os
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

# Export backend/.env into os.environ so provider modules that read
# os.environ directly (ai_provider) see the same secrets as Settings.
# Real environment variables always win over .env file values.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.is_file():
    load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "SchemeKnit"
    APP_VERSION: str = "1.0.5"
    DEBUG: bool = False
    # Local desktop evaluation build. Opt-in via DESKTOP_MODE=1, set only by
    # the Electron host. A desktop build is *by design* single-user, bound to
    # 127.0.0.1, SQLite-backed, locally stored, and has no Resend/AI cloud
    # dependency. This flag relaxes ONLY the cloud-infrastructure production
    # checks (Postgres/Resend/public URLs/localhost CORS); the secret and
    # entitlement checks below still apply. Public web deploys leave it unset.
    DESKTOP_MODE: bool = False
    # Preview mode for temporary public evaluation builds. Relaxes the
    # EMAIL_FROM domain check (allows resend.dev test sender) while keeping
    # all other production checks active. Set SCHEMEKNIT_PREVIEW=true on
    # the Render backend to enable.
    PREVIEW_MODE: bool = False
    SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION"
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

    # Database
    DATABASE_URL: str = "sqlite:///./teachflow.db"
    # Separate test database — tests must NEVER touch the production DB.
    TEST_DATABASE_URL: str = "sqlite:///./test_teachflow.db"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Generation liveness / crash recovery.
    # A non-terminal job is reclaimed only when its last activity - the
    # heartbeat written by the owning worker, else created_at for legacy or
    # never-started jobs - is STRICTLY older than this many minutes. The
    # default (60) is deliberately conservative for normal runs, which finish
    # in seconds/minutes. Units: integer minutes.
    GENERATION_STALE_MINUTES: int = 60
    # How often a running generation refreshes heartbeat_at. Must be shorter
    # than the stale window so a healthy worker always proves liveness before
    # another request could reclaim it. Units: integer seconds.
    GENERATION_HEARTBEAT_SECONDS: int = 30

    # Public URLs (production: no localhost)
    PUBLIC_WEB_URL: str = "http://localhost:3000"
    API_BASE_URL: str = "http://localhost:8000"

    # CORS — comma-separated list in env, e.g.
    # CORS_ALLOWED_ORIGINS=https://app.schemeknit.com,https://schemeknit.com
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:18235"]

    # JWT Authentication
    JWT_SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Platform Admin Bootstrap
    # One-time secret required to create the FIRST platform admin via
    # /setup/platform-admin. Empty = bootstrap disabled (use the CLI tool).
    # NEVER commit a real value; set it via environment or .env.
    PLATFORM_ADMIN_BOOTSTRAP_SECRET: str = ""

    # Password reset token lifetime (minutes)
    PASSWORD_RESET_TOKEN_TTL_MINUTES: int = 30

    # File Storage
    # STORAGE_BACKEND=local (default) or s3 for S3-compatible object storage.
    UPLOAD_DIR: str = "uploads"
    EXPORT_DIR: str = "exports"
    TEMP_DIR: str = "temp"
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = [".docx", ".pdf"]

    # Object storage (S3-compatible: AWS S3, MinIO, Cloudflare R2, B2, …)
    # Only used when STORAGE_BACKEND=s3. See src/storage.py.
    STORAGE_BACKEND: str = "local"
    S3_ENDPOINT: str = ""
    S3_REGION: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""

    # Transactional email (Resend)
    # Server-side ONLY. NEVER expose RESEND_API_KEY to browser code
    # (do NOT use NEXT_PUBLIC_RESEND_API_KEY).
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""
    EMAIL_REPLY_TO: str = ""

    # AI Providers — secrets and model IDs come from the environment only.
    # AI_MODE may be OFF/BASIC/ENHANCED (deterministic fallback) or a named
    # provider: gemini | groq | openai | ollama | opencode-zen | minimax.
    AI_MODE: str = "OFF"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    # DeepSeek is the verified Zeli engine (see ZELI_* below). Server-side only.
    DEEPSEEK_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    MINIMAX_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    OPENCODE_ZEN_API_KEY: str = ""
    OPENCODE_ZEN_MODEL: str = "nemotron-3-ultra-free"
    OPENCODE_ZEN_BASE_URL: str = "https://opencode.ai/zen/v1"

    # ── Generate with Zeli (whole-lesson generation method) ───────────────
    # Zeli's verified engine is DeepSeek (OpenAI-compatible chat completions).
    # Every ZELI_* value is OPTIONAL: when unset, Zeli uses the built-in
    # DeepSeek endpoint/model and DEEPSEEK_API_KEY. ZELI_API_KEY, when set,
    # takes precedence over DEEPSEEK_API_KEY. Selecting ZELI_PROVIDER=groq
    # falls back to GROQ_MODEL / GROQ_BASE_URL / GROQ_API_KEY instead, so the
    # previous integration keeps working without a second credential system.
    # Secrets are read here and in the provider module only — never sent to
    # the browser.
    #
    # ZELI_ENABLED=False disables the method without affecting Standard
    # generation. ZELI_PROVIDER must be one of the supported provider keys.
    # The tuning values are consumed by ``DeepSeekProvider`` (and by
    # ``zeli_generation.get_zeli_provider``); see docs/ZELI_ENVIRONMENT.md.
    ZELI_ENABLED: bool = True
    ZELI_PROVIDER: str = "deepseek"
    ZELI_MODEL: str = ""
    ZELI_BASE_URL: str = ""
    ZELI_API_KEY: str = ""
    #: Sampling temperature. Omitted from the request when the selected model
    #: does not support it (reasoning/thinking mode).
    ZELI_TEMPERATURE: float = 0.3
    #: Maps to the API's ``max_tokens`` field (completion budget).
    ZELI_MAX_TOKENS: int = 2000
    #: "enabled" | "disabled" | "auto" (auto = omit the parameter).
    ZELI_THINKING_MODE: str = "disabled"
    #: HTTP connect/read timeouts (seconds) enforced by the requests client.
    ZELI_CONNECT_TIMEOUT_SECONDS: float = 10.0
    ZELI_READ_TIMEOUT_SECONDS: float = 90.0
    #: Bounded retries for transient failures (429 / 5xx / network only).
    ZELI_MAX_RETRIES: int = 2

    # Paystack (payments) — optional; absent keys disable new payment initiation.
    # Server-side secret only; never expose PAYSTACK_SECRET_KEY to the browser.
    # PAYSTACK_MODE must match the key environment: "test" for sk_test_,
    # "live" for sk_live_. Live keys are refused outside live mode, so a
    # development machine cannot accidentally start a real-money payment.
    PAYSTACK_ENABLED: bool = True
    PAYSTACK_MODE: str = "test"
    PAYSTACK_PUBLIC_KEY: str = ""
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_CURRENCY: str = "GHS"
    # Compatibility: the owner's private environment uses the frontend-style
    # name for the public key. Accepted here so the backend can boot; it is
    # never returned by an API.
    NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Maintenance Mode
    MAINTENANCE_MODE: bool = False
    MAINTENANCE_MESSAGE: str = "SchemeKnit is currently undergoing maintenance. We'll be back shortly."
    MAINTENANCE_ESTIMATED_RESTORE: str = ""  # e.g. "2 hours" or "30 minutes"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("GENERATION_STALE_MINUTES")
    @classmethod
    def _validate_stale_minutes(cls, value: int) -> int:
        value = int(value)
        if not 1 <= value <= 1440:
            raise ValueError(
                "GENERATION_STALE_MINUTES must be between 1 and 1440 minutes"
            )
        return value

    @field_validator("GENERATION_HEARTBEAT_SECONDS")
    @classmethod
    def _validate_heartbeat_seconds(cls, value: int) -> int:
        value = int(value)
        if not 5 <= value <= 3600:
            raise ValueError(
                "GENERATION_HEARTBEAT_SECONDS must be between 5 and 3600 seconds"
            )
        return value

    @model_validator(mode="after")
    def _validate_heartbeat_window(self):
        if self.GENERATION_HEARTBEAT_SECONDS >= self.GENERATION_STALE_MINUTES * 60:
            raise ValueError(
                "GENERATION_HEARTBEAT_SECONDS must be shorter than "
                "GENERATION_STALE_MINUTES, otherwise a healthy long run can "
                "be reclaimed before its next heartbeat"
            )
        return self

    @field_validator("ZELI_PROVIDER")
    @classmethod
    def _validate_zeli_provider(cls, value: str) -> str:
        # Imported lazily so settings can load before the engine package.
        from .engines.ai_provider import NAMED_PROVIDERS

        provider = (value or "deepseek").strip().lower()
        if provider not in NAMED_PROVIDERS:
            raise ValueError(
                "ZELI_PROVIDER must be one of: "
                + ", ".join(sorted(NAMED_PROVIDERS))
            )
        return provider

    @field_validator("ZELI_MODEL", "ZELI_BASE_URL", "ZELI_API_KEY", "DEEPSEEK_API_KEY")
    @classmethod
    def _validate_zeli_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("ZELI_TEMPERATURE")
    @classmethod
    def _validate_zeli_temperature(cls, value: float) -> float:
        value = float(value)
        if not 0.0 <= value <= 2.0:
            raise ValueError("ZELI_TEMPERATURE must be between 0.0 and 2.0")
        return value

    @field_validator("ZELI_MAX_TOKENS")
    @classmethod
    def _validate_zeli_max_tokens(cls, value: int) -> int:
        value = int(value)
        if not 1 <= value <= 8192:
            raise ValueError("ZELI_MAX_TOKENS must be between 1 and 8192")
        return value

    @field_validator("ZELI_THINKING_MODE")
    @classmethod
    def _validate_zeli_thinking_mode(cls, value: str) -> str:
        mode = (value or "auto").strip().lower()
        if mode not in ("enabled", "disabled", "auto"):
            raise ValueError(
                "ZELI_THINKING_MODE must be enabled, disabled or auto"
            )
        return mode

    @field_validator("ZELI_CONNECT_TIMEOUT_SECONDS")
    @classmethod
    def _validate_zeli_connect_timeout(cls, value: float) -> float:
        value = float(value)
        if not 1.0 <= value <= 60.0:
            raise ValueError(
                "ZELI_CONNECT_TIMEOUT_SECONDS must be between 1 and 60 seconds"
            )
        return value

    @field_validator("ZELI_READ_TIMEOUT_SECONDS")
    @classmethod
    def _validate_zeli_read_timeout(cls, value: float) -> float:
        value = float(value)
        if not 1.0 <= value <= 600.0:
            raise ValueError(
                "ZELI_READ_TIMEOUT_SECONDS must be between 1 and 600 seconds"
            )
        return value

    @field_validator("ZELI_MAX_RETRIES")
    @classmethod
    def _validate_zeli_max_retries(cls, value: int) -> int:
        value = int(value)
        if not 0 <= value <= 5:
            raise ValueError("ZELI_MAX_RETRIES must be between 0 and 5")
        return value

    def validate_production(self):
        """Fail fast when mandatory production secrets are missing/default.

        Development (DEBUG=true) keeps working with dev defaults; any
        non-debug boot requires real secrets. Called at application startup.

        DESKTOP_MODE is the local evaluation profile: single-user, bound to
        127.0.0.1, SQLite + local storage by design. It still enforces strong
        secrets but skips the cloud-infrastructure requirements (Postgres,
        Resend, public URLs, localhost CORS) that do not apply locally.
        """
        if self.DEBUG:
            return

        problems: list[str] = []

        # Core secrets — required in EVERY non-debug profile, including desktop.
        # The Electron host generates random per-installation secrets, so a
        # default value here is always a real misconfiguration.
        for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
            val = getattr(self, key, "")
            if not val or val == "CHANGE-ME-IN-PRODUCTION":
                problems.append(key)

        if self.DESKTOP_MODE:
            # Local evaluation build: SQLite and local storage are correct,
            # email/password-reset runs through the local bootstrap flow, and
            # the frontend is served from 127.0.0.1 so localhost CORS is
            # required, not forbidden.
            if problems:
                raise RuntimeError(
                    "Refusing to start with missing secrets (desktop mode):\n  - "
                    + "\n  - ".join(problems)
                    + "\nThe desktop host must supply strong per-installation secrets."
                )
            return

        # Database must not be the SQLite dev default in production
        if not self.DATABASE_URL or self.DATABASE_URL.startswith("sqlite"):
            problems.append(
                "DATABASE_URL (production must use PostgreSQL, not SQLite)"
            )

        # Public URLs must not contain localhost in production
        for key in ("PUBLIC_WEB_URL", "API_BASE_URL"):
            val = getattr(self, key, "")
            if not val or "localhost" in val or "127.0.0.1" in val:
                problems.append(f"{key} (must be a real production URL)")

        # CORS must not allow localhost in production
        for origin in self.CORS_ORIGINS:
            if "localhost" in origin or "127.0.0.1" in origin:
                problems.append(
                    f"CORS_ORIGINS contains dev origin '{origin}' "
                    "(remove localhost in production)"
                )

        # Email — required in production (password reset depends on it)
        if not self.RESEND_API_KEY:
            problems.append("RESEND_API_KEY (required for password reset email)")
        if not self.EMAIL_FROM:
            problems.append("EMAIL_FROM (required for transactional email)")
        elif "localhost" in self.EMAIL_FROM:
            problems.append(
                "EMAIL_FROM (must use a real email address, not localhost)"
            )
        elif (
            "resend.dev" in self.EMAIL_FROM
            and not self.PREVIEW_MODE
            and not self.DEBUG
        ):
            problems.append(
                "EMAIL_FROM (must use a verified production domain, "
                "not resend.dev — set SCHEMEKNIT_PREVIEW=true for test mode)"
            )

        # Paystack — when enabled in production, it must be explicitly live.
        # A test key here would take test-mode payments in production, so that
        # is a hard boot failure rather than a silent downgrade.
        if self.PAYSTACK_ENABLED:
            mode = (self.PAYSTACK_MODE or "").strip().lower()
            secret = (self.PAYSTACK_SECRET_KEY or "").strip()
            if secret:
                if mode != "live":
                    problems.append(
                        "PAYSTACK_MODE (must be 'live' when a live Paystack "
                        "secret is configured in production)"
                    )
                if not secret.startswith("sk_live_"):
                    problems.append(
                        "PAYSTACK_SECRET_KEY (production must use sk_live_, "
                        "not a test key)"
                    )
            if (self.PAYSTACK_CURRENCY or "").strip().upper() != "GHS":
                problems.append("PAYSTACK_CURRENCY (must be GHS)")
            for key in ("PAYSTACK_PUBLIC_KEY", "NEXT_PUBLIC_PAYSTACK_PUBLIC_KEY"):
                value = (getattr(self, key, "") or "").strip()
                if value.startswith("sk_"):
                    problems.append(
                        f"{key} (must never contain a Paystack secret key)"
                    )

        # Object storage — required in production
        if self.STORAGE_BACKEND == "s3":
            for key in ("S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
                if not getattr(self, key, ""):
                    problems.append(f"{key} (required when STORAGE_BACKEND=s3)")
        elif self.STORAGE_BACKEND != "local":
            problems.append(
                f"STORAGE_BACKEND='{self.STORAGE_BACKEND}' is invalid "
                "(must be 'local' or 's3')"
            )

        if problems:
            raise RuntimeError(
                "Refusing to start with missing production configuration:\n  - "
                + "\n  - ".join(problems)
                + "\nSet them via environment variables (see .env.example)."
            )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
