"""Audit a rendered WAPEF DOCX for the reported quality defects.

Usage:
    python backend/scripts/audit_wapef_docx.py path/to/plan.docx

The audit is intentionally conservative: it reports observable symptoms, not
guesses. It is used with the supplied Basic 7 reproduction document and with a
freshly generated plan to show the before/after difference.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


def _table_text(document) -> str:
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.extend(p.text for p in cell.paragraphs)
    return "\n".join(parts)


def _cell_fill(cell) -> str:
    tc_pr = cell._tc.tcPr
    if tc_pr is None:
        return ""
    shd = tc_pr.find(qn("w:shd"))
    return shd.get(qn("w:fill")) if shd is not None else ""


def _wapef_field_values(document) -> dict[str, str]:
    values = {}
    for table in document.tables:
        for row in table.rows:
            seen = set()
            for cell in row.cells:
                if id(cell._tc) in seen:
                    continue
                seen.add(id(cell._tc))
                text = (cell.text or "").strip()
                for label in ("Through line", "God\u2019s Story", "God's Story",
                              "Deep Hope", "Storyline"):
                    if text.startswith(label):
                        values[label] = text[len(label):].strip(" :\n")
    return values


def audit(path: Path) -> dict:
    document = Document(str(path))
    text = _table_text(document)
    fields = _wapef_field_values(document)
    empty_fields = [label for label, value in fields.items() if not value]

    fragments = re.findall(
        r"\b[A-Za-z]+-(?=\s|$)|\(\s*$|\b(?:and|or|with|using|of|to)\s*\.\s",
        text,
    )
    numeric_splits = re.findall(r"\b\d{1,3}\s*\n\s*000\b", text)
    phase_split = re.findall(r"DURATIO\s*\n\s*N\b", text)
    repeated = len(re.findall(r"1,000,000,000", text))
    style = {
        "header_fill": "",
        "label_fill": "",
    }
    for table in document.tables:
        if not table.rows:
            continue
        fills = {_cell_fill(cell) for cell in table.rows[0].cells}
        if "1A365D" in fills:
            style["header_fill"] = "1A365D"
        if "F2F4F8" in fills:
            style["label_fill"] = "F2F4F8"
    return {
        "path": str(path),
        "wapef_fields": fields,
        "empty_wapef_fields": empty_fields,
        "malformed_fragments": len(fragments),
        "fragment_examples": fragments[:8],
        "numeric_splits": len(numeric_splits),
        "phase_heading_splits": len(phase_split),
        "indicator_mentions": repeated,
        "style": style,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    result = audit(args.path)
    for key, value in result.items():
        print(f"{key}: {value}")
    problems = (
        len(result["empty_wapef_fields"])
        + result["malformed_fragments"]
        + result["numeric_splits"]
        + result["phase_heading_splits"]
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
