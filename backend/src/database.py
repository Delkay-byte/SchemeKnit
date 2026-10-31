"""
SchemeKnit Database Layer

SQLAlchemy models for persistent storage.
SQLite for development, PostgreSQL for production.
"""

from datetime import datetime, date
from typing import Optional
import uuid

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SAEnum, Index, UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from .config import get_settings

settings = get_settings()


def normalize_database_url(url: str) -> str:
    """Normalize standard PostgreSQL URLs to the installed Psycopg 3 driver.

    SQLAlchemy's bare ``postgresql://`` and ``postgres://`` schemes default to
    the psycopg2 DBAPI. This project installs ``psycopg[binary]`` (Psycopg 3),
    so those schemes must select ``postgresql+psycopg`` before create_engine.

    The value is changed only at the scheme prefix; credentials, host, port,
    database, path and every query parameter (including ``sslmode`` and
    ``channel_binding``) are preserved byte-for-byte. The URL is never logged.
    """
    if not url or not str(url).strip():
        raise ValueError("DATABASE_URL is not configured.")
    value = str(url).strip()
    lower = value.lower()
    if lower.startswith("postgresql+psycopg://"):
        return value
    if lower.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    if lower.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    # SQLite and any other explicitly selected SQLAlchemy driver are unchanged.
    return value


_database_url = normalize_database_url(settings.DATABASE_URL)
_is_sqlite = _database_url.startswith("sqlite")
engine = create_engine(
    _database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    echo=settings.DEBUG,
    # Neon/Render can close idle pooled PostgreSQL connections. Pre-ping
    # replaces a dead connection before use instead of surfacing a 500.
    pool_pre_ping=not _is_sqlite,
    pool_recycle=300 if not _is_sqlite else -1,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        db.close()


def generate_id() -> str:
    return str(uuid.uuid4())


# ── User Model ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_id)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    school_name = Column(String, default="")
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    role = Column(String, default="teacher")  # platform_admin, school_admin, teacher
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)
    subscription_type = Column(String, nullable=True)  # individual | school | null
    # Session invalidation: bumped on every password change/reset. The JWT
    # carries a `pwv` claim with this value; a mismatch means the token was
    # issued before the password changed and must be rejected.
    password_changed_at = Column(DateTime, default=datetime.utcnow)
    # Privileged-account MFA. The secret is only active when mfa_enabled is
    # true; recovery codes are bcrypt hashes and are single-use.
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String, nullable=True)
    mfa_recovery_codes = Column(JSON, default=list)
    mfa_last_step = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    schemes = relationship("SchemeDB", back_populates="owner")
    generation_jobs = relationship("GenerationJobDB", back_populates="owner")


# ── Scheme of Work ────────────────────────────────────────────────────────────

class SchemeDB(Base):
    __tablename__ = "schemes"

    id = Column(String, primary_key=True, default=generate_id)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)
    filename = Column(String, nullable=False)
    storage_filename = Column(String, nullable=True)
    subject = Column(String, nullable=False)
    class_level = Column(String, nullable=False)
    term = Column(String, default="1")
    academic_year = Column(String, default="2026/2027")
    status = Column(String, default="uploaded")
    upload_date = Column(DateTime, default=datetime.utcnow)
    raw_text = Column(Text, default="")
    validation_issues = Column(JSON, default=list)
    # ── Multi-subject document detection (§4) ────────────────────────────
    # One large document may contain several subjects for the same level. The
    # detected subject sections are stored so the teacher can confirm which one
    # to use without SchemeKnit guessing. `detection_status` is one of
    # "single" | "multiple" | "low_confidence".
    document_title = Column(String, default="")
    detected_subjects = Column(JSON, default=list)
    detection_status = Column(String, default="")
    subject_sections = Column(JSON, default=list)
    #: Per-lesson review drafts keyed by lesson_sequence (or indicator_code).
    #: Saved by the teacher BEFORE generation; applied when lessons are built.
    #: Fields: keywords, other_tlrs, core_competencies, structured_references.
    lesson_review_drafts = Column(JSON, default=dict)
    #: Guided lesson configuration (Phase 2): school name, teacher's name,
    #: class size, reference, lesson duration, period allocation, periods per
    #: week and the days the subject is taught — saved by the teacher AFTER
    #: extraction and BEFORE generation, and re-used by every export of this
    #: plan. JSON document; NULL/empty = not configured (never invented).
    lesson_config = Column(JSON, nullable=True)

    owner = relationship("User", back_populates="schemes")
    weeks = relationship("WeekDB", back_populates="scheme", cascade="all, delete-orphan")


class WeekDB(Base):
    __tablename__ = "weeks"

    id = Column(String, primary_key=True, default=generate_id)
    scheme_id = Column(String, ForeignKey("schemes.id"), nullable=False)
    week_number = Column(Integer, nullable=False)
    week_type = Column(String, default="instruction")
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    #: True when end_date was derived (source document had no week-ending date).
    week_ending_derived = Column(Boolean, default=False, nullable=False)
    strand = Column(String, default="")
    sub_strand = Column(String, default="")
    content_standards = Column(JSON, default=list)
    indicators = Column(JSON, default=list)
    resources = Column(JSON, default=list)
    #: Special-period metadata (PART O/P): the verbatim source label of a
    #: non-instructional period row and its normalized type. Empty for normal
    #: instructional weeks. Existing rows default to empty via migration v026.
    special_period_label = Column(String, default="")
    special_period_type = Column(String, default="")

    scheme = relationship("SchemeDB", back_populates="weeks")

    __table_args__ = (
        Index("ix_weeks_scheme_number", "scheme_id", "week_number"),
    )


# ── Term Configuration ────────────────────────────────────────────────────────

class TermConfigDB(Base):
    __tablename__ = "term_configs"

    id = Column(String, primary_key=True, default=generate_id)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    scheme_id = Column(String, ForeignKey("schemes.id"), nullable=False)
    term_start_date = Column(Date, nullable=False)
    term_end_date = Column(Date, nullable=False)
    lessons_per_week = Column(Integer, default=3)
    lesson_duration_minutes = Column(Integer, default=60)
    #: No default: an unconfigured class size stays NULL and renders blank.
    class_size = Column(Integer, nullable=True)
    teaching_days = Column(JSON, default=lambda: [0, 2, 4])
    holidays = Column(JSON, default=list)
    ai_mode = Column(String, default="OFF")
    template_type = Column(String, default="GES-style")
    include_special_weeks = Column(Boolean, default=False)
    school_name = Column(String, default="")
    teacher_name = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Generation Job ────────────────────────────────────────────────────────────

class GenerationJobDB(Base):
    __tablename__ = "generation_jobs"

    id = Column(String, primary_key=True, default=generate_id)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    scheme_id = Column(String, ForeignKey("schemes.id"), nullable=False)
    status = Column(String, default="pending")
    progress = Column(Integer, default=0)
    total_lessons = Column(Integer, default=0)
    completed_lessons = Column(Integer, default=0)
    failed_lessons = Column(Integer, default=0)
    error_message = Column(Text, default="")
    config_snapshot = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    #: Last proof of life from the worker that owns this job. NULL on legacy
    #: rows and on jobs that never started; reconciliation then falls back to
    #: created_at. Written by the running worker every
    #: GENERATION_HEARTBEAT_SECONDS, so a genuinely long run is not mistaken
    #: for an orphaned one.
    heartbeat_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    owner = relationship("User", back_populates="generation_jobs")
    lesson_plans = relationship("LessonPlanDB", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_jobs_owner_scheme", "owner_id", "scheme_id"),
    )


# ── Export Events (workflow stage 5 persistence) ──────────────────────────────

class ExportEventDB(Base):
    __tablename__ = "export_events"

    id = Column(String, primary_key=True, default=generate_id)
    job_id = Column(String, ForeignKey("generation_jobs.id"), nullable=False)
    scheme_id = Column(String, ForeignKey("schemes.id"), nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    format = Column(String, nullable=False)  # docx | xlsx | zip | pdf
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_exports_owner_scheme", "owner_id", "scheme_id"),
    )


# ── Lesson Plan ───────────────────────────────────────────────────────────────

class LessonPlanDB(Base):
    __tablename__ = "lesson_plans"

    id = Column(String, primary_key=True, default=generate_id)
    job_id = Column(String, ForeignKey("generation_jobs.id"), nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    scheme_id = Column(String, ForeignKey("schemes.id"), nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=True)

    #: Source curriculum week (the scheme week the indicator belongs to).
    week_number = Column(Integer, nullable=False)
    #: Stable identity of the source occurrence the lesson was generated from
    #: (week<source_week>:<position_in_week>:<indicator_code>). Canonical key
    #: for weekly coverage; the timetable never contributes to it. Added by
    #: migration v032 (additive; legacy rows stay NULL/empty).
    source_occurrence_id = Column(String, default="", nullable=True)
    #: Source week-ending date for that curriculum week (authoritative).
    week_ending = Column(Date, nullable=True)
    week_ending_derived = Column(Boolean, default=False, nullable=False)
    #: Actual teaching week the lesson is delivered in. Source-occurrence
    #: semantics: always the source week — nothing carries forward. The column
    #: predates that rule and is kept for rows generated before Priority 1.
    teaching_week = Column(Integer, nullable=True)
    #: Legacy column: only pre-Priority-1 rows can be True.
    carry_forward = Column(Boolean, default=False)
    lesson_sequence = Column(Integer, nullable=False)
    lesson_date = Column(Date, nullable=True)
    lesson_number = Column(Integer, default=1)
    # Timetable slot the teacher configured (e.g. "1st & 2nd"). Never invented:
    # it is carried from the configuration/preferences, or blank.
    period = Column(String, default="")
    class_level = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    #: No default: an unconfigured class size stays NULL and renders blank.
    class_size = Column(Integer, nullable=True)
    duration_minutes = Column(Integer, default=60)
    school_name = Column(String, default="")
    teacher_name = Column(String, default="")

    strand = Column(String, default="")
    sub_strand = Column(String, default="")
    content_standard = Column(String, default="")
    content_standard_code = Column(String, default="")
    indicators = Column(JSON, default=list)
    indicator_codes = Column(JSON, default=list)
    lesson_topic = Column(String, default="")

    previous_knowledge = Column(Text, default="")
    learning_objectives = Column(JSON, default=list)
    # ── WAPEF structured fields (Approved WAPEF Plan; v025) ────────────
    # Teacher-selected curriculum/context selections — never AI-chosen.
    # Optional (empty default) so existing lessons stay valid.
    wapef_deep_hope = Column(Text, default="")
    wapef_storyline = Column(Text, default="")
    wapef_through_lines = Column(JSON, default=list)
    wapef_gods_story = Column(String, default="")
    remarks = Column(Text, default="")
    core_competencies = Column(JSON, default=list)
    #: TLRs from the scheme for this subject + source week (SOURCE provenance).
    source_tlrs = Column(JSON, default=list)
    #: Teacher-added resources for this lesson only (TEACHER provenance).
    other_tlrs = Column(JSON, default=list)
    teaching_learning_resources = Column(JSON, default=list)

    introduction = Column(Text, default="")
    starter_activity = Column(Text, default="")
    main_activities = Column(JSON, default=list)
    learner_activities = Column(JSON, default=list)
    teacher_activities = Column(JSON, default=list)
    assessment = Column(Text, default="")
    # Structured assessment prompts (DoK + marking guidance) and the
    # analytic rubric for this lesson when one is needed (Phase 3). Both are
    # additive JSON columns (v033) — legacy rows stay valid empty.
    assessment_items = Column(JSON, default=list)
    assessment_rubric = Column(JSON, nullable=True, default=None)
    conclusion = Column(Text, default="")
    references = Column(JSON, default=list)
    #: Structured per-lesson references: {type,title,author_publisher,page,notes}.
    structured_references = Column(JSON, default=list)
    keywords = Column(JSON, default=list)
    homework = Column(Text, default="")
    #: Assignment the class completes IN LESSON (guides lesson flow).
    class_assignment = Column(Text, default="")
    #: Assignment set to complete AT HOME (after the lesson).
    home_assignment = Column(Text, default="")
    differentiation = Column(Text, default="")
    essential_questions = Column(JSON, default=list)
    #: Template this lesson was generated under. Persisted per lesson so an
    #: export always re-renders in the same form the teacher approved
    #: (column added by migration v001; wired into the ORM here).
    template_id = Column(String, nullable=True)
    #: Special-period identity carried from the source week (v026 added the
    #: columns to weeks; lessons derived from a special-period allocation
    #: need them too or the review UI shows fake curriculum fields after
    #: save+reload).
    special_period_label = Column(String, default="")
    special_period_type = Column(String, default="")

    status = Column(String, default="generated")
    ai_generated = Column(Boolean, default=False)
    #: Durable AI provenance (v035). Empty for deterministic lessons.
    ai_provider = Column(String, default="")
    ai_model = Column(String, default="")
    generation_method = Column(String, default="standard")
    teacher_edited = Column(Boolean, default=False)
    original_data = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("GenerationJobDB", back_populates="lesson_plans")

    __table_args__ = (
        Index("ix_lesson_plans_job", "job_id"),
        Index("ix_lesson_plans_owner", "owner_id"),
        Index("ix_lesson_plans_scheme", "scheme_id"),
    )


# ── Holiday ───────────────────────────────────────────────────────────────────

class HolidayDB(Base):
    __tablename__ = "holidays"

    id = Column(String, primary_key=True, default=generate_id)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    is_recurring = Column(Boolean, default=False)
    description = Column(Text, default="")

    __table_args__ = (
        Index("ix_holidays_date", "date"),
    )


# ── User Preferences ──────────────────────────────────────────────────────────

class UserPreferencesDB(Base):
    __tablename__ = "user_preferences"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    default_class_level = Column(String, default="Basic 9")
    default_subject = Column(String, default="Science")
    default_lessons_per_week = Column(Integer, default=3)
    default_lesson_duration = Column(Integer, default=60)
    default_template = Column(String, default="GES-style")
    default_school_name = Column(String, default="")
    ai_mode = Column(String, default="OFF")
    # Teacher-level defaults so these are not re-typed on every lesson plan
    # (PART 13). Period is a timetable slot ("1st & 2nd"); the list columns are
    # JSON arrays of strings. All optional and blank by default — never invented.
    default_period = Column(String, default="")
    default_references = Column(JSON, default=list)
    default_tlrs = Column(JSON, default=list)
    default_keywords = Column(JSON, default=list)
    default_core_competencies = Column(JSON, default=list)


# ── Entitlement ───────────────────────────────────────────────────────────────

class EntitlementDB(Base):
    __tablename__ = "entitlements"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    edition = Column(String, default="free")
    features = Column(JSON, default=list)
    max_schemes = Column(Integer, default=5)
    max_lessons_per_scheme = Column(Integer, default=50)
    max_templates = Column(Integer, default=3)
    ai_enabled = Column(Boolean, default=False)
    advanced_ai_enabled = Column(Boolean, default=False)
    cloud_sync = Column(Boolean, default=False)
    template_import = Column(Boolean, default=False)
    content_library = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Individual teacher plan fields (v013)
    subscription_type = Column(String, nullable=True)  # individual | school | null
    generation_limit = Column(Integer, default=0)  # 0 = unlimited
    generations_used = Column(Integer, default=0)
    batch_generation = Column(Boolean, default=False)
    zip_export = Column(Boolean, default=False)
    pdf_export = Column(Boolean, default=True)
    custom_template_limit = Column(Integer, default=3)
    history_limit = Column(Integer, default=10)
    ai_credits = Column(Integer, default=0)  # 0 = unlimited or disabled
    ai_credits_used = Column(Integer, default=0)
    # ── Authoritative plan lifecycle (v028) ────────────────────────────────
    # ``edition`` carries the commercial plan (free | teacher | school); the
    # columns below make the ADMIN-WORKFLOW explicit so a teacher's plan can be
    # activated, expired or REVOKED without deleting the row (and without the
    # frontend being able to influence it — every field is server-written).
    #   status: "active" | "expired" | "revoked"
    #   source: "free" | "admin" | "payment" | "license" | "activation_code"
    status = Column(String, default="active", nullable=False)
    source = Column(String, default="free")
    starts_at = Column(DateTime, nullable=True)
    # Who performed the activation/revocation and when (admin audit trail).
    activated_by = Column(String, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    revoked_by = Column(String, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(Text, default="")


class SubscriptionDB(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    edition = Column(String, nullable=False)
    plan_name = Column(String, default="")
    status = Column(String, default="active")
    started_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    payment_provider = Column(String, default="")
    external_id = Column(String, default="")


# ── One-time download tokens (PART C) ────────────────────────────────────────

class DownloadTokenDB(Base):
    """A single-use, short-lived credential for a pre-rendered export.

    The browser reaches ``GET /api/generation/downloads/{token}`` by a plain
    navigation, so it cannot attach the tab's Bearer header; the token itself
    is the credential. Persisting it (rather than keeping a process-local dict)
    means the POST that issues the token and the GET that consumes it may reach
    DIFFERENT workers on a multi-process deployment and the link still works.

    Security: the token is unguessable (``secrets.token_urlsafe(32)``), bound
    to the issuing user and job, expires quickly, and is consumed exactly once
    (``used_at`` set on first use; a second use 404s).
    """

    __tablename__ = "download_tokens"

    token = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    job_id = Column(String, nullable=False)
    path = Column(String, nullable=False)
    media_type = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_download_tokens_user", "user_id"),
        Index("ix_download_tokens_expires", "expires_at"),
    )


# ── Content Pack ──────────────────────────────────────────────────────────────

class ContentPackDB(Base):
    __tablename__ = "content_packs"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    class_level = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    term = Column(String, nullable=False)
    academic_year = Column(String, nullable=False)
    educational_level = Column(String, nullable=False)
    template_family = Column(String, nullable=False)
    version = Column(String, default="1.0")
    author = Column(String, default="SchemeKnit")
    is_official = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)
    price = Column(Float, default=0.0)
    lesson_count = Column(Integer, default=0)
    preview_path = Column(String, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContentPackLessonDB(Base):
    __tablename__ = "content_pack_lessons"

    id = Column(String, primary_key=True, default=generate_id)
    pack_id = Column(String, ForeignKey("content_packs.id"), nullable=False)
    lesson_plan_id = Column(String, ForeignKey("lesson_plans.id"), nullable=False)
    week_number = Column(Integer, nullable=False)
    lesson_sequence = Column(Integer, nullable=False)
    preview_text = Column(Text, default="")


class ContentPackPurchaseDB(Base):
    __tablename__ = "content_pack_purchases"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    pack_id = Column(String, ForeignKey("content_packs.id"), nullable=False)
    version = Column(String, default="1.0")
    purchased_at = Column(DateTime, default=datetime.utcnow)
    download_count = Column(Integer, default=0)


# ── Template Definition (custom templates) ────────────────────────────────────

class TemplateDefinitionDB(Base):
    __tablename__ = "template_definitions"

    id = Column(String, primary_key=True, default=generate_id)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)
    family = Column(String, nullable=False)
    educational_level = Column(String, nullable=False)
    description = Column(Text, default="")
    features = Column(JSON, default=list)
    sections = Column(JSON, default=list)
    layout = Column(JSON, default=dict)
    is_default = Column(Boolean, default=False)
    is_official = Column(Boolean, default=False)
    is_custom = Column(Boolean, default=False)
    source_type = Column(String, default="builtin")
    template_file_path = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)
    status = Column(String, default="active")
    structure = Column(JSON, default=dict)
    version = Column(String, default="1.0")
    author = Column(String, default="SchemeKnit")
    preview_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── AI Enrichment Cache ──────────────────────────────────────────────────────

class AIEnrichmentCacheDB(Base):
    __tablename__ = "ai_enrichment_cache"

    id = Column(String, primary_key=True, default=generate_id)
    lesson_plan_id = Column(String, ForeignKey("lesson_plans.id"), nullable=False)
    section = Column(String, nullable=False)
    content = Column(Text, default="")
    provider = Column(String, default="")
    educational_level = Column(String, default="")
    subject = Column(String, default="")
    strand = Column(String, default="")
    indicator_hash = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ai_cache_lesson_section", "lesson_plan_id", "section"),
    )


class ZeliGenerationCacheDB(Base):
    """Whole-lesson Zeli output, keyed by every material generation input.

    Separate from ``ai_enrichment_cache`` because it is produced BEFORE any
    lesson row exists and is keyed by curriculum/config identity rather than a
    lesson_plan_id. The cache key includes generation method, provider, model,
    prompt version and every lesson/config input that changes the output, so a
    Zeli result can never be served to a STANDARD generation (or vice versa).
    """

    __tablename__ = "zeli_generation_cache"

    id = Column(String, primary_key=True, default=generate_id)
    cache_key = Column(String, nullable=False, unique=True, index=True)
    content = Column(Text, default="")
    provider = Column(String, default="")
    model = Column(String, default="")
    generation_method = Column(String, default="zeli")
    created_at = Column(DateTime, default=datetime.utcnow)


class AIUsageEventDB(Base):
    """Idempotency ledger for successful AI generations.

    Records that one successful AI generation request consumed an allowance.
    It is NOT a second quota system — the monthly quota itself lives in
    ``ai_generation_periods`` (ai_quota.py). This table only guarantees a
    duplicate submission for the same request cannot double-consume
    (``request_id`` is supplied by the client per user action).
    """
    __tablename__ = "ai_usage_events"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    request_id = Column(String, nullable=True)
    consumed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_ai_usage_user_request"),
    )


# ── Usage Quota (calendar-period lesson-plan allowance) ───────────────────────

class AIGenerationPeriodDB(Base):
    """Aggregate AI generation usage for one user in one calendar month.

    The Free Tier AI allowance is MONTHLY (real-use remediation PART 16):
    keyed by (user_id, "ai_calendar_month", "YYYY-MM") from the SERVER clock,
    so a new month reads a different row and usage resets to 0/N automatically.
    A failed AI call never writes a row (PART 19) — only a successful
    AI-assisted generation increments ``units_used`` via ai_quota.py.
    """
    __tablename__ = "ai_generation_periods"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    period_type = Column(String, nullable=False)   # "ai_calendar_month"
    period_key = Column(String, nullable=False)    # e.g. "2026-09"
    units_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "period_type", "period_key",
                         name="uq_ai_generation_period"),
    )


class UsagePeriodDB(Base):
    """Aggregate lesson-plan usage for one user in one calendar period.

    Keyed by (user_id, period_type, period_key). For the Free Tier the period
    is a calendar month (period_key = "YYYY-MM" derived from the SERVER clock),
    so January usage never affects February and no cron job is required to
    reset anything: a new month simply reads a different row.

    ``units_used`` mirrors the number of ``usage_units`` rows for the period and
    is only ever changed through the atomic reservation API in usage_quota.py.
    """
    __tablename__ = "usage_periods"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    period_type = Column(String, nullable=False)   # "calendar_month"
    period_key = Column(String, nullable=False)    # e.g. "2026-09"
    units_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "period_type", "period_key",
                         name="uq_usage_period"),
    )


class UsageUnitDB(Base):
    """One billable unit (one generated lesson plan) inside a usage period.

    The unit is keyed by (user, period, kind, key) where the key identifies the
    exact lesson being generated (``<scheme_id>:<indicator_code>``). This makes
    the quota idempotent: regenerating the same indicator for the same scheme in
    the same month does NOT consume another unit, because the row already exists.
    """
    __tablename__ = "usage_units"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    period_type = Column(String, nullable=False)
    period_key = Column(String, nullable=False)
    unit_kind = Column(String, nullable=False)     # "lesson_plan"
    unit_key = Column(String, nullable=False)      # "<scheme_id>:<indicator_code>"
    scheme_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "period_type", "period_key",
                         "unit_kind", "unit_key", name="uq_usage_unit"),
        Index("ix_usage_units_period", "user_id", "period_type", "period_key"),
    )


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentDB(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    payment_method = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="GHS")
    product_type = Column(String, nullable=False)
    product_id = Column(String, nullable=False)
    product_name = Column(String, default="")
    reference = Column(String, default="")
    payer_name = Column(String, default="")
    payer_phone = Column(String, default="")
    proof_path = Column(String, nullable=True)
    notes = Column(Text, default="")
    status = Column(String, default="pending")
    submitted_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String, nullable=True)
    rejection_reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_payments_user_status", "user_id", "status"),
        Index("ix_payments_status", "status"),
    )


class PaymentAuditLogDB(Base):
    __tablename__ = "payment_audit_logs"

    id = Column(String, primary_key=True, default=generate_id)
    payment_id = Column(String, ForeignKey("payments.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    amount = Column(Float, default=0.0)
    currency = Column(String, default="GHS")
    product_type = Column(String, default="")
    product_id = Column(String, default="")
    payment_method = Column(String, default="")
    performed_by = Column(String, nullable=False)
    notes = Column(Text, default="")
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_audit_payment", "payment_id"),
        Index("ix_audit_timestamp", "timestamp"),
    )


# ── Product / Plan Configuration ──────────────────────────────────────────────

class ProductPlanDB(Base):
    __tablename__ = "product_plans"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    product_type = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, default="GHS")
    duration_days = Column(Integer, nullable=True)
    seat_limit = Column(Integer, default=10)
    features = Column(JSON, default=list)
    educational_levels = Column(JSON, default=list)
    template_access = Column(JSON, default=list)
    ai_access = Column(String, default="")
    content_access = Column(JSON, default=list)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Individual teacher plan fields (v013)
    customer_type = Column(String, default="school")  # school | individual_teacher
    generation_limit = Column(Integer, default=0)  # 0 = unlimited
    batch_generation = Column(Boolean, default=False)
    zip_export = Column(Boolean, default=False)
    pdf_export = Column(Boolean, default=False)
    custom_template_limit = Column(Integer, default=0)
    history_limit = Column(Integer, default=0)
    ai_enabled = Column(Boolean, default=False)
    ai_credits = Column(Integer, default=0)  # 0 = unlimited or disabled
    max_generations_per_period = Column(Integer, default=0)  # 0 = unlimited


class PaymentConfigDB(Base):
    __tablename__ = "payment_config"

    id = Column(String, primary_key=True, default=generate_id)
    config_key = Column(String, unique=True, nullable=False)
    config_value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── School ────────────────────────────────────────────────────────────────────

class SchoolDB(Base):
    __tablename__ = "schools"

    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    school_code = Column(String, unique=True, nullable=False)
    contact_name = Column(String, default="")
    contact_phone = Column(String, default="")
    contact_email = Column(String, default="")
    address = Column(Text, default="")
    status = Column(String, default="active")  # active, suspended, archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    memberships = relationship("SchoolMembershipDB", back_populates="school")
    licenses = relationship("SchoolLicenseDB", back_populates="school")


# ── School Membership ─────────────────────────────────────────────────────────

class SchoolMembershipDB(Base):
    __tablename__ = "school_memberships"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    role = Column(String, nullable=False)  # school_admin, teacher
    status = Column(String, default="active")  # active, inactive
    joined_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="school_memberships")
    school = relationship("SchoolDB", back_populates="memberships")

    __table_args__ = (
        Index("ix_membership_user_school", "user_id", "school_id", unique=True),
    )


# ── School License ────────────────────────────────────────────────────────────

class SchoolLicenseDB(Base):
    __tablename__ = "school_licenses"

    id = Column(String, primary_key=True, default=generate_id)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    product_plan_id = Column(String, ForeignKey("product_plans.id"), nullable=False)
    license_code = Column(String, unique=True, nullable=False)
    status = Column(String, default="pending")  # pending, active, expired, suspended, cancelled
    start_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False)
    seat_limit = Column(Integer, default=10)
    # Activation lifecycle: set when a school redeems an activation code against
    # this license. `status` alone cannot distinguish "created by admin" from
    # "actually claimed by a school".
    activated_at = Column(DateTime, nullable=True)
    # Plain reference (not a ForeignKey) to avoid a circular table dependency:
    # activation_codes.license_id already points back here.
    activation_code_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    school = relationship("SchoolDB", back_populates="licenses")
    product_plan = relationship("ProductPlanDB")

    __table_args__ = (
        Index("ix_license_school", "school_id"),
        Index("ix_license_code", "license_code"),
    )


# ── Activation Code ───────────────────────────────────────────────────────────

class ActivationCodeDB(Base):
    __tablename__ = "activation_codes"

    id = Column(String, primary_key=True, default=generate_id)
    license_id = Column(String, ForeignKey("school_licenses.id"), nullable=False)
    code = Column(String, unique=True, nullable=False)
    status = Column(String, default="active")  # active, used, revoked
    used_by_school_id = Column(String, ForeignKey("schools.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    license = relationship("SchoolLicenseDB")

    __table_args__ = (
        Index("ix_activation_code", "code"),
    )


# ── Individual Teacher Activation Code ────────────────────────────────────────

class IndividualActivationCodeDB(Base):
    __tablename__ = "individual_activation_codes"

    id = Column(String, primary_key=True, default=generate_id)
    product_plan_id = Column(String, ForeignKey("product_plans.id"), nullable=False)
    code = Column(String, unique=True, nullable=False)
    status = Column(String, default="active")  # active, used, revoked
    used_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    product_plan = relationship("ProductPlanDB")

    __table_args__ = (
        Index("ix_individual_activation_code", "code"),
    )


# ── Platform Audit Log ────────────────────────────────────────────────────────

class PlatformAuditLogDB(Base):
    __tablename__ = "platform_audit_logs"

    id = Column(String, primary_key=True, default=generate_id)
    actor_id = Column(String, ForeignKey("users.id"), nullable=False)
    actor_role = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target_type = Column(String, default="")  # school, license, payment, user, etc.
    target_id = Column(String, default="")
    details = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_platform_audit_actor", "actor_id"),
        Index("ix_platform_audit_timestamp", "timestamp"),
    )


# ── Offline License Cache (for desktop) ──────────────────────────────────────

class LicenseCacheDB(Base):
    __tablename__ = "license_cache"

    id = Column(String, primary_key=True, default=generate_id)
    school_id = Column(String, ForeignKey("schools.id"), nullable=False)
    license_code = Column(String, nullable=False)
    plan_name = Column(String, default="")
    seat_limit = Column(Integer, default=10)
    features = Column(JSON, default=list)
    expiry_date = Column(Date, nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow)
    validated_at = Column(DateTime, nullable=True)
    signature = Column(String, default="")  # For integrity verification


# ── Password Reset Tokens ─────────────────────────────────────────────────────

class PasswordResetTokenDB(Base):
    """One-time, expiring password-reset tokens.

    The raw token is ``secrets.token_urlsafe(32)`` — only its SHA-256 digest
    is persisted. A token is bound to exactly one user, single-use, and
    expires after RESET_TOKEN_TTL_MINUTES.
    """

    __tablename__ = "password_reset_tokens"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)  # NULL = pending
    initiated_by = Column(String, nullable=False)  # user id of the admin/actor
    initiated_at = Column(DateTime, default=datetime.utcnow)
    # Method: web_admin | cli_break_glass | self_service
    method = Column(String, default="web_admin")

    user = relationship("User")

    __table_args__ = (
        Index("ix_reset_token_user", "user_id"),
        Index("ix_reset_token_hash", "token_hash"),
    )


# ── Paystack subscriptions & automatic licensing ────────────────────────────

class SubscriptionPlanDB(Base):
    """Sellable subscription plan with environment-specific Paystack codes."""
    __tablename__ = "subscription_plans"

    id = Column(String, primary_key=True, default=generate_id)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    price_pesewas = Column(Integer, nullable=False)  # GHS minor unit
    currency = Column(String, default="GHS")
    interval = Column(String, nullable=False)  # monthly | annual
    duration_days = Column(Integer, nullable=False)
    features = Column(JSON, default=list)
    entitlements = Column(JSON, default=dict)
    active = Column(Boolean, default=True)
    paystack_test_plan_code = Column(String, default="")
    paystack_live_plan_code = Column(String, default="")
    #: Approved commercial catalogue (v041). ``package_kind`` is
    #: free | flexible | timed. A timed package grants ``credit_allowance``
    #: credits until ``credit_validity_days`` after activation; a flexible pack
    #: grants credits that never expire. Prices remain in ``price_pesewas``.
    package_kind = Column(String, default="timed")
    credit_allowance = Column(Integer, default=0)
    credit_validity_days = Column(Integer, nullable=True)
    display_order = Column(Integer, default=0)
    payment_terms = Column(String, default="One-time prepaid payment. No automatic renewal.")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSubscriptionDB(Base):
    """One local subscription per user, advanced only by verified payments."""
    __tablename__ = "user_subscriptions"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(String, ForeignKey("subscription_plans.id"), nullable=False)
    provider = Column(String, default="paystack")
    environment = Column(String, default="test")  # test | live
    provider_customer_code = Column(String, default="")
    provider_subscription_code = Column(String, default="", index=True)
    provider_email_token = Column(String, default="")
    status = Column(String, default="pending")  # pending|active|past_due|non_renewing|cancelled|expired|completed
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    paid_through = Column(DateTime, nullable=True)
    grace_until = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    cancelled_at = Column(DateTime, nullable=True)
    billing_mode = Column(String, default="recurring")  # recurring|prepaid
    payment_method = Column(String, default="card")  # card|mobile_money
    provider = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_subscription_user"),
    )


class SubscriptionTransactionDB(Base):
    """Payment attempt keyed by our unique reference (never credited twice)."""
    __tablename__ = "subscription_transactions"

    id = Column(String, primary_key=True, default=generate_id)
    reference = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(String, ForeignKey("subscription_plans.id"), nullable=False)
    subscription_id = Column(String, ForeignKey("user_subscriptions.id"), nullable=True)
    provider = Column(String, default="paystack")
    environment = Column(String, default="test")
    amount_pesewas = Column(Integer, nullable=False)
    currency = Column(String, default="GHS")
    status = Column(String, default="pending")  # pending|success|failed|abandoned
    provider_transaction_id = Column(String, default="")
    channel = Column(String, default="")
    payment_method = Column(String, default="card_recurring")  # card_recurring|mobile_money
    provider = Column(String, default="")  # mtn|atl|vod
    charge_status = Column(String, default="")
    instructions = Column(Text, default="")
    #: Provider-returned prepaid instructions (bank account, expiry, etc.).
    payment_details = Column(JSON, default=dict)
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaystackWebhookEventDB(Base):
    """Idempotency ledger for webhook deliveries."""
    __tablename__ = "paystack_webhook_events"

    id = Column(String, primary_key=True, default=generate_id)
    event_key = Column(String, unique=True, nullable=False, index=True)
    event_type = Column(String, default="")
    reference = Column(String, default="", index=True)
    payload_hash = Column(String, default="")
    payload_json = Column(JSON, default=dict)
    status = Column(String, default="received")  # received|processing|processed|ignored|failed|exhausted
    attempts = Column(Integer, default=0)
    last_error = Column(String, default="")
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    lease_owner = Column(String, default="")
    lease_expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_paystack_webhook_retry", "status", "next_retry_at"),
    )


class SubscriptionEventDB(Base):
    """Append-only subscription status history for audit and support."""
    __tablename__ = "subscription_events"

    id = Column(String, primary_key=True, default=generate_id)
    subscription_id = Column(String, ForeignKey("user_subscriptions.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    from_status = Column(String, default="")
    to_status = Column(String, default="")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserLicenseDB(Base):
    """Per-user software licence issued by a verified subscription payment."""
    __tablename__ = "user_licenses"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    plan_id = Column(String, ForeignKey("subscription_plans.id"), nullable=False)
    subscription_id = Column(String, ForeignKey("user_subscriptions.id"), nullable=True)
    licence_key = Column(String, unique=True, nullable=False)
    key_hash = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="active")  # active|expired|revoked
    issued_at = Column(DateTime, default=datetime.utcnow)
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CreditBalanceDB(Base):
    """One auditable credit bucket for a user.

    ``source`` keeps free/referral/purchased/package credits separate so each
    source keeps its own expiry and reporting. Free monthly credits are not
    stored here: they are computed from ``usage_periods`` and reset with the
    Africa/Accra calendar. A pack that never expires stores ``expires_at=None``.
    """
    __tablename__ = "credit_balances"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String, nullable=False)  # purchased|package|referral
    package_slug = Column(String, default="")
    label = Column(String, default="")
    credits_granted = Column(Integer, nullable=False, default=0)
    credits_remaining = Column(Integer, nullable=False, default=0)
    granted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # NULL = never expires
    #: Idempotency key for the grant that created this bucket (e.g.
    #: ``package:<transaction reference>`` or ``referral:referrer:<id>``).
    grant_key = Column(String, unique=True, nullable=False, index=True)
    reference = Column(String, default="")
    status = Column(String, default="active")  # active|exhausted|reversed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_credit_balance_user_source", "user_id", "source"),
    )


class CreditLedgerDB(Base):
    """Append-only credit movement ledger (never delete a row)."""
    __tablename__ = "credit_ledger"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    balance_id = Column(String, ForeignKey("credit_balances.id"), nullable=True, index=True)
    entry_type = Column(String, nullable=False)  # grant|consume|release|expire|reverse|adjust
    source = Column(String, default="")
    credits = Column(Integer, nullable=False)  # signed: + grant, - consume
    reason = Column(String, default="")
    reference = Column(String, default="", index=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CreditReservationDB(Base):
    """A held batch of credits for one generation request.

    ``allocations`` records exactly which bucket paid for which indicator code,
    so a failed or partial run can refund the correct source without guessing.
    The unique ``idempotency_key`` makes a duplicate submission return the
    existing hold instead of charging twice.
    """
    __tablename__ = "credit_reservations"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    scheme_id = Column(String, default="")
    units = Column(Integer, nullable=False, default=0)
    status = Column(String, default="held")  # held|committed|released
    allocations = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReferralCodeDB(Base):
    """One stable referral code/link per eligible account."""
    __tablename__ = "referral_codes"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralDB(Base):
    """Attribution and reward state for one referred account.

    ``referred_id`` is unique: an account can be attributed to exactly one
    referrer, and no second reward is ever possible for it.
    """
    __tablename__ = "referrals"

    id = Column(String, primary_key=True, default=generate_id)
    referrer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    referred_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    code = Column(String, nullable=False, index=True)
    attributed_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="registered")  # registered|qualified|rewarded|reversed
    qualifying_reference = Column(String, default="", index=True)
    referrer_credits = Column(Integer, default=0)
    referred_credits = Column(Integer, default=0)
    rewarded_at = Column(DateTime, nullable=True)
    reversed_at = Column(DateTime, nullable=True)
    reversal_reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReferralVisitDB(Base):
    """A referral-link open, so the dashboard can report invites accurately."""
    __tablename__ = "referral_visits"

    id = Column(String, primary_key=True, default=generate_id)
    code = Column(String, nullable=False, index=True)
    opened_at = Column(DateTime, default=datetime.utcnow)


class ReferralSettingDB(Base):
    """Admin-configurable referral limits (singleton row)."""
    __tablename__ = "referral_settings"

    id = Column(String, primary_key=True, default=generate_id)
    reward_referrer = Column(Integer, default=5)
    reward_referred = Column(Integer, default=3)
    term_limit = Column(Integer, default=5)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String, default="")


class RevokedTokenDB(Base):
    """Bounded server-side logout revocation, one row per signed-out session.

    Access tokens are stateless JWTs, so logout cannot invalidate them by
    deleting a server session. Each user token carries a unique ``jti``; logout
    inserts that id here and every authenticated request rejects a revoked
    ``jti`` until its natural expiry. Rows are deleted once expired, keeping
    the table bounded by the number of *recent* logouts, not by lifetime usage.

    Only the token id is stored — never the token, password, or email.
    """
    __tablename__ = "revoked_tokens"

    jti = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_revoked_token_expiry", "expires_at"),
    )


class UserSessionDB(Base):
    """Server-verifiable login session for JWT idle/absolute/revoke-all checks.

    Only the JWT id and timestamps are stored. No token, password or raw IP is
    kept. ``revoked_at`` marks individual logout or revoke-all.
    """
    __tablename__ = "user_sessions"

    jti = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_user_sessions_user", "user_id", "revoked_at"),
        Index("ix_user_sessions_expiry", "expires_at"),
    )


class LoginFailureDB(Base):
    """Per-account failed-login state for progressive cooldown.

    The account key is an HMAC of the normalized identifier, never a plaintext
    email. Counters are account-scoped so changing IP cannot bypass them.
    """

    __tablename__ = "login_failure_counters"

    id = Column(String, primary_key=True, default=generate_id)
    account_key = Column(String, nullable=False, unique=True, index=True)
    failed_count = Column(Integer, default=0, nullable=False)
    window_started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_failed_at = Column(DateTime, nullable=True)
    lockout_count = Column(Integer, default=0, nullable=False)
    last_lockout_at = Column(DateTime, nullable=True)
    lockout_until = Column(DateTime, nullable=True, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RateLimitCounterDB(Base):
    """Shared fixed-window rate-limit counter (SQLite/PostgreSQL)."""

    __tablename__ = "rate_limit_counters"

    id = Column(String, primary_key=True, default=generate_id)
    bucket_key = Column(String, nullable=False)
    window_start = Column(Integer, nullable=False)  # Unix seconds
    count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("bucket_key", "window_start",
                         name="uq_rate_limit_bucket_window"),
        Index("ix_rate_limit_window", "window_start"),
    )


def init_db():
    Base.metadata.create_all(bind=engine)
