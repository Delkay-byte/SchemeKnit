"""Static contracts for the teacher upload privacy notice.

These tests pin the owner's exact wording and the upload-page placement so a
later refactor cannot quietly remove or soften the notice. Browser-level
visibility and mobile layout are exercised by
``frontend/e2e/upload-privacy-notice.js`` against a running build.
"""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
UPLOAD_PAGE = FRONTEND / "src/app/(app)/upload/page.tsx"
NOTICE_COMPONENT = FRONTEND / "src/components/upload-privacy-notice.tsx"

EXACT_NOTICE = (
    "Upload curriculum and teaching documents only. Please do not include "
    "pupils' names, personal information, grades or other identifiable student "
    "records. SchemeKnit is a teacher lesson-planning tool, not a student "
    "records management system."
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_notice_component_contains_exact_wording():
    component = _text(NOTICE_COMPONENT)
    assert EXACT_NOTICE in component
    assert "data-upload-privacy-notice" in component
    assert 'role="note"' in component
    assert "aria-labelledby" in component


def test_upload_page_renders_notice_before_dropzone():
    page = _text(UPLOAD_PAGE)
    assert "UploadPrivacyNotice" in page
    notice_at = page.index("<UploadPrivacyNotice />")
    dropzone_at = page.index("data-dropzone")
    assert notice_at < dropzone_at, "notice must precede the dropzone"
    # The notice lives in the pre-upload branch, not only after a successful
    # upload. The idle branch starts at the Dropzone comment.
    idle_branch = page.index("{/* Privacy notice")
    assert idle_branch < notice_at < dropzone_at
    assert "api.uploadScheme(file)" in page
    assert 'accept=".docx,.pdf"' in page
    assert "Upload &amp; Process" in page


def test_notice_is_responsive_and_readable():
    component = _text(NOTICE_COMPONENT)
    # Mobile-first padding that grows at the sm breakpoint.
    assert "px-4 py-4" in component
    assert "sm:px-5" in component
    # Long words and narrow screens must wrap instead of forcing overflow.
    assert "min-w-0" in component
    assert "break-words" in component
    assert "text-sm" in component
    assert "leading-relaxed" in component


def test_upload_page_is_the_only_scheme_upload_entry_point():
    """A Scheme of Learning upload must always show the notice.

    The templates page accepts a DOCX template, not a Scheme of Learning, so
    it is not a curriculum upload entry point. Any new scheme uploader must
    reuse ``UploadPrivacyNotice`` or this contract fails.
    """
    callers = [
        path
        for path in (FRONTEND / "src").rglob("*.tsx")
        if ".uploadScheme(" in _text(path)
    ]
    assert callers == [UPLOAD_PAGE]

    pages_with_scheme_accept = [
        path
        for path in (FRONTEND / "src").rglob("*.tsx")
        if 'accept=".docx,.pdf"' in _text(path)
    ]
    assert pages_with_scheme_accept == [UPLOAD_PAGE]
