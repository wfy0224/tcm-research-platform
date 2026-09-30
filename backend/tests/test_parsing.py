import json
import zipfile

import pytest
from pdf_samples import pdf_with_pages, pdf_with_text

from tcm_platform.parsing import OCRRequired, SourceParseError, parse_source_file


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
    text_pdf.write_bytes(pdf_with_text("Hello PDF"))
    assert "Hello PDF" in parse_source_file(text_pdf, "pdf").text

    from pypdf import PdfWriter

    scan_pdf = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with scan_pdf.open("wb") as output:
        writer.write(output)
    with pytest.raises(OCRRequired):
        parse_source_file(scan_pdf, "pdf")


@pytest.mark.parametrize(
    ("texts", "missing_pages"),
    [(("Cover", None), [2]), ((None, "Body"), [1]), (("Cover", "   "), [2])],
)
def test_mixed_pdf_requires_complete_page_review(tmp_path, texts, missing_pages):
    path = tmp_path / "mixed.pdf"
    path.write_bytes(pdf_with_pages(*texts))
    with pytest.raises(OCRRequired) as error:
        parse_source_file(path, "pdf")
    assert error.value.page_numbers == missing_pages
    assert error.value.code == "OCR_REQUIRED"
    assert str(missing_pages[0]) in str(error.value)


def test_text_pdf_preserves_every_physical_page(tmp_path):
    path = tmp_path / "text-pages.pdf"
    path.write_bytes(pdf_with_pages("First", "Second"))
    parsed = parse_source_file(path, "pdf")
    assert [(page.page_no, page.text.strip()) for page in parsed.pages] == [
        (1, "First"), (2, "Second"),
    ]
    assert parsed.warnings == []


def test_zero_page_pdf_is_not_a_parsed_source(tmp_path):
    path = tmp_path / "empty.pdf"
    path.write_bytes(pdf_with_pages())
    with pytest.raises(SourceParseError) as error:
        parse_source_file(path, "pdf")
    assert error.value.code == "EMPTY_TEXT"

