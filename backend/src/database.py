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

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=settings.DEBUG,
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
    strand = Column(String, default="")
    sub_strand = Column(String, default="")
    content_standards = Column(JSON, default=list)
    indicators = Column(JSON, default=list)
    resources = Column(JSON, default=list)

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
    class_size = Column(Integer, default=11)
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
    #: Actual teaching week the lesson is delivered in. Differs from
    #: week_number only when the indicator carried forward.
    teaching_week = Column(Integer, nullable=True)
    carry_forward = Column(Boolean, default=False)
    lesson_sequence = Column(Integer, nullable=False)
    lesson_date = Column(Date, nullable=True)
    lesson_number = Column(Integer, default=1)
    # Timetable slot the teacher configured (e.g. "1st & 2nd"). Never invented:
    # it is carried from the configuration/preferences, or blank.
    period = Column(String, default="")
    class_level = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    class_size = Column(Integer, default=11)
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
    core_competencies = Column(JSON, default=list)
    teaching_learning_resources = Column(JSON, default=list)

    introduction = Column(Text, default="")
    starter_activity = Column(Text, default="")
    main_activities = Column(JSON, default=list)
    learner_activities = Column(JSON, default=list)
    teacher_activities = Column(JSON, default=list)
    assessment = Column(Text, default="")
    conclusion = Column(Text, default="")
    references = Column(JSON, default=list)
    keywords = Column(JSON, default=list)
    homework = Column(Text, default="")
    differentiation = Column(Text, default="")
    essential_questions = Column(JSON, default=list)

    status = Column(String, default="generated")
    ai_generated = Column(Boolean, default=False)
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


class AIUsageEventDB(Base):
    """Idempotency ledger for successful AI generations.

    Records that one successful AI generation request consumed an allowance.
    It is NOT a second quota system — the quota itself lives on
    EntitlementDB.ai_credits / ai_credits_used. This table only guarantees a
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


def init_db():
    Base.metadata.create_all(bind=engine)
