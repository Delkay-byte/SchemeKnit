"""
SchemeKnit ZIP Export Engine

Bundles multiple lesson plan files into a single ZIP archive.
"""

from pathlib import Path
from typing import List, Optional
import zipfile

from ..models import LessonPlan, Template
from .docx_export import DOCXExportEngine
from .template_engine import get_template_by_type
from ..models import TemplateType


class ZIPExportEngine:
    """ZIP archive generation for batch lesson plans."""

    def __init__(self):
        self.docx_engine = DOCXExportEngine()

    def export_batch(
        self,
        lesson_plans: List[LessonPlan],
        output_path: Path,
        template_type: TemplateType = TemplateType.GES_STYLE,
        structure: Optional[dict] = None,
        context: Optional[dict] = None,
        template: Optional[Template] = None,
    ) -> Path:
        # A structure (custom/approved sample) drives rendering when present;
        # otherwise the caller's chosen built-in template is used, falling back
        # to the default for the type when the caller named none.
        template = None if structure else (template or get_template_by_type(template_type))
        temp_dir = output_path.parent / "temp_zip"
        temp_dir.mkdir(parents=True, exist_ok=True)

        generated_files = []
        for lp in lesson_plans:
            filename = self.docx_engine._make_filename(
                lp,
                "{subject}_{class}_W{week:02d}_L{lesson:02d}_{date}"
            )
            filepath = temp_dir / filename
            if structure:
                self.docx_engine.export_single_custom(lp, structure, filepath, context)
            else:
                self.docx_engine.export_single(lp, template, filepath)
            generated_files.append(filepath)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(output_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in generated_files:
                zf.write(str(f), f.name)

        for f in generated_files:
            f.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(str(temp_dir), ignore_errors=True)

        return output_path
