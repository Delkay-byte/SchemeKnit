"""
SchemeKnit PDF Export Engine

Converts DOCX to PDF using docx2pdf (which drives Microsoft Word on
Windows/macOS) or LibreOffice for cross-platform/server use.

In desktop mode, a bundled LibreOffice runtime is resolved via the
``LIBREOFFICE_PATH`` environment variable (set by main.js).  Each
conversion runs with an isolated user profile so concurrent exports
never collide on lock files.

Failure contract
----------------
PDF export has two distinct failure layers and callers must be able to tell
them apart:

1. The converter is not installed on this server -> `PDF_CONVERTER_REQUIREMENT`
   (reported as 503 by the API).
2. The converter is present but the conversion did not yield a real PDF ->
   `PDFConversionError` (reported as 500 with a controlled message).

This module never returns a DOCX path from a PDF entry point. Returning the
intermediate .docx was surfacing as a "PDF download" that the browser saved
with a .docx filename and `Content-Type: application/pdf` — a silently corrupt
file rather than a visible error.
"""

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


class PDFConversionError(RuntimeError):
    """DOCX -> PDF conversion was attempted and did not produce a valid PDF."""


def _resolve_libreoffice() -> Optional[str]:
    """Resolve the soffice executable, preferring the bundled runtime.

    Resolution order:
    1. ``LIBREOFFICE_PATH`` env var (set by desktop main.js).
    2. System ``soffice`` / ``libreoffice`` on PATH.
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
    return shutil.which("libreoffice") or shutil.which("soffice")


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
        """True when at least one converter backend exists on this machine.

        Availability is about the *toolchain* only. Note that on Windows
        docx2pdf additionally requires Microsoft Word to be installed and will
        raise at conversion time if it is not — which is a conversion failure,
        not an availability failure.
        """
        try:
            import docx2pdf  # noqa: F401
            return True
        except Exception:
            pass
        return _resolve_libreoffice() is not None

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
