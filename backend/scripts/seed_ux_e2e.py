"""Create disposable UX E2E fixtures and print environment assignments.

Used only by local/CI acceptance runs against a throwaway database. Never run
against production. Tokens are ephemeral CI/local credentials.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.auth import hash_password
from src.database import (
    GenerationJobDB, LessonPlanDB, ProductPlanDB, SchoolDB, SchoolLicenseDB,
    SchoolMembershipDB, SchemeDB, SessionLocal, User, WeekDB,
)
from src.models import DayPlan, SubjectMetadata, SubjectPlan, WeeklyClassPlan
from src.weekly_plan_store import create_row

PASSWORD = "UxE2e!Pass2026"


def uid() -> str:
    return str(uuid.uuid4())


def login(api: str, email: str, entry: str) -> dict:
    request = urllib.request.Request(
        f"{api}/api/auth/login",
        data=json.dumps({"email": email, "password": PASSWORD, "entry": entry}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(request, timeout=30))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        school = SchoolDB(id=uid(), name="UX Test School",
                          school_code=f"UXT-{uid()[:6]}", status="active")
        product = ProductPlanDB(id=uid(), name="UX Test School Plan",
                                product_type="school", price=0, seat_limit=20,
                                active=True)
        db.add_all([school, product])
        db.flush()
        db.add(SchoolLicenseDB(
            id=uid(), school_id=school.id, product_plan_id=product.id,
            license_code=f"UX-LIC-{uid()[:8]}", status="active",
            start_date=date.today(),
            expiry_date=date.today() + timedelta(days=365), seat_limit=20,
        ))

        def add_user(email, name, role, active=True, admin=False):
            user = User(
                id=uid(), email=email, full_name=name,
                hashed_password=hash_password(PASSWORD), role=role,
                school_id=school.id, is_admin=admin, is_active=active,
                school_name="UX Test School",
                subscription_type="school",
            )
            db.add(user)
            db.flush()
            db.add(SchoolMembershipDB(
                id=uid(), user_id=user.id, school_id=school.id,
                role=role, status="active",
            ))
            return user

        admin = add_user("ux-admin@test.local", "UX Admin", "school_admin", admin=True)
        teacher = add_user("ux-teacher@test.local", "UX E2E Teacher", "teacher")
        active = add_user("ux-active@test.local", "Active UX Teacher", "teacher")
        inactive = add_user("ux-inactive@test.local", "Inactive UX Teacher", "teacher", active=False)

        scheme = SchemeDB(
            id=uid(), owner_id=teacher.id, school_id=school.id,
            filename="ux-hardening-lesson.pdf", subject="Science",
            class_level="Basic 8", term="First Term", status="generated",
        )
        db.add(scheme)
        db.flush()
        db.add(WeekDB(
            id=uid(), scheme_id=scheme.id, week_number=1,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            strand="Diversity of Matter", sub_strand="Materials",
            content_standards=["B8.1.1.1 Demonstrate materials"],
            indicators=["B8.1.1.1.1 Identify materials"],
            resources=["Chart"],
        ))
        job = GenerationJobDB(
            id=uid(), owner_id=teacher.id, scheme_id=scheme.id,
            status="completed", completed_lessons=1, total_lessons=1,
        )
        db.add(job)
        db.flush()
        lesson = LessonPlanDB(
            id=uid(), job_id=job.id, owner_id=teacher.id, scheme_id=scheme.id,
            week_number=1, lesson_sequence=1, lesson_number=1,
            lesson_date=date(2026, 9, 11), class_level="Basic 8",
            subject="Science", lesson_topic="Original fixture topic",
            introduction="Original introduction", assessment="Original assessment",
            conclusion="Original conclusion", status="generated",
        )
        db.add(lesson)
        db.commit()
        db.refresh(lesson)

        plan = WeeklyClassPlan(
            id="wp-ux-fixture", owner_id=teacher.id, class_level="Basic 1",
            week_number=1, term="First Term", academic_year="2026/2027",
            school_name="UX Test School", teacher_name="UX E2E Teacher",
            template_id="wapef_basic13",
            subjects=[SubjectPlan(
                scheme_of_work_id=scheme.id, subject="English Language",
                teaching_days=["MONDAY"], teaching_day_groups=[["MONDAY"]],
                metadata=SubjectMetadata(subject="English Language", class_level="Basic 1"),
                day_plans=[DayPlan(
                    days=["MONDAY"], day_label="MONDAY",
                    focus_indicators=["B1.1.1.1.1"], starter="Original starter",
                    reflection="Original reflection", period="1st",
                )],
            )],
        )
        create_row(db, owner_id=teacher.id, plan=plan, school_id=school.id)

        admin_login = login(args.api, admin.email, "school_admin")
        teacher_login = login(args.api, teacher.email, "teacher")
        env = {
            "UX_ADMIN_TOKEN": admin_login["access_token"],
            "UX_ADMIN_USER": json.dumps(admin_login["user"]),
            "UX_TEACHER_TOKEN": teacher_login["access_token"],
            "UX_TEACHER_USER": json.dumps(teacher_login["user"]),
            "UX_ACTIVE_TEACHER_ID": active.id,
            "UX_INACTIVE_TEACHER_ID": inactive.id,
            "UX_LESSON_ID": lesson.id,
            "UX_PLAN_ID": plan.id,
            "UX_SCHEME_ID": scheme.id,
        }
        Path(args.out).write_text(
            "\n".join(f"{key}={shlex.quote(str(value))}" for key, value in env.items()) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"fixtures": "created", "env_file": args.out}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
