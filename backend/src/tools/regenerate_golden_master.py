"""Regenerate the approved-source golden-master fingerprint.

The golden master (``src/engines/assets/ges_jhs_golden_master.json``) is the
normalized structural contract for the approved JHS lesson-plan form. It is
derived from the bundled source document itself, so it must be regenerated
whenever the source .docx or the analyzer changes::

    python -m src.tools.regenerate_golden_master

The stored fingerprint is then asserted against the live document by
``tests/test_official_ges_template.py::TestGoldenMaster`` so drift is caught.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.engines.official_ges_levels import JHS_SPEC
from src.engines.official_ges_template import template_path
from src.engines.template_analyzer import analyze_docx_sample

ASSETS = Path(__file__).resolve().parent.parent / "engines" / "assets"
OUTPUT = ASSETS / "ges_jhs_golden_master.json"


def regenerate() -> Path:
    source = template_path(JHS_SPEC)
    analysis = analyze_docx_sample(str(source))
    golden = {
        "source_document": source.name,
        "provenance": "approved_organizational",
        "note": ("Structural fingerprint of the approved source document, derived "
                 "from the file itself. Do not hand-edit: regenerate with "
                 "src/tools/regenerate_golden_master.py."),
        "table_count": analysis["meta"]["table_count"],
        "tables": analysis["tables"],
    }
    OUTPUT.write_text(json.dumps(golden, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    return OUTPUT


def main(argv=None) -> int:
    out = regenerate()
    print(f"regenerated {out}")
    print(f"tables={json.loads(out.read_text(encoding='utf-8'))['table_count']}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    raise SystemExit(main())
