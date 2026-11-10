"""Apply the WAPEF visual language to the bundled template and its web copy."""

from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docx import Document
from src.engines.wapef_style import style_wapef_document

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ASSET = ROOT / "backend/src/engines/assets/wapef_approved_plan_template.docx"
FRONTEND_ASSET = ROOT / "frontend/public/docx-templates/wapef_approved_plan_template.docx"


def main() -> None:
    doc = Document(str(BACKEND_ASSET))
    # The approved form's own heading spelling (never rewritten by styling).
    for table in doc.tables[1:]:
        if not table.rows:
            continue
        cell = table.rows[0].cells[0]
        if "PHASE" in (cell.text or "").upper():
            paragraph = cell.paragraphs[0]
            for extra in list(cell.paragraphs)[1:]:
                extra._element.getparent().remove(extra._element)
            runs = list(paragraph.runs)
            first = runs[0] if runs else paragraph.add_run()
            first.text = "PHASE / DURATION  "
            for run in runs[1:]:
                run._element.getparent().remove(run._element)
    style_wapef_document(doc)
    doc.save(str(BACKEND_ASSET))
    FRONTEND_ASSET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BACKEND_ASSET, FRONTEND_ASSET)
    print(f"styled {BACKEND_ASSET}")
    print(f"copied  {FRONTEND_ASSET}")


if __name__ == "__main__":
    main()
