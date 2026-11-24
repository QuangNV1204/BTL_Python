
from __future__ import annotations

import io

import pytest

from app.shared.error.exceptions import ApiException
from app.shared.storage.documents import (
    DOCX_TYPE,
    PDF_TYPE,
    TEXT_TYPE,
    extract_text,
)


def _build_pdf(text: str) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 12 Tf 20 250 Td ({text}) Tj ET".encode()
    objects[3] = (
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_position = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _build_docx(text: str) -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extracts_plain_text() -> None:
    assert extract_text("  Nội dung  ".encode(), TEXT_TYPE) == "Nội dung"


def test_extracts_docx() -> None:
    assert extract_text(_build_docx("Bài học DOCX"), DOCX_TYPE) == "Bài học DOCX"


def test_extracts_pdf() -> None:
    assert extract_text(_build_pdf("Noi dung PDF"), PDF_TYPE) == "Noi dung PDF"


def test_empty_text_returns_none() -> None:
    assert extract_text(b"   \n\t ", TEXT_TYPE) is None


def test_invalid_pdf_raises_unsupported() -> None:
    with pytest.raises(ApiException) as exc:
        extract_text(b"not a pdf", PDF_TYPE)
    assert exc.value.code.value == "UNSUPPORTED_FILE_TYPE"
