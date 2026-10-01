"""Regressions for the complete-text demonstration, without model calls."""
from tcm_platform.parsing import ParsedDocument, ParsedPage
from tcm_platform.segmentation import resolve_structure


def paragraphs(text, *, file_format="txt", pages=None):
    return [row for row in resolve_structure(
        ParsedDocument(file_format, pages or [ParsedPage(1, text)], "utf-8", []),
        title="演示复现",
    ) if row.segment_type not in {"BOOK", "SENTENCE"}]


def test_wrapped_chinese_sentence_survives_blank_physical_lines():
    text = "原始社会时期，我们的祖先就在生活实践中逐渐发现了药物。最初只是用单味药治病，经\n\n过长期的经验积累，形成了方剂。\n\n下一段已经完整。"
    rows = paragraphs(text)
    assert len(rows) == 2
    assert "经过长期" in rows[0].original_text.replace("\n", "")
    assert rows[1].original_text == "下一段已经完整。"
    assert rows[0].structural_locator["line_start"] == 1
    assert rows[0].structural_locator["line_end"] == 3


def test_headings_lists_and_unpunctuated_short_classical_lines_stay_separate():
    text = "第一章\n第一节\n【组成】麻黄三两\n【用法】水煎服\n1、第一项\n2、第二项\n太阳之为病\n脉浮头项强痛"
    rows = paragraphs(text)
    assert [row.original_text for row in rows] == text.splitlines()


def test_pdf_continuation_records_both_physical_pages():
    first = "这是一个用于验证分页续句和引号归属的较长段落，原文应按顺序完整保留，经过"
    rows = paragraphs("", file_format="pdf", pages=[ParsedPage(1, first), ParsedPage(2, "长期积累形成经验。\n下一段。")])
    assert len(rows) == 2
    assert rows[0].structural_locator["page_end"] == 2
    assert "经过长期" in rows[0].original_text.replace("\n", "")


def test_long_paragraph_and_closing_quotes_lose_no_characters():
    text = "引文：“" + "原文内容，" * 100 + "完整。”下一句。"
    document = ParsedDocument("txt", [ParsedPage(1, text)], "utf-8", [])
    rows = resolve_structure(document, title="长段")
    parent = next(row for row in rows if row.segment_type == "PARAGRAPH")
    children = [row for row in rows if row.segment_type == "SENTENCE"]
    assert parent.original_text == text
    assert "".join(row.original_text for row in children) == text
    assert children[0].original_text.endswith("。”")


def test_docx_authoritative_paragraphs_survive_artifact_roundtrip(tmp_path):
    import zipfile
    from io import BytesIO

    from tcm_platform.parsing import parse_source_file
    from tcm_platform.segment_service import _load_parsed
    from tcm_platform.storage import ContentAddressedStore

    first = "这是一个在句中换行的较长段落，必须合并这个段落内部的换行，经过"
    second = "这是另一自然段，即使上一段没有句号也不能合并"
    path = tmp_path / "paragraphs.docx"
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body><w:p><w:r><w:t>{first}</w:t><w:br/><w:t>长期积累</w:t></w:r></w:p>'
           f'<w:p><w:r><w:t>{second}</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    parsed = parse_source_file(path, "docx")
    store = ContentAddressedStore(tmp_path / "store")
    artifact = store.put(BytesIO(parsed.to_bytes()))
    restored = _load_parsed(store, artifact.sha256)
    rows = paragraphs("", file_format="docx", pages=restored.pages)
    assert [row.original_text for row in rows] == [first + "\n长期积累", second]
