"""DOCX/PDF upload-container security tests."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.routers.documents import (  # noqa: E402
    _validate_docx_archive, _validate_pdf_signature,
)


def _valid_docx() -> bytes:
    from docx import Document
    doc = Document()
    doc.add_paragraph("Scheme of Learning")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _zip(entries: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compression) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_valid_docx_passes():
    _validate_docx_archive(_valid_docx())


def test_bad_signature_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_docx_archive(b"not a zip")
    assert exc.value.status_code == 400


def test_malformed_zip_rejected():
    with pytest.raises(HTTPException):
        _validate_docx_archive(b"PK\x03\x04broken")


def test_missing_container_parts_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_docx_archive(_zip({"word/document.xml": b"<x/>"}))
    assert "incomplete" in exc.value.detail.lower()


def test_macro_enabled_docx_rejected():
    payload = _zip({
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b"<w:document/>",
        "word/vbaProject.bin": b"macro",
    })
    with pytest.raises(HTTPException) as exc:
        _validate_docx_archive(payload)
    assert "macro" in exc.value.detail.lower()


def test_path_traversal_entry_rejected():
    payload = _zip({
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b"<w:document/>",
        "../escape.xml": b"<x/>",
    })
    with pytest.raises(HTTPException) as exc:
        _validate_docx_archive(payload)
    assert "unsafe path" in exc.value.detail.lower()


def test_xml_doctype_or_entity_rejected():
    payload = _zip({
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b'<!DOCTYPE x [<!ENTITY y "z">]><x/>',
    })
    with pytest.raises(HTTPException) as exc:
        _validate_docx_archive(payload)
    assert "xml" in exc.value.detail.lower()


def test_high_compression_ratio_rejected():
    payload = _zip({
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b"<w:document/>",
        "word/bomb.bin": b"0" * (1024 * 1024),
    })
    with pytest.raises(HTTPException) as exc:
        _validate_docx_archive(payload)
    assert "ratio" in exc.value.detail.lower()


def test_pdf_signature():
    _validate_pdf_signature(b"%PDF-1.7\n...")
    with pytest.raises(HTTPException):
        _validate_pdf_signature(b"<html>not pdf</html>")
