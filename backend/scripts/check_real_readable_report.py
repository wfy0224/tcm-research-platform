"""Read-only checks of readable exports using the actual saved research records."""

import io
import json
import os
import re
import zipfile
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.engine.url import make_url

os.environ["TCM_DATABASE_URL"] = make_url(os.environ["TCM_DATABASE_URL"]).set(
    database="tcm_vib62_workspace_test").render_as_string(hide_password=False)

from tcm_platform.db import SessionLocal
from tcm_platform.models import ResearchTask, StructuredReport
from tcm_platform.report_export import (
    W,
    _digest,
    _process_snapshot,
    render_docx,
    render_markdown,
    report_blocks,
)

opaque = re.compile(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b|\b[0-9a-f]{64}\b")
results = []
with SessionLocal() as session:
    for public_id in ("RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940",
                      "RT-01a0f788-b1a8-7cee-9e52-7cee5d555a58",
                      "RT-01a0f73b-04e1-7c42-bd42-2c21c469f744"):
        task = session.scalar(select(ResearchTask).where(ResearchTask.public_id == public_id))
        reports = list(session.scalars(select(StructuredReport).where(
            StructuredReport.task_id == task.id).order_by(StructuredReport.revision_no)))
        for report in reports:
            original_hash = report.content_hash
            process = {**_process_snapshot(session, task.id),
                       "report_metadata": {"revision_no": report.revision_no}}
            blocks = report_blocks(report.content, process)
            assert not opaque.search("\n".join(b.text for b in blocks))
            anchors = {block.anchor for block in blocks if block.anchor}
            assert all(block.link in anchors for block in blocks if block.link)
            assert len(anchors) == sum(bool(block.anchor) for block in blocks)
            # Keep every original excerpt and accepted/rejected answer unchanged.
            quotes = {e["quote_text"] for rows in report.content["sections"].values()
                      for finding in rows for e in finding["evidence"]}
            assert quotes <= {block.text for block in blocks if block.style == "Quote"}
            if report.content.get("answer"):
                assert all(p["text"] in {b.text for b in blocks}
                           for p in report.content["answer"]["paragraphs"])
            assert sum(b.style == "Heading2" and b.text.startswith("质疑 ")
                       for b in blocks) == len(process["critiques"])
            assert sum(b.style == "Heading2" and b.text.startswith("回应 ")
                       for b in blocks) == len(process["rebuttals"])
            markdown = render_markdown(report.content, process).decode()
            assert "报告编号：" not in markdown and "运行指纹" not in markdown
            with zipfile.ZipFile(io.BytesIO(render_docx(report.content, process))) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
                visible = "\n".join(root.itertext())
                assert not opaque.search(visible)
                bookmarks = {node.attrib[f"{{{W}}}name"]
                             for node in root.iter(f"{{{W}}}bookmarkStart")}
                assert all(node.attrib[f"{{{W}}}anchor"] in bookmarks
                           for node in root.iter(f"{{{W}}}hyperlink"))
            assert _digest(report.content) == original_hash
            results.append({"task": public_id, "revision": report.revision_no,
                            "visible_ids": 0, "valid_links": sum(bool(b.link) for b in blocks),
                            "quotes_preserved": len(quotes), "report_hash_unchanged": True})
print(json.dumps({"checks": results}, ensure_ascii=False))
