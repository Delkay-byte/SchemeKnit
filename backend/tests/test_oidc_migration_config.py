"""Migration and production-config tests for the platform-admin OIDC SSO.

- v052 creates the additive ``platform_admin_oidc_links`` table, is idempotent,
  is discovered by the migration runner after v051, and enforces a unique
  ``idp_sub``.
- ``validate_production`` refuses an SSO-enabled production boot without an
  https issuer / client secret / linking key, while desktop mode boots
  regardless (feature default OFF).
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.orm import sessionmaker

from src.config import Settings, get_settings
from src.database import Base, User, generate_id, PlatformAdminOidcLinkDB


class TestV052Migration:

    @pytest.fixture
    def migrated_db(self, tmp_path, monkeypatch):
        engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
        # v052 references users(id); provide it the way real migrations do.
        Base.metadata.create_all(bind=engine, tables=[User.__table__])
        Session = sessionmaker(bind=engine)
        db = Session()
        from src.migrations import v052_platform_admin_oidc_links as migration
        # The migration module inspects the global DB engine; point it at the
        # test engine (the migration runner does the equivalent injection).
        monkeypatch.setattr(migration, "engine", engine)
        yield db, engine, migration
        db.close()
        engine.dispose()

    def test_creates_link_table(self, migrated_db):
        db, engine, migration = migrated_db
        migration.up(db)
        inspector = sa_inspect(engine)
        assert inspector.has_table("platform_admin_oidc_links")
        cols = {c["name"] for c in inspector.get_columns(
            "platform_admin_oidc_links")}
        assert {"id", "user_id", "issuer", "idp_sub", "linked_at",
                "linked_via", "created_by"} <= cols

    def test_idempotent(self, migrated_db):
        db, engine, migration = migrated_db
        migration.up(db)
        migration.up(db)  # second run must not raise or duplicate
        assert sa_inspect(engine).has_table("platform_admin_oidc_links")

    def test_unique_idp_sub(self, migrated_db):
        db, engine, migration = migrated_db
        migration.up(db)
        user = User(id=generate_id(), email="a@b.c", full_name="A",
                    hashed_password="x", role="platform_admin", is_active=True)
        db.add(user)
        db.commit()
        db.add(PlatformAdminOidcLinkDB(
            id=generate_id(), user_id=user.id, issuer="iss", idp_sub="sub-1"))
        db.commit()
        db.add(PlatformAdminOidcLinkDB(
            id=generate_id(), user_id=user.id, issuer="iss", idp_sub="sub-1"))
        with pytest.raises(Exception):
            db.commit()
        db.rollback()

    def test_runner_discovers_v052_after_v051(self):
        from src.migration_runner import run_all_migrations  # import sanity
        migration_dir = Path(__file__).parent.parent / "src" / "migrations"
        versions = sorted(p.stem for p in migration_dir.glob("v*.py"))
        assert "v052_platform_admin_oidc_links" in versions
        assert versions.index("v052_platform_admin_oidc_links") \
            == versions.index("v051_weekly_class_plans") + 1


class TestProductionValidation:

    def _settings(self, **overrides):
        base = dict(
            # Force the production profile: the developer .env sets DEBUG=true,
            # which would short-circuit validate_production entirely.
            DEBUG=False,
            RATE_LIMIT_BACKEND="db",
            SECRET_KEY="real-secret",
            JWT_SECRET_KEY="real-jwt-secret",
            DATABASE_URL="postgresql://u:p@db/x",
            RESEND_API_KEY="re_x",
            EMAIL_FROM="no-reply@schemeknit.com",
            PUBLIC_WEB_URL="https://app.schemeknit.com",
            API_BASE_URL="https://api.schemeknit.com",
            CORS_ORIGINS=["https://app.schemeknit.com"],
            TURNSTILE_ENABLED=False,
            STORAGE_BACKEND="local",
        )
        base.update(overrides)
        return Settings(**base)

    def test_oidc_enabled_requires_https_issuer(self):
        s = self._settings(
            PLATFORM_OIDC_ENABLED=True,
            PLATFORM_OIDC_ISSUER="http://localhost:9000/application/o/schemeknit/",
            PLATFORM_OIDC_CLIENT_SECRET="s",
            PLATFORM_OIDC_LINKING_API_KEY="k",
        )
        with pytest.raises(RuntimeError) as exc:
            s.validate_production()
        assert "PLATFORM_OIDC_ISSUER" in str(exc.value)

    def test_oidc_enabled_requires_client_secret(self):
        s = self._settings(
            PLATFORM_OIDC_ENABLED=True,
            PLATFORM_OIDC_ISSUER="https://idp.example.com/application/o/schemeknit/",
            PLATFORM_OIDC_CLIENT_SECRET="",
            PLATFORM_OIDC_LINKING_API_KEY="k",
        )
        with pytest.raises(RuntimeError) as exc:
            s.validate_production()
        assert "PLATFORM_OIDC_CLIENT_SECRET" in str(exc.value)

    def test_oidc_enabled_requires_linking_key(self):
        s = self._settings(
            PLATFORM_OIDC_ENABLED=True,
            PLATFORM_OIDC_ISSUER="https://idp.example.com/application/o/schemeknit/",
            PLATFORM_OIDC_CLIENT_SECRET="s",
            PLATFORM_OIDC_LINKING_API_KEY="",
        )
        with pytest.raises(RuntimeError) as exc:
            s.validate_production()
        assert "PLATFORM_OIDC_LINKING_API_KEY" in str(exc.value)

    def test_oidc_properly_configured_adds_no_problems(self):
        s = self._settings(
            PLATFORM_OIDC_ENABLED=True,
            PLATFORM_OIDC_ISSUER="https://idp.example.com/application/o/schemeknit/",
            PLATFORM_OIDC_CLIENT_SECRET="s",
            PLATFORM_OIDC_LINKING_API_KEY="k",
        )
        # A fully valid production config must boot; if anything fails, the
        # failure must NOT be about the OIDC settings.
        try:
            s.validate_production()
        except RuntimeError as exc:
            assert "PLATFORM_OIDC" not in str(exc.value)

    def test_oidc_disabled_needs_nothing(self):
        s = self._settings()  # PLATFORM_OIDC_ENABLED default False
        try:
            s.validate_production()
        except RuntimeError as exc:
            assert "PLATFORM_OIDC" not in str(exc.value)

    def test_desktop_mode_boots_with_feature_off_default(self):
        s = Settings(
            SECRET_KEY="real-secret",
            JWT_SECRET_KEY="real-jwt-secret",
            DESKTOP_MODE=True,
        )
        assert s.PLATFORM_OIDC_ENABLED is False
        s.validate_production()  # must not raise
