"""Structural fingerprint tool for lesson-plan DOCX documents.

Dumps the normalized topology of a .docx (table count, order, row/column
counts, merged-cell map, cell widths, labels, phase markers) so an approved
source document and a generated document can be compared structurally.

Run:

    python -m src.tools.docx_structure <file.docx> [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document  # type: ignore
from docx.oxml.ns import qn  # type: ignore
from docx.table import Table  # type: ignore


def _cell_grid(tc) -> Optional[Dict[str, Any]]:
    """Grid position/size of one ``<w:tc>`` from its tcPr."""
    tc_pr = tc.tcPr
    if tc_pr is None:
        return None
    grid_span = tc_pr.find(qn("w:gridSpan"))
    v_merge = tc_pr.find(qn("w:vMerge"))
    return {
        "grid_span": int(grid_span.get(qn("w:val"))) if grid_span is not None else 1,
        "v_merge": (v_merge.get(qn("w:val")) if v_merge is not None
                    else ("continue" if v_merge is not None else None)),
    }


def _row_cells(tr) -> List[Any]:
    return [tc for tc in tr.findall(qn("w:tc"))]


def _tc_width(tc) -> Optional[float]:
    tc_pr = tc.tcPr
    if tc_pr is None:
        return None
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        return None
    val = tc_w.get(qn("w:w"))
    return float(val) if val is not None else None


def _table_grid_cols(table) -> int:
    """Column count from the ``<w:tblGrid>`` (authoritative grid width)."""
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        return len(grid.findall(qn("w:gridCol")))
    return len(table.columns)


def fingerprint_table(table: Table, index: int) -> Dict[str, Any]:
    """Normalized fingerprint of one table."""
    tbl = table._tbl
    rows_xml = tbl.findall(qn("w:tr"))
    grid_cols = _table_grid_cols(table)

    rows_out: List[Dict[str, Any]] = []
    merge_events: List[str] = []
    h_merges = 0
    v_merges = 0

    for r_idx, tr in enumerate(rows_xml):
        tcs = _row_cells(tr)
        cells_out: List[Dict[str, Any]] = []
        col_cursor = 0
        for tc in tcs:
            info = _cell_grid(tc) or {"grid_span": 1, "v_merge": None}
            span = info["grid_span"]
            vm = info["v_merge"]
            text = "\n".join(p.text for p in _tc_paragraphs(tc)).strip()
            cells_out.append({
                "r": r_idx,
                "grid_c_start": col_cursor,
                "grid_span": span,
                "v_merge": vm,
                "width_twips": _tc_width(tc),
                "text": text,
            })
            if span > 1:
                merge_events.append(f"r{r_idx}:c{col_cursor} h-span={span}")
                h_merges += 1
            if vm == "continue":
                merge_events.append(f"r{r_idx}:c{col_cursor} v-continue")
                v_merges += 1
            elif vm == "restart":
                merge_events.append(f"r{r_idx}:c{col_cursor} v-restart")
                v_merges += 1
            col_cursor += span
        rows_out.append({
            "row": r_idx,
            "tc_count": len(tcs),
            "grid_width": col_cursor,
            "cells": cells_out,
        })

    # The python-docx .rows/.cells view collapses merges; report it too because
    # that is what a renderer using the high-level API actually sees.
    grid_view: List[List[str]] = []
    try:
        for row in table.rows:
            grid_view.append([_norm(c.text) for c in row.cells])
    except Exception:
        pass

    return {
        "index": index,
        "grid_cols": grid_cols,
        "row_count": len(rows_xml),
        "horizontal_merges": h_merges,
        "vertical_merge_events": v_merges,
        "merge_events": merge_events,
        "rows": rows_out,
        "grid_view": grid_view,
    }


def _tc_paragraphs(tc):
    from docx.text.paragraph import Paragraph  # type: ignore
    return [Paragraph(p, tc) for p in tc.findall(qn("w:p"))]


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def fingerprint_document(path) -> Dict[str, Any]:
    """Full normalized structural fingerprint of a .docx file."""
    document = Document(str(path))
    tables = [fingerprint_table(t, i) for i, t in enumerate(document.tables)]

    paragraphs = []
    for p in document.paragraphs:
        text = _norm(p.text)
        if text:
            paragraphs.append({"style": p.style.name if p.style else "",
                               "text": text})

    return {
        "file": str(path),
        "table_count": len(tables),
        "paragraph_count": len(paragraphs),
        "paragraphs": paragraphs,
        "tables": tables,
    }


def _print_fingerprint(fp: Dict[str, Any], out=None) -> None:
    out = out or sys.stdout
    print(f"FILE: {fp['file']}", file=out)
    print(f"tables = {fp['table_count']}  body paragraphs = {fp['paragraph_count']}",
          file=out)
    for p in fp["paragraphs"]:
        style = f" [{p['style']}]" if p["style"] and p["style"] != "Normal" else ""
        print(f"  P{style}: {p['text'][:120]}", file=out)
    for t in fp["tables"]:
        print("", file=out)
        print(f"TABLE {t['index']}: rows={t['row_count']} "
              f"grid_cols={t['grid_cols']} "
              f"h_merges={t['horizontal_merges']} "
              f"v_merge_events={t['vertical_merge_events']}", file=out)
        for row in t["rows"]:
            print(f"  row {row['row']}: tc={row['tc_count']} "
                  f"grid_width={row['grid_width']}", file=out)
            for cell in row["cells"]:
                tag = ""
                if cell["grid_span"] > 1:
                    tag += f" HSPAN={cell['grid_span']}"
                if cell["v_merge"]:
                    tag += f" VMERGE={cell['v_merge']}"
                w = cell["width_twips"]
                if w is not None:
                    tag += f" w={w:g}"
                text = cell["text"].replace("\n", " / ")[:90]
                print(f"    c{cell['grid_c_start']}{tag}: {text!r}", file=out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help=".docx file to fingerprint")
    parser.add_argument("--json", metavar="OUT", help="write JSON fingerprint")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        print(f"not found: {path}", file=sys.stderr)
        return 2
    fp = fingerprint_document(path)
    _print_fingerprint(fp)
    if args.json:
        Path(args.json).write_text(json.dumps(fp, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
