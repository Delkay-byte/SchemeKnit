"""True multi-process generation tests against PostgreSQL.

Every worker is a separate OS process with its own Python interpreter,
SQLAlchemy engine, session factory and FastAPI app. They share only the
PostgreSQL database. This is the evidence the earlier single-process /
single-connection advisory-lock test could not provide.

The tests are skipped unless ``TEACHFLOW_TEST_DATABASE_URL`` points at
PostgreSQL. They never contact production.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
WORKER = Path(__file__).resolve().parent / "pg_worker.py"


def _pg_url():
    url = os.environ.get("TEACHFLOW_TEST_DATABASE_URL", "")
    return url if url.startswith("postgresql") else None


pytestmark = pytest.mark.skipif(
    _pg_url() is None,
    reason="Set TEACHFLOW_TEST_DATABASE_URL to a scratch PostgreSQL database",
)


class Worker:
    """One independent backend process with file-based start synchronisation."""

    def __init__(self, tmp_path, name, mode, user_id, scheme_id,
                 config=None, job_id=None, job_age_minutes=120):
        self.name = name
        self.ready = tmp_path / f"{name}.ready"
        self.go = tmp_path / "go"
        self.result_path = tmp_path / f"{name}.result.json"
        self.log_path = tmp_path / f"{name}.log"
        self.mode = mode
        args = [
            sys.executable, str(WORKER),
            "--mode", mode,
            "--url", _pg_url(),
            "--user", user_id,
            "--scheme", scheme_id,
            "--ready", str(self.ready),
            "--go", str(self.go),
            "--result", str(self.result_path),
            "--job-age-minutes", str(job_age_minutes),
        ]
        if config is not None:
            config_path = tmp_path / f"{name}.config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            args += ["--config", str(config_path)]
        if job_id:
            args += ["--job", job_id]
        self.args = args
        self.proc = None

    def start(self):
        env = os.environ.copy()
        env["DATABASE_URL"] = _pg_url()
        env["PYTHONPATH"] = str(BACKEND_DIR)
        env["AI_MODE"] = "OFF"
        env["DEBUG"] = "true"
        self._log = self.log_path.open("w", encoding="utf-8")
        self.proc = subprocess.Popen(
            self.args,
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        return self

    def wait_ready(self, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ready.exists():
                return self
            if self.proc.poll() is not None:
                raise AssertionError(
                    f"{self.name} exited before ready (rc={self.proc.returncode})"
                    f"\n{self._read_log()}")
            time.sleep(0.05)
        raise AssertionError(
            f"{self.name} did not become ready\n{self._read_log()}")

    def release(self):
        self.go.write_text("go", encoding="utf-8")

    def result(self, timeout=180):
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=30)
            raise AssertionError(
                f"{self.name} timed out\n{self._read_log()}")
        if self.proc.returncode != 0:
            raise AssertionError(
                f"{self.name} exited rc={self.proc.returncode}\n"
                f"{self._read_log()}")
        assert self.result_path.exists(), (
            f"{self.name} produced no result\n{self._read_log()}")
        return json.loads(self.result_path.read_text(encoding="utf-8"))

    def stop(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(timeout=30)
        finally:
            if getattr(self, "_log", None):
                self._log.close()

    def _read_log(self):
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        except OSError:
            return "<no log>"


@pytest.fixture()
def workers(tmp_path):
    started: list[Worker] = []

    def _make(*args, **kwargs):
        worker = Worker(tmp_path, *args, **kwargs).start()
        started.append(worker)
        return worker

    yield _make
    for worker in started:
        worker.stop()


def _scheme(db, owner_id, weeks=2, subject="ICT", class_level="Basic 7"):
    from src.database import SchemeDB, WeekDB, generate_id

    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="multiprocess.docx",
        subject=subject, class_level=class_level, status="approved",
    )
    db.add(scheme)
    db.flush()
    for n in range(1, weeks + 1):
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Computing",
            sub_strand="Hardware",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"B7.1.1.{n}.1 Identify a device"],
            resources=["Chart"],
        ))
    db.commit()
    db.refresh(scheme)
    return scheme


def _config(scheme_id, weeks=2):
    from src.models import TermConfig

    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2, 4], holidays=[], ai_mode="OFF",
        include_special_weeks=False, class_level="Basic 7", subject="ICT",
    )


def _counts(db, user_id, scheme_id):
    from sqlalchemy import func

    from src.database import GenerationJobDB, LessonPlanDB, UsagePeriodDB, UsageUnitDB
    from src.usage_quota import current_period_key

    db.expire_all()
    period_key = current_period_key()
    jobs = db.query(GenerationJobDB).filter(
        GenerationJobDB.owner_id == user_id,
        GenerationJobDB.scheme_id == scheme_id).count()
    lessons = db.query(LessonPlanDB).filter(
        LessonPlanDB.owner_id == user_id,
        LessonPlanDB.scheme_id == scheme_id).count()
    occurrences = db.query(LessonPlanDB.source_occurrence_id).filter(
        LessonPlanDB.owner_id == user_id,
        LessonPlanDB.scheme_id == scheme_id).all()
    units = db.query(UsageUnitDB).filter(
        UsageUnitDB.user_id == user_id,
        UsageUnitDB.period_key == period_key).count()
    period = db.query(UsagePeriodDB).filter(
        UsagePeriodDB.user_id == user_id,
        UsagePeriodDB.period_key == period_key).first()
    return {
        "jobs": jobs,
        "lessons": lessons,
        "occurrences": [row[0] for row in occurrences],
        "units": units,
        "units_used": int(period.units_used or 0) if period else 0,
        "distinct_occurrences": len({
            row[0] for row in occurrences if row[0]
        }),
    }


def test_two_processes_same_scheme_start_exactly_one_run(db, workers, tmp_path):
    """Two independent OS processes, same owner+scheme: one 200, one 409."""
    from tests.conftest import make_user

    user = make_user(db, email="mp-same@test.local")
    scheme = _scheme(db, user.id, weeks=2)
    config = _config(scheme.id, weeks=2).model_dump(mode="json")

    first = workers("same-a", "generate", user.id, scheme.id, config=config)
    second = workers("same-b", "generate", user.id, scheme.id, config=config)
    first.wait_ready()
    second.wait_ready()
    first.release()

    results = [first.result(), second.result()]
    statuses = sorted(result["status"] for result in results)
    assert statuses == [200, 409], (
        f"exactly one process may run; got {results}")

    loser = next(r for r in results if r["status"] == 409)
    assert "already running" in json.dumps(loser["body"]).lower()

    counts = _counts(db, user.id, scheme.id)
    assert counts["jobs"] == 1, "the refused process must not create a job"
    assert counts["lessons"] > 0
    assert counts["distinct_occurrences"] == counts["lessons"], (
        "a source occurrence was generated twice: "
        f"{counts['occurrences']}")
    assert counts["units"] == 2, "one unit per scheme indicator code"
    assert counts["units_used"] == 2


def test_two_processes_can_generate_different_schemes_concurrently(
        db, workers, tmp_path):
    from tests.conftest import make_user

    user = make_user(db, email="mp-different@test.local")
    scheme_a = _scheme(db, user.id, weeks=2)
    scheme_b = _scheme(db, user.id, weeks=2)
    config_a = _config(scheme_a.id, weeks=2).model_dump(mode="json")
    config_b = _config(scheme_b.id, weeks=2).model_dump(mode="json")

    first = workers("diff-a", "generate", user.id, scheme_a.id, config=config_a)
    second = workers("diff-b", "generate", user.id, scheme_b.id, config=config_b)
    first.wait_ready()
    second.wait_ready()
    first.release()

    results = [first.result(), second.result()]
    assert [r["status"] for r in results] == [200, 200], results

    from src.database import UsageUnitDB

    counts_a = _counts(db, user.id, scheme_a.id)
    counts_b = _counts(db, user.id, scheme_b.id)
    assert counts_a["jobs"] == 1 and counts_b["jobs"] == 1
    assert counts_a["lessons"] > 0 and counts_b["lessons"] > 0
    current_units = db.query(UsageUnitDB).filter_by(user_id=user.id).count()
    assert current_units == 4, (
        "two schemes x two indicator codes must charge four units, no more")
    assert counts_a["distinct_occurrences"] == counts_a["lessons"]
    assert counts_b["distinct_occurrences"] == counts_b["lessons"]


def test_advisory_lock_is_released_when_a_worker_process_is_killed(
        db, db_engine, workers, tmp_path):
    """A crashed worker cannot strand the scheme behind a session lock."""
    from sqlalchemy import text

    from src.routers.generation import generation_lock_key
    from tests.conftest import make_user

    user = make_user(db, email="mp-kill@test.local")
    scheme = _scheme(db, user.id, weeks=1)
    config = _config(scheme.id, weeks=1).model_dump(mode="json")
    key = generation_lock_key(user.id, scheme.id)

    holder = workers("holder", "hold-lock", user.id, scheme.id)
    holder.wait_ready()

    probe = db_engine.connect()
    try:
        assert probe.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": key}
        ).scalar() is False, "the holder process did not take the lock"
    finally:
        probe.close()

    holder.proc.kill()
    holder.proc.wait(timeout=30)

    released = None
    probe = db_engine.connect()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            released = probe.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": key}
            ).scalar()
            if released:
                probe.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                probe.commit()
                break
            time.sleep(0.1)
    finally:
        probe.close()
    assert released is True, (
        "PostgreSQL did not release the advisory lock after process death")

    replacement = workers("replacement", "generate", user.id, scheme.id,
                          config=config)
    replacement.wait_ready()
    replacement.release()
    result = replacement.result()
    assert result["status"] == 200, result
    counts = _counts(db, user.id, scheme.id)
    assert counts["lessons"] > 0
    assert counts["units"] == 1


def test_second_process_resumes_a_job_whose_worker_died(
        db, workers, tmp_path):
    """A killed worker leaves a stale processing job; a peer resumes it."""
    from tests.conftest import make_user
    from src.database import GenerationJobDB, LessonPlanDB, generate_id
    from src.models import TermConfig
    from src.routers import generation as gen_router
    from src.service import data_service

    user = make_user(db, email="mp-resume@test.local")
    scheme = _scheme(db, user.id, weeks=2)
    config = _config(scheme.id, weeks=2)

    scheme_model = data_service.scheme_to_model(scheme)
    allocations = gen_router._allocations_for_config(scheme_model, config)
    planned = [
        a.source_occurrence_id for a in allocations
        if a.source_occurrence_id
    ]
    assert len(planned) >= 2, planned

    snapshot = config.model_dump(mode="json")
    snapshot["planned_occurrence_ids"] = planned
    job = GenerationJobDB(
        id=generate_id(), owner_id=user.id, scheme_id=scheme.id,
        status="processing",
        created_at=datetime.utcnow() - timedelta(minutes=120),
        config_snapshot=snapshot,
    )
    db.add(job)

    # A lesson the teacher already had before the crashed worker ran. Resume
    # must never delete or rewrite it just because the job was reclaimed.
    preserved_id = generate_id()
    preserved_occurrence = "pre-existing-lesson-before-worker-crash"
    db.add(LessonPlanDB(
        id=preserved_id, job_id=job.id, owner_id=user.id,
        scheme_id=scheme.id, week_number=99, lesson_sequence=1,
        class_level="Basic 7", subject="ICT",
        source_occurrence_id=preserved_occurrence,
        lesson_topic="Existing lesson that must survive recovery",
    ))
    db.commit()

    dying = workers("dying", "hold-lock", user.id, scheme.id,
                    job_id=job.id, job_age_minutes=120)
    dying.wait_ready()
    dying.proc.kill()
    dying.proc.wait(timeout=30)

    recovery = workers("recovery", "resume", user.id, scheme.id,
                       job_id=job.id)
    recovery.wait_ready()
    recovery.release()
    result = recovery.result()

    assert result["status"] == 200, result
    body = result["body"]
    assert body["resumed"] is True
    assert body["job_id"] == job.id, "resume must reuse the durable job"
    assert body["status"] == "completed"

    db.expire_all()
    recovered = db.query(GenerationJobDB).filter(
        GenerationJobDB.id == job.id).one()
    assert recovered.status == "completed"
    assert recovered.completed_at is not None

    preserved = db.query(LessonPlanDB).filter(
        LessonPlanDB.id == preserved_id).one_or_none()
    assert preserved is not None, "recovery deleted an existing lesson"
    assert preserved.source_occurrence_id == preserved_occurrence
    assert preserved.lesson_topic == "Existing lesson that must survive recovery"

    counts = _counts(db, user.id, scheme.id)
    assert counts["jobs"] == 1
    assert counts["lessons"] == len(planned) + 1, (
        f"expected {len(planned)} resumed lessons plus the existing one, "
        f"got {counts['lessons']}")
    generated_occurrences = set(counts["occurrences"]) - {preserved_occurrence}
    assert generated_occurrences <= set(planned)
    assert len(generated_occurrences) == len(planned)
    assert counts["distinct_occurrences"] == counts["lessons"]
    assert counts["units"] == 2


def test_retry_after_successful_commit_does_not_duplicate_or_recharge(
        db, workers, tmp_path):
    """A lost response followed by a retry is safe across process boundaries."""
    from tests.conftest import make_user

    user = make_user(db, email="mp-retry@test.local")
    scheme = _scheme(db, user.id, weeks=2)
    config = _config(scheme.id, weeks=2).model_dump(mode="json")

    first = workers("retry-a", "generate", user.id, scheme.id, config=config)
    first.wait_ready()
    first.release()
    first_result = first.result()
    assert first_result["status"] == 200, first_result
    before = _counts(db, user.id, scheme.id)

    retry = workers("retry-b", "generate", user.id, scheme.id, config=config)
    retry.wait_ready()
    retry.release()
    retry_result = retry.result()
    assert retry_result["status"] == 200, retry_result
    after = _counts(db, user.id, scheme.id)

    assert after["lessons"] == before["lessons"], (
        "the retry duplicated lessons or dropped the existing set")
    assert after["distinct_occurrences"] == after["lessons"]
    assert after["units"] == before["units"] == 2
    assert after["units_used"] == 2, "the retry charged quota twice"
