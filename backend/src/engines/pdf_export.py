"""
SchemeKnit PDF Export Engine

Converts DOCX to PDF using docx2pdf (which drives Microsoft Word on
Windows/macOS) or LibreOffice for cross-platform/server use.

In desktop mode, a bundled LibreOffice runtime is resolved via the
``LIBREOFFICE_PATH`` environment variable (set by main.js).  Each
conversion runs with an isolated user profile so concurrent exports
never collide on lock files.

Hosts with neither Word nor LibreOffice (e.g. Render) do NOT get a
converter here: the API renders the lesson through the structured
ReportLab renderer instead (see ``engines/structured_pdf.py``), which is
why this module no longer carries a PyMuPDF fallback. That fallback
re-extracted TEXT from the DOCX and wrapped it in a PDF, flattening every
table into prose — a text dump rather than a lesson plan.

Failure contract
----------------
PDF export has two distinct failure layers and callers must be able to tell
them apart:

1. No converter backend on this server AND the structured render failed ->
   `PDF_CONVERTER_REQUIREMENT` (reported as 503 by the API).
2. A converter was attempted but the conversion did not yield a real PDF ->
   `PDFConversionError` (reported as 500 with a controlled message).

This module never returns a DOCX path from a PDF entry point. Returning the
intermediate .docx was surfacing as a "PDF download" that the browser saved
with a .docx filename and `Content-Type: application/pdf` — a silently corrupt
file rather than a visible error.
"""

import sys
from pathlib import Path
from typing import List, Optional
import os
import shutil
import subprocess
import tempfile
import threading

#: Word COM automation is process-global: serialize conversions so two export
#: requests can never race each other inside the Word instance.
_WORD_COM_LOCK = threading.Lock()

from ..models import LessonPlan, Template
from .docx_export import DOCXExportEngine

#: Production PDF dependency. DOCX/XLSX/ZIP never need it.
PDF_CONVERTER_REQUIREMENT = (
    "PDF export requires a document converter on the server "
    "(LibreOffice for cross-platform production use)."
)

#: Converter present, conversion attempted, no usable PDF produced.
PDF_CONVERSION_FAILED = (
    "PDF conversion failed on the server. Word (.docx) export is unaffected."
)

#: Every valid PDF begins with this signature (ISO 32000-1 §7.5.2).
_PDF_MAGIC = b"%PDF-"

#: Well-known install locations, so a system LibreOffice that is not on PATH
#: (the normal Windows install) still converts instead of looking missing.
_LIBREOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    r"C:\Program Files\LibreOffice\program\soffice.com",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/usr/lib/libreoffice/program/soffice",
    "/snap/bin/libreoffice",
)

#: Word's App Paths key — present only when Office is installed.
_WORD_APP_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Winword.exe"


class PDFConversionError(RuntimeError):
    """DOCX -> PDF conversion was attempted and did not produce a valid PDF."""


def _resolve_libreoffice() -> Optional[str]:
    """Resolve the soffice executable, preferring the bundled runtime.

    Resolution order:
    1. ``LIBREOFFICE_PATH`` env var (set by desktop main.js).
    2. System ``soffice`` / ``libreoffice`` on PATH.
    3. The standard install locations per platform.
    """
    env_path = os.environ.get("LIBREOFFICE_PATH", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return str(candidate)
        # Maybe the caller pointed at the program/ directory
        candidate = candidate / "soffice.exe"
        if candidate.is_file():
            return str(candidate)
    on_path = shutil.which("libreoffice") or shutil.which("soffice")
    if on_path:
        return on_path
    for candidate in _LIBREOFFICE_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def _word_installed() -> bool:
    """True when Microsoft Word (the docx2pdf backend) is actually present.

    ``import docx2pdf`` succeeds on any machine with the pip package; only the
    registry / app bundle tells us Word itself exists. Without this check
    availability would claim a converter that fails at conversion time.
    """
    if sys.platform == "darwin":
        return any(Path(app).exists() for app in (
            "/Applications/Microsoft Word.app",
            str(Path.home() / "Applications/Microsoft Word.app"),
        ))
    try:
        import winreg
    except Exception:
        return False
    try:
        winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _WORD_APP_PATH).Close()
        return True
    except OSError:
        return False


def _is_real_pdf(path: Path) -> bool:
    """True when `path` exists and starts with the PDF signature.

    Guards against a converter (or a stray copy step) leaving a DOCX or an
    empty file where a PDF was expected.
    """
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        with path.open("rb") as fh:
            return fh.read(len(_PDF_MAGIC)) == _PDF_MAGIC
    except OSError:
        return False


class PDFExportEngine:
    """PDF generation from DOCX."""

    @staticmethod
    def is_available() -> bool:
        """True when a real DOCX -> PDF toolchain exists on this machine.

        Two backends are driven: LibreOffice (any platform) and Word via
        docx2pdf (Windows/macOS only, and only when Word is installed).
        Anything else — including a bare Linux server — reports False so the
        API falls back to the always-available structured renderer.

        Availability is about the *toolchain* only: a backend that is present
        but fails at conversion time raises `PDFConversionError`, which is a
        conversion failure, not an availability failure.
        """
        if _resolve_libreoffice() is not None:
            return True
        if not (sys.platform.startswith("win") or sys.platform == "darwin"):
            return False
        try:
            import docx2pdf  # noqa: F401
        except Exception:
            return False
        return _word_installed()

    def __init__(self):
        self.docx_engine = DOCXExportEngine()

    def export_single(
        self,
        lesson_plan: LessonPlan,
        template: Optional[Template] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Render one lesson plan to PDF. Raises PDFConversionError on failure."""
        if output_path is None:
            output_path = Path(f"lesson_plan_{lesson_plan.id}.pdf")

        docx_path = output_path.with_suffix('.docx')
        try:
            self.docx_engine.export_single(lesson_plan, template, docx_path)
            return self._convert_docx_to_pdf(docx_path, output_path)
        finally:
            # The intermediate DOCX is throwaway in every outcome, success or
            # failure — never leave it behind looking like the export result.
            if docx_path != output_path:
                docx_path.unlink(missing_ok=True)

    def export_batch(
        self,
        lesson_plans: list,
        template: Optional[Template] = None,
        output_dir: Path = Path("exports/pdf"),
    ) -> List[Path]:
        """Render many lesson plans. Returns the PDFs that succeeded.

        Raises PDFConversionError when nothing converted, so a total converter
        outage is reported instead of an empty list.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results: List[Path] = []
        errors: List[str] = []
        for lp in lesson_plans:
            subject = lp.subject.value if hasattr(lp.subject, 'value') else str(lp.subject)
            cls = lp.class_level.value if hasattr(lp.class_level, 'value') else str(lp.class_level)
            date_str = lp.lesson_date.strftime("%Y-%m-%d") if lp.lesson_date else "nodate"
            filename = f"{subject}_{cls}_W{lp.week_number:02d}_L{lp.lesson_sequence:02d}_{date_str}.pdf"
            filepath = output_dir / filename
            try:
                self.export_single(lp, template, filepath)
                results.append(filepath)
            except Exception as e:  # keep going: one bad lesson must not block the batch
                errors.append(f"{filename}: {e}")

        if not results:
            detail = errors[0] if errors else "no lesson plans to convert"
            raise PDFConversionError(detail)
        return results

    def _convert_docx_to_pdf(self, docx_path: Path, pdf_path: Path) -> Path:
        """Convert and verify. Raises PDFConversionError if no valid PDF results."""
        # Explicit labels: `fn.__name__` is unavailable when a backend is
        # patched out in tests, and a label is what an operator needs anyway.
        # Order: Word (desktop maturity) -> LibreOffice (best server fidelity).
        attempts = [
            ("docx2pdf", self._try_docx2pdf),
            ("libreoffice", self._try_libreoffice),
        ]
        errors: List[str] = []

        for label, attempt in attempts:
            try:
                attempt(docx_path, pdf_path)
            except Exception as e:
                errors.append(f"{label}: {e}")
                continue
            if _is_real_pdf(pdf_path):
                return pdf_path
            errors.append(f"{label}: produced no valid PDF")

        # Report EVERY attempt's failure: masking the first behind the last hid
        # the real cause (e.g. a Word COM error surfacing as only
        # "libreoffice: LibreOffice not installed").
        raise PDFConversionError("; ".join(errors) or "no converter backend available")

    def _try_docx2pdf(self, docx_path: Path, pdf_path: Path) -> Path:
        # Word COM is apartment-threaded: CoInitialize must run on the calling
        # thread. Exports execute on executor threads (never the main thread),
        # which is exactly where "CoInitialize has not been called" otherwise
        # aborts the conversion. The lock also serializes Word automation —
        # concurrent conversions can fail each other.
        with _WORD_COM_LOCK:
            import pythoncom
            pythoncom.CoInitialize()
            try:
                from docx2pdf import convert
                convert(str(docx_path), str(pdf_path))
            finally:
                pythoncom.CoUninitialize()
        return pdf_path

    def _try_libreoffice(self, docx_path: Path, pdf_path: Path) -> Path:
        binary = _resolve_libreoffice()
        if not binary:
            raise RuntimeError("LibreOffice not installed")
        # Use an isolated user profile per conversion to prevent lock-file
        # collisions when multiple PDF exports run concurrently.
        profile_dir = tempfile.mkdtemp(prefix="sk_lo_")
        try:
            lo_url = "file:///" + profile_dir.replace("\\", "/")
            cmd = [
                binary,
                "--headless",
                "--norestore",
                "--nofirststartwizard",
                f"-env:UserInstallation={lo_url}",
                "--convert-to", "pdf",
                "--outdir", str(pdf_path.parent),
                str(docx_path),
            ]
            env = os.environ.copy()
            # Point URE_BOOTSTRAP at the bundled program/ dir so LibreOffice
            # can find its share/ data without the "platform independent
            # libraries" warning.  When using a system install this variable
            # is typically not set and soffice finds its prefix automatically.
            lo_program = Path(binary).parent
            bootstrap = lo_program / "fundamentalrc"
            if bootstrap.is_file():
                env["URE_BOOTSTRAP"] = "file:///" + str(bootstrap).replace("\\", "/")
            subprocess.run(cmd, capture_output=True, timeout=120, check=True, env=env)
        finally:
            # Clean up the temporary profile directory
            shutil.rmtree(profile_dir, ignore_errors=True)
        generated = pdf_path.parent / (docx_path.stem + ".pdf")
        if generated.exists():
            if generated != pdf_path:
                generated.replace(pdf_path)
            return pdf_path
        raise RuntimeError("LibreOffice conversion produced no output")
