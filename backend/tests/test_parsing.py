import json
import zipfile

import pytest

from tcm_platform.parsing import OCRRequired, SourceParseError, parse_source_file


def _pdf_with_text(text: str) -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    )
    return bytes(result)


def test_txt_preserves_chinese_and_encoding(tmp_path):
    path = tmp_path / "classic.txt"
    path.write_bytes("太阳之为病，脉浮。\r\n第二条。".encode("gb18030"))
    parsed = parse_source_file(path, "txt")
    assert parsed.text == "太阳之为病，脉浮。\n第二条。"
    assert parsed.warnings == ["encoding_fallback_gb18030"]
    assert json.loads(parsed.to_bytes())["pages"][0]["page_no"] == 1


def test_docx_extracts_paragraphs_without_losing_original_order(tmp_path):
    path = tmp_path / "source.docx"
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>第一段</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>第二段</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    assert parse_source_file(path, "docx").text == "第一段\n第二段"


def test_docx_rejects_unsafe_archive_entries(tmp_path):
    path = tmp_path / "unsafe.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("../outside.txt", "unsafe")
    with pytest.raises(SourceParseError, match="unsafe entry path"):
        parse_source_file(path, "docx")


def test_pdf_text_layer_and_scan_boundary(tmp_path):
    text_pdf = tmp_path / "text.pdf"
    text_pdf.write_bytes(_pdf_with_text("Hello PDF"))
    assert "Hello PDF" in parse_source_file(text_pdf, "pdf").text

    from pypdf import PdfWriter

    scan_pdf = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with scan_pdf.open("wb") as output:
        writer.write(output)
    with pytest.raises(OCRRequired):
        parse_source_file(scan_pdf, "pdf")

