"""PDF integrity checks with real PDFs around the tail-read boundary."""

from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter

from utils.pdf_export import PDFValidationError, validate_pdf


def _write_pdf(path, size=None):
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    data = buffer.getvalue()
    if size is not None:
        assert len(data) <= size
        # Whitespace before EOF leaves all object and xref offsets unchanged.
        eof = data.rfind(b"%%EOF")
        data = data[:eof] + b"\n" * (size - len(data)) + data[eof:]
    path.write_bytes(data)


@pytest.mark.parametrize("size", [None, 1023, 1024, 1025])
def test_validate_pdf_accepts_small_and_boundary_sized_pdfs(tmp_path, size):
    path = tmp_path / "valid.pdf"
    _write_pdf(path, size)

    assert len(PdfReader(path).pages) == 1
    if size is None:
        assert path.stat().st_size < 1024
    else:
        assert path.stat().st_size == size
    assert validate_pdf(path) is True


def test_validate_pdf_rejects_truncated_pdf(tmp_path):
    path = tmp_path / "truncated.pdf"
    _write_pdf(path)
    path.write_bytes(path.read_bytes().split(b"%%EOF")[0])

    with pytest.raises(PDFValidationError, match="%%EOF"):
        validate_pdf(path)


@pytest.mark.parametrize(
    "data",
    [b"", b"not a PDF\n%%EOF\n", b"%PDF-1.4\ninvalid PDF objects\n%%EOF\n"],
    ids=["empty", "invalid-header", "unparseable"],
)
def test_validate_pdf_rejects_malformed_pdf(tmp_path, data):
    path = tmp_path / "malformed.pdf"
    path.write_bytes(data)

    with pytest.raises(PDFValidationError):
        validate_pdf(path)
