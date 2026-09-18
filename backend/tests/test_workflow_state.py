"""
Workflow progress state tests: server-persisted stage derivation.
Stages derive ONLY from stored rows — page visitation plays no role.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.service import compute_workflow_state, WORKFLOW_STAGES


def states(s):
    return {stage["key"]: stage["state"] for stage in s}


def test_stage_keys_in_order():
    s = compute_workflow_state("uploaded", False, False, 0, False)
    assert [x["key"] for x in s] == WORKFLOW_STAGES


def test_initial_state_upload_active():
    st = states(compute_workflow_state("uploaded", False, False, 0, False))
    assert st == {"upload": "completed", "review": "active", "configure": "locked",
                  "generate": "locked", "export": "locked"}


def test_extracted_review_still_active():
    st = states(compute_workflow_state("extracted", False, False, 0, False))
    assert st["upload"] == "completed"
    assert st["review"] == "active"
    assert st["configure"] == "locked"


def test_approved_review_done_configure_active():
    st = states(compute_workflow_state("approved", False, False, 0, False))
    assert st["review"] == "completed"
    assert st["configure"] == "active"
    assert st["generate"] == "locked"
    assert st["export"] == "locked"


def test_job_exists_marks_configure_done():
    st = states(compute_workflow_state("approved", True, False, 0, False))
    assert st["configure"] == "completed"
    assert st["generate"] == "active"


def test_completed_job_without_lessons_not_generated():
    st = states(compute_workflow_state("generating", True, True, 0, False))
    assert st["generate"] == "active"
    assert st["export"] == "locked"


def test_completed_job_with_lessons_marks_generate_done():
    st = states(compute_workflow_state("approved", True, True, 12, False))
    assert st["generate"] == "completed"
    assert st["export"] == "active"


def test_export_completes_all():
    st = states(compute_workflow_state("approved", True, True, 12, True))
    assert set(st.values()) == {"completed"}


def test_incomplete_stages_stay_incomplete():
    # A job alone never completes review or export
    st = states(compute_workflow_state("extracted", True, False, 0, False))
    assert st["review"] == "active"
    assert st["export"] == "locked"


def test_exactly_one_active_unless_done():
    import itertools
    statuses = ["uploaded", "extracted", "approved", "generating", "generated", "completed"]
    for status, hj, jc, lc, he in itertools.product(
            statuses, [False, True], [False, True], [0, 5], [False, True]):
        vals = list(states(compute_workflow_state(status, hj, jc, lc, he)).values())
        actives = vals.count("active")
        if all(v == "completed" for v in vals):
            assert actives == 0
        else:
            assert actives == 1, (status, hj, jc, lc, he, vals)


def test_export_events_persist(db):
    from tests.conftest import make_user, make_school
    from src.service import data_service
    from src.database import SchemeDB, GenerationJobDB, generate_id
    u = make_user(db, role="teacher", email="wf@wf.test")
    school = make_school(db)
    scheme = SchemeDB(id=generate_id(), owner_id=u.id, school_id=school.id,
                      filename="s.docx", subject="Science", class_level="Basic 9")
    db.add(scheme)
    db.commit()
    job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                          status="completed")
    db.add(job)
    db.commit()
    assert data_service.has_export_for_scheme(db, scheme.id, u.id) is False
    data_service.log_export_event(db, job.id, scheme.id, u.id, "docx")
    assert data_service.has_export_for_scheme(db, scheme.id, u.id) is True
    assert data_service.has_export_for_scheme(db, "no-such-scheme", u.id) is False
