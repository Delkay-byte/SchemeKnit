"""
SchemeKnit Production Configuration

Environment-based settings. All secrets come from .env.
"""

import os
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv
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
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    MINIMAX_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    OPENCODE_ZEN_API_KEY: str = ""
    OPENCODE_ZEN_MODEL: str = "nemotron-3-ultra-free"
    OPENCODE_ZEN_BASE_URL: str = "https://opencode.ai/zen/v1"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Maintenance Mode
    MAINTENANCE_MODE: bool = False
    MAINTENANCE_MESSAGE: str = "SchemeKnit is currently undergoing maintenance. We'll be back shortly."
    MAINTENANCE_ESTIMATED_RESTORE: str = ""  # e.g. "2 hours" or "30 minutes"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

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
