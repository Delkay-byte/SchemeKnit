"""
SchemeKnit Data Service

Bridges Pydantic models with SQLAlchemy persistence.
Provides CRUD operations with ownership enforcement.
"""

from datetime import datetime, date
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from .database import (
    SchemeDB, WeekDB, TermConfigDB, GenerationJobDB, LessonPlanDB,
    HolidayDB, UserPreferencesDB, TemplateDefinitionDB, ExportEventDB,
    User, generate_id
)
from .models import (
    SchemeOfWork, Week, WeekType, TermConfig, Subject, ClassLevel,
    GenerationJob, LessonPlan, LessonStatus, JobStatus, Holiday,
    AIMode, ValidationIssue, EducationalLevel, TemplateType,
    CLASS_LEVEL_TO_EDUCATIONAL_LEVEL,
)


WORKFLOW_STAGES = ["upload", "review", "configure", "generate", "export"]

# Scheme statuses that imply the review/approve action was persisted.
REVIEWED_STATUSES = ("approved", "generating", "generated", "completed")


def compute_workflow_state(status: str, has_job: bool, job_completed: bool,
                           lessons_count: int, has_export: bool) -> list:
    """Derive completed/active/locked per stage from PERSISTED signals only.

    Page visitation plays no role: every flag comes from stored rows
    (scheme status, generation jobs, lesson plans, export events).
    Exactly one stage is active unless all five are completed.
    """
    done = {
        "upload": True,  # the scheme row exists (caller enforces ownership)
        "review": status in REVIEWED_STATUSES,
        "configure": bool(has_job),
        "generate": bool(job_completed and (lessons_count or 0) > 0),
        "export": bool(has_export),
    }
    stages = []
    active_assigned = False
    for key in WORKFLOW_STAGES:
        if done[key]:
            state = "completed"
        elif not active_assigned:
            state = "active"
            active_assigned = True
        else:
            state = "locked"
        stages.append({"key": key, "state": state})
    return stages


class DataService:
    """Persistent data service with ownership enforcement."""

    # ── Schemes ───────────────────────────────────────────────────────────────

    def create_scheme(self, db: Session, owner_id: str, scheme: SchemeOfWork, school_id: str = None) -> SchemeDB:
        db_scheme = SchemeDB(
            id=scheme.id,
            owner_id=owner_id,
            school_id=school_id,
            filename=scheme.filename,
            subject=scheme.subject.value if isinstance(scheme.subject, Subject) else str(scheme.subject),
            class_level=scheme.class_level.value if isinstance(scheme.class_level, ClassLevel) else str(scheme.class_level),
            term=scheme.term,
            academic_year=scheme.academic_year,
            status=scheme.status,
            raw_text=scheme.raw_text or "",
            validation_issues=[vi.model_dump() for vi in scheme.validation_issues],
        )
        db.add(db_scheme)

        for week in scheme.weeks:
            db_week = WeekDB(
                id=week.id,
                scheme_id=scheme.id,
                week_number=week.week_number,
                week_type=week.week_type.value,
                start_date=week.start_date,
                end_date=week.end_date,
                strand=week.strand or "",
                sub_strand=week.sub_strand or "",
                content_standards=week.content_standards,
                indicators=week.indicators,
                resources=week.resources,
            )
            db.add(db_week)

        db.commit()
        db.refresh(db_scheme)
        return db_scheme

    def get_scheme(self, db: Session, scheme_id: str, owner_id: str) -> Optional[SchemeDB]:
        return db.query(SchemeDB).filter(
            and_(SchemeDB.id == scheme_id, SchemeDB.owner_id == owner_id)
        ).first()

    def scheme_exists(self, db: Session, scheme_id: str) -> bool:
        """ID-only existence check for diagnostic 404 vs 403 responses."""
        return db.query(SchemeDB.id).filter(SchemeDB.id == scheme_id).first() is not None

    def list_schemes(self, db: Session, owner_id: str) -> List[SchemeDB]:
        return db.query(SchemeDB).filter(
            SchemeDB.owner_id == owner_id
        ).order_by(SchemeDB.upload_date.desc()).all()

    def update_scheme_status(self, db: Session, scheme_id: str, owner_id: str, status: str) -> Optional[SchemeDB]:
        scheme = self.get_scheme(db, scheme_id, owner_id)
        if scheme:
            scheme.status = status
            db.commit()
            db.refresh(scheme)
        return scheme

    def scheme_has_children(self, db: Session, scheme_id: str, owner_id: str) -> bool:
        """True when generation jobs or lesson plans reference the scheme.

        Deletion is blocked in that case (409) rather than orphaning rows on
        SQLite or violating foreign keys on PostgreSQL.
        """
        job = db.query(GenerationJobDB.id).filter(
            and_(GenerationJobDB.scheme_id == scheme_id,
                 GenerationJobDB.owner_id == owner_id)).first()
        if job:
            return True
        lesson = db.query(LessonPlanDB.id).filter(
            and_(LessonPlanDB.scheme_id == scheme_id,
                 LessonPlanDB.owner_id == owner_id)).first()
        return lesson is not None

    def delete_scheme(self, db: Session, scheme_id: str, owner_id: str) -> bool:
        scheme = self.get_scheme(db, scheme_id, owner_id)
        if scheme:
            storage = getattr(scheme, "storage_filename", None)
            db.delete(scheme)
            db.commit()
            # Safe orphan cleanup: remove the storage file only when no other
            # scheme references it. Filesystem errors never fail the delete.
            if storage:
                try:
                    refs = db.query(SchemeDB).filter(
                        SchemeDB.storage_filename == storage).count()
                    if refs == 0:
                        import os
                        if os.path.exists(storage):
                            os.unlink(storage)
                except Exception:
                    pass
            return True
        return False

    def scheme_to_model(self, db_scheme: SchemeDB) -> SchemeOfWork:
        weeks = []
        for w in db_scheme.weeks:
            weeks.append(Week(
                id=w.id,
                week_number=w.week_number,
                week_type=WeekType(w.week_type),
                start_date=w.start_date,
                end_date=w.end_date,
                strand=w.strand,
                sub_strand=w.sub_strand,
                content_standards=w.content_standards or [],
                indicators=w.indicators or [],
                resources=w.resources or [],
                scheme_of_work_id=w.scheme_id,
            ))

        return SchemeOfWork(
            id=db_scheme.id,
            filename=db_scheme.filename,
            upload_date=db_scheme.upload_date,
            subject=Subject(db_scheme.subject),
            class_level=ClassLevel(db_scheme.class_level),
            term=db_scheme.term,
            academic_year=db_scheme.academic_year,
            weeks=weeks,
            raw_text=db_scheme.raw_text,
            status=db_scheme.status,
        )

    # ── Term Configs ──────────────────────────────────────────────────────────

    def create_term_config(self, db: Session, owner_id: str, scheme_id: str, config: TermConfig) -> TermConfigDB:
        db_config = TermConfigDB(
            id=config.id,
            owner_id=owner_id,
            scheme_id=scheme_id,
            term_start_date=config.term_start_date,
            term_end_date=config.term_end_date,
            lessons_per_week=config.lessons_per_week,
            lesson_duration_minutes=config.lesson_duration_minutes,
            class_size=config.class_size,
            teaching_days=config.teaching_days,
            holidays=[h.model_dump() for h in config.holidays],
            ai_mode=config.ai_mode.value if isinstance(config.ai_mode, AIMode) else str(config.ai_mode),
            template_type=config.template_type.value if isinstance(config.template_type, TemplateType) else str(config.template_type),
            include_special_weeks=config.include_special_weeks,
            school_name=config.school_name or "",
            teacher_name=config.teacher_name or "",
        )
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return db_config

    def get_term_config(self, db: Session, scheme_id: str, owner_id: str) -> Optional[TermConfigDB]:
        return db.query(TermConfigDB).filter(
            and_(TermConfigDB.scheme_id == scheme_id, TermConfigDB.owner_id == owner_id)
        ).first()

    # ── Generation Jobs ───────────────────────────────────────────────────────

    def create_job(self, db: Session, owner_id: str, scheme_id: str, config: TermConfig) -> GenerationJobDB:
        db_job = GenerationJobDB(
            owner_id=owner_id,
            scheme_id=scheme_id,
            status="pending",
            config_snapshot=config.model_dump(mode="json"),
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        return db_job

    def get_job(self, db: Session, job_id: str, owner_id: str) -> Optional[GenerationJobDB]:
        return db.query(GenerationJobDB).filter(
            and_(GenerationJobDB.id == job_id, GenerationJobDB.owner_id == owner_id)
        ).first()

    def update_job(self, db: Session, job_id: str, **kwargs) -> Optional[GenerationJobDB]:
        job = db.query(GenerationJobDB).filter(GenerationJobDB.id == job_id).first()
        if job:
            for key, value in kwargs.items():
                setattr(job, key, value)
            db.commit()
            db.refresh(job)
        return job

    def list_jobs(self, db: Session, owner_id: str) -> List[GenerationJobDB]:
        return db.query(GenerationJobDB).filter(
            GenerationJobDB.owner_id == owner_id
        ).order_by(GenerationJobDB.created_at.desc()).all()

    # ── Lesson Plans ──────────────────────────────────────────────────────────

    def create_lesson_plan(self, db: Session, owner_id: str, job_id: str, scheme_id: str, lp: LessonPlan) -> LessonPlanDB:
        db_lp = LessonPlanDB(
            id=lp.id,
            job_id=job_id,
            owner_id=owner_id,
            scheme_id=scheme_id,
            week_number=lp.week_number,
            lesson_sequence=lp.lesson_sequence,
            lesson_date=lp.lesson_date,
            lesson_number=lp.lesson_number,
            period=getattr(lp, "period", "") or "",
            class_level=lp.class_level.value if isinstance(lp.class_level, ClassLevel) else str(lp.class_level),
            subject=lp.subject.value if isinstance(lp.subject, Subject) else str(lp.subject),
            class_size=lp.class_size,
            duration_minutes=lp.duration_minutes,
            school_name=lp.school_name or "",
            teacher_name=lp.teacher_name or "",
            strand=lp.strand or "",
            sub_strand=lp.sub_strand or "",
            content_standard=lp.content_standard or "",
            content_standard_code=lp.content_standard_code or "",
            indicators=lp.indicators,
            indicator_codes=lp.indicator_codes,
            lesson_topic=lp.lesson_topic or "",
            previous_knowledge=lp.previous_knowledge or "",
            learning_objectives=[o.model_dump() for o in lp.learning_objectives],
            core_competencies=lp.core_competencies,
            teaching_learning_resources=lp.teaching_learning_resources,
            introduction=lp.introduction or "",
            main_activities=[a.model_dump() for a in lp.main_activities],
            learner_activities=[a.model_dump() for a in lp.learner_activities],
            teacher_activities=[a.model_dump() for a in lp.teacher_activities],
            assessment=lp.assessment or "",
            conclusion=lp.conclusion or "",
            references=lp.references,
            status=lp.status.value if isinstance(lp.status, LessonStatus) else str(lp.status),
            ai_generated=lp.ai_generated,
            teacher_edited=lp.teacher_edited,
            original_data={},
        )
        db.add(db_lp)
        db.commit()
        db.refresh(db_lp)
        return db_lp

    def get_lesson_plan(self, db: Session, lesson_id: str, owner_id: str) -> Optional[LessonPlanDB]:
        return db.query(LessonPlanDB).filter(
            and_(LessonPlanDB.id == lesson_id, LessonPlanDB.owner_id == owner_id)
        ).first()

    def get_lesson_plans_for_job(self, db: Session, job_id: str, owner_id: str) -> List[LessonPlanDB]:
        return db.query(LessonPlanDB).filter(
            and_(LessonPlanDB.job_id == job_id, LessonPlanDB.owner_id == owner_id)
        ).order_by(LessonPlanDB.week_number, LessonPlanDB.lesson_sequence).all()

    def get_lesson_plans_for_scheme(self, db: Session, scheme_id: str, owner_id: str) -> List[LessonPlanDB]:
        return db.query(LessonPlanDB).filter(
            and_(LessonPlanDB.scheme_id == scheme_id, LessonPlanDB.owner_id == owner_id)
        ).order_by(LessonPlanDB.lesson_date, LessonPlanDB.lesson_sequence).all()

    def update_lesson_plan(self, db: Session, lesson_id: str, owner_id: str, updates: dict) -> Optional[LessonPlanDB]:
        lp = self.get_lesson_plan(db, lesson_id, owner_id)
        if not lp:
            return None

        if not lp.teacher_edited:
            lp.original_data = {
                "introduction": lp.introduction,
                "main_activities": lp.main_activities,
                "learner_activities": lp.learner_activities,
                "teacher_activities": lp.teacher_activities,
                "assessment": lp.assessment,
                "conclusion": lp.conclusion,
                "lesson_topic": lp.lesson_topic,
                "learning_objectives": lp.learning_objectives,
            }

        for key, value in updates.items():
            if hasattr(lp, key) and key not in ("id", "job_id", "owner_id", "scheme_id", "created_at"):
                setattr(lp, key, value)

        lp.teacher_edited = True
        lp.status = "edited"
        db.commit()
        db.refresh(lp)
        return lp

    def delete_lesson_plans_for_job(self, db: Session, job_id: str):
        db.query(LessonPlanDB).filter(LessonPlanDB.job_id == job_id).delete()
        db.commit()

    def delete_lesson_plans_for_scheme(self, db: Session, scheme_id: str, owner_id: str):
        db.query(LessonPlanDB).filter(
            and_(LessonPlanDB.scheme_id == scheme_id, LessonPlanDB.owner_id == owner_id)
        ).delete()
        db.commit()

    # ── Holidays ──────────────────────────────────────────────────────────────

    def list_holidays(self, db: Session, owner_id: Optional[str] = None) -> List[HolidayDB]:
        query = db.query(HolidayDB)
        if owner_id:
            query = query.filter(HolidayDB.owner_id == owner_id)
        return query.order_by(HolidayDB.date).all()

    def create_holiday(self, db: Session, holiday: Holiday, owner_id: Optional[str] = None) -> HolidayDB:
        db_holiday = HolidayDB(
            id=holiday.id,
            owner_id=owner_id,
            name=holiday.name,
            date=holiday.date,
            is_recurring=holiday.is_recurring,
            description=holiday.description or "",
        )
        db.add(db_holiday)
        db.commit()
        db.refresh(db_holiday)
        return db_holiday

    def delete_holiday(self, db: Session, holiday_id: str) -> bool:
        h = db.query(HolidayDB).filter(HolidayDB.id == holiday_id).first()
        if h:
            db.delete(h)
            db.commit()
            return True
        return False

    # ── User Preferences ──────────────────────────────────────────────────────

    def get_preferences(self, db: Session, user_id: str) -> Optional[UserPreferencesDB]:
        return db.query(UserPreferencesDB).filter(
            UserPreferencesDB.user_id == user_id
        ).first()

    def upsert_preferences(self, db: Session, user_id: str, **kwargs) -> UserPreferencesDB:
        prefs = self.get_preferences(db, user_id)
        if not prefs:
            prefs = UserPreferencesDB(user_id=user_id, **kwargs)
            db.add(prefs)
        else:
            for key, value in kwargs.items():
                if hasattr(prefs, key):
                    setattr(prefs, key, value)
        db.commit()
        db.refresh(prefs)
        return prefs


    # ── Custom Templates ───────────────────────────────────────────────────────

    def create_custom_template(self, db: Session, owner_id: str, *,
                                name: str, family: str, educational_level: str,
                                description: str = "", features: list = None,
                                sections: list = None, layout: dict = None,
                                template_file_path: str = None,
                                source_type: str = "uploaded") -> TemplateDefinitionDB:
        tpl = TemplateDefinitionDB(
            id=generate_id(),
            owner_id=owner_id,
            name=name,
            family=family,
            educational_level=educational_level,
            description=description,
            features=features or [],
            sections=sections or [],
            layout=layout or {},
            is_custom=True,
            is_official=False,
            source_type=source_type,
            template_file_path=template_file_path,
            author="Custom",
            version="1.0",
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)
        return tpl

    def get_custom_template(self, db: Session, template_id: str, owner_id: str = None) -> Optional[TemplateDefinitionDB]:
        q = db.query(TemplateDefinitionDB).filter(TemplateDefinitionDB.id == template_id)
        if owner_id:
            q = q.filter(TemplateDefinitionDB.owner_id == owner_id)
        return q.first()

    def list_custom_templates(self, db: Session, owner_id: str = None,
                              educational_level: str = None,
                              include_archived: bool = False) -> List[TemplateDefinitionDB]:
        q = db.query(TemplateDefinitionDB).filter(TemplateDefinitionDB.is_custom == True)
        if owner_id:
            q = q.filter(TemplateDefinitionDB.owner_id == owner_id)
        if educational_level:
            q = q.filter(TemplateDefinitionDB.educational_level == educational_level)
        if not include_archived:
            q = q.filter(
                (TemplateDefinitionDB.status == "active") |
                (TemplateDefinitionDB.status.is_(None))
            )
        return q.order_by(TemplateDefinitionDB.created_at.desc()).all()

    def update_custom_template(self, db: Session, template_id: str, owner_id: str, **kwargs) -> Optional[TemplateDefinitionDB]:
        tpl = self.get_custom_template(db, template_id, owner_id)
        if not tpl:
            return None
        for key, value in kwargs.items():
            if hasattr(tpl, key) and key not in ("id", "owner_id", "created_at"):
                setattr(tpl, key, value)
        tpl.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(tpl)
        return tpl

    def delete_custom_template(self, db: Session, template_id: str, owner_id: str) -> bool:
        tpl = self.get_custom_template(db, template_id, owner_id)
        if not tpl:
            return False
        db.delete(tpl)
        db.commit()
        return True

    def version_custom_template(self, db: Session, template_id: str, owner_id: str,
                                  version: str) -> Optional[TemplateDefinitionDB]:
        """Bump a template version (e.g. 1.0 -> 1.1). History rows keep old versions."""
        tpl = self.get_custom_template(db, template_id, owner_id)
        if not tpl:
            return None
        tpl.version = version
        tpl.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(tpl)
        return tpl

    def archive_custom_template(self, db: Session, template_id: str, owner_id: str) -> Optional[TemplateDefinitionDB]:
        """Soft-archive a template. Generated documents keep their version association."""
        tpl = self.get_custom_template(db, template_id, owner_id)
        if not tpl:
            return None
        tpl.status = "archived"
        tpl.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(tpl)
        return tpl

    # ── Workflow progress (server-persisted stage state) ──────────────────────

    def log_export_event(self, db: Session, job_id: str, scheme_id: str,
                         owner_id: str, format: str) -> ExportEventDB:
        """Persist a successful export (workflow stage 5 signal)."""
        ev = ExportEventDB(
            id=generate_id(),
            job_id=job_id,
            scheme_id=scheme_id,
            owner_id=owner_id,
            format=format,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return ev

    def has_export_for_scheme(self, db: Session, scheme_id: str, owner_id: str) -> bool:
        return db.query(ExportEventDB.id).filter(
            and_(ExportEventDB.scheme_id == scheme_id,
                 ExportEventDB.owner_id == owner_id)
        ).first() is not None

    def count_lessons_for_scheme(self, db: Session, scheme_id: str, owner_id: str) -> int:
        return db.query(LessonPlanDB.id).filter(
            and_(LessonPlanDB.scheme_id == scheme_id,
                 LessonPlanDB.owner_id == owner_id)
        ).count()

    def count_custom_templates(self, db: Session, owner_id: str) -> int:
        return db.query(TemplateDefinitionDB).filter(
            TemplateDefinitionDB.is_custom == True,
            TemplateDefinitionDB.owner_id == owner_id,
        ).count()


data_service = DataService()
