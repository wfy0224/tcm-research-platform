"""Synthetic materials exercise integrity only, never genuine corpus acceptance."""

import json
import runpy
import sys
from pathlib import Path

import pytest

from tcm_platform.corpus_preflight import (
    BLOCKERS,
    CANONICALIZATION,
    canonical_text,
    check_candidate_bundle,
    text_sha256,
)


@pytest.fixture
def candidate(tmp_path):
    source = "合成测试标题\n甲😀乙。\n另一行\n"
    excerpt = "甲😀乙。\n"
    start = source.index(excerpt)
    files = {
        "upstream.txt": (source, "UPSTREAM_TEXT"),
        "excerpt.txt": (excerpt, "EXCERPT"),
        "rights.txt": ("合成权利测试材料，仅测试完整性。\n", "RIGHTS_NOTICE"),
    }
    artifacts = []
    for name, (text, role) in files.items():
        # The byte hashes intentionally differ from the canonical hashes.
        (tmp_path / name).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        artifacts.append({
            "file": name,
            "role": role,
            "canonicalization": CANONICALIZATION,
            "canonical_sha256": text_sha256(text),
        })
    manifest = {
        "schema_version": "c02-candidate/v1",
        "selection_status": "PROPOSED",
        "data_owner_role": "测试人员",
        "expert_review_status": "PENDING",
        "outbound_authorized": False,
        "source_url": "https://zh.wikisource.org/wiki/合成材料",
        "revision_url": "https://zh.wikisource.org/w/index.php?title=合成材料&oldid=123",
        "upstream_revision_id": 123,
        "section": "合成测试章节",
        "rights_basis": "合成材料，不作真实权利断言",
        "license_notice_url": "https://zh.wikisource.org/wiki/版权说明",
        "physical_page_mapping": None,
        "artifacts": artifacts,
        "excerpts": [{
            "file": "excerpt.txt",
            "source_file": "upstream.txt",
            "source_start": start,
            "source_end": start + len(excerpt),
            "text_sha256": text_sha256(excerpt),
        }],
    }
    save_manifest(tmp_path, manifest)
    return tmp_path, manifest


def save_manifest(bundle, manifest):
    (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def test_complete_synthetic_bundle_is_integrity_valid_but_not_accepted(candidate):
    bundle, _ = candidate
    report = check_candidate_bundle(bundle)
    assert report["structural_valid"] is True
    assert report["acceptance_ready"] is False
    assert report["blockers"] == BLOCKERS
    assert report["verification_scope"] == "LOCAL_MATERIAL_INTEGRITY_ONLY"
    assert report["errors"] == []


@pytest.mark.parametrize("field,value", [
    ("schema_version", "c02-candidate/v2"),
    ("selection_status", "APPROVED"),
    ("data_owner_role", "专家"),
    ("expert_review_status", "APPROVED"),
    ("outbound_authorized", True),
    ("outbound_authorized", 0),
    ("physical_page_mapping", []),
    ("rights_basis", ""),
    ("section", ""),
    ("source_url", "http://zh.wikisource.org/wiki/合成材料"),
    ("source_url", "https://[broken"),
    ("license_notice_url", None),
    ("upstream_revision_id", "123"),
    ("revision_url", "https://zh.wikisource.org/wiki/合成材料"),
    ("revision_url", "https://zh.wikisource.org/wiki/合成材料?oldid=124"),
    ("revision_url", "https://zh.wikisource.org/wiki/合成材料?oldid=123&oldid="),
    ("revision_url", "https://elsewhere.test/wiki/合成材料?oldid=123"),
    ("revision_url", "https://zh.wikisource.org/wiki/另一页?oldid=123"),
])
def test_invalid_metadata_is_reported(candidate, field, value):
    bundle, manifest = candidate
    manifest[field] = value
    save_manifest(bundle, manifest)
    report = check_candidate_bundle(bundle)
    assert report["structural_valid"] is False
    assert report["errors"]
    assert report["acceptance_ready"] is False


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "C:\\outside.txt"])
def test_artifact_path_escape_is_rejected(candidate, name):
    bundle, manifest = candidate
    manifest["artifacts"][0]["file"] = name
    save_manifest(bundle, manifest)
    assert check_candidate_bundle(bundle)["structural_valid"] is False


def test_symlink_escape_is_rejected(candidate, tmp_path):
    bundle, manifest = candidate
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = bundle / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable on this host; escape case unverified")
    manifest["artifacts"][0]["file"] = "escape.txt"
    save_manifest(bundle, manifest)
    report = check_candidate_bundle(bundle)
    assert any("escapes bundle" in error for error in report["errors"])


@pytest.mark.parametrize("damage", ["missing", "non_utf8", "hash", "canonicalization", "empty"])
def test_artifact_integrity_failures(candidate, damage):
    bundle, manifest = candidate
    path = bundle / "upstream.txt"
    if damage == "missing":
        path.unlink()
    elif damage == "non_utf8":
        path.write_bytes(b"\xff")
    elif damage == "hash":
        manifest["artifacts"][0]["canonical_sha256"] = "0" * 64
    elif damage == "canonicalization":
        manifest["artifacts"][0]["canonicalization"] = "NFKC"
    elif damage == "empty":
        path.write_bytes(b" ")
    save_manifest(bundle, manifest)
    assert check_candidate_bundle(bundle)["structural_valid"] is False


@pytest.mark.parametrize("field,value", [
    ("source_start", -1), ("source_start", True), ("source_end", 10000),
    ("source_end", 0), ("source_end", "10"), ("text_sha256", "0" * 64),
    ("source_file", "rights.txt"), ("file", "missing.txt"),
])
def test_excerpt_offset_and_mapping_failures(candidate, field, value):
    bundle, manifest = candidate
    manifest["excerpts"][0][field] = value
    save_manifest(bundle, manifest)
    assert check_candidate_bundle(bundle)["structural_valid"] is False


def test_equivalent_visual_unicode_does_not_replace_exact_text(candidate):
    bundle, manifest = candidate
    replacement = "甲😀乙．\n"  # Fullwidth stop is not the original ideographic stop.
    (bundle / "excerpt.txt").write_text(replacement, encoding="utf-8")
    manifest["artifacts"][1]["canonical_sha256"] = text_sha256(replacement)
    manifest["excerpts"][0]["text_sha256"] = text_sha256(replacement)
    save_manifest(bundle, manifest)
    assert any("differs from source slice" in e for e in check_candidate_bundle(bundle)["errors"])


@pytest.mark.parametrize("damage", ["rights", "excerpts", "duplicate", "unmapped"])
def test_material_coverage(candidate, damage):
    bundle, manifest = candidate
    if damage == "rights":
        manifest["artifacts"].pop()
    elif damage == "excerpts":
        manifest["excerpts"] = []
    elif damage == "duplicate":
        manifest["artifacts"].append(manifest["artifacts"][0])
    elif damage == "unmapped":
        extra = dict(manifest["artifacts"][1], file="extra.txt")
        (bundle / "extra.txt").write_bytes((bundle / "excerpt.txt").read_bytes())
        manifest["artifacts"].append(extra)
    save_manifest(bundle, manifest)
    assert check_candidate_bundle(bundle)["structural_valid"] is False


@pytest.mark.parametrize("raw", [b"{", b"[]", b"\xff", b'{"schema":1,"schema":2}'])
def test_malformed_manifest_is_readable_json_error(tmp_path, raw):
    (tmp_path / "manifest.json").write_bytes(raw)
    report = check_candidate_bundle(tmp_path)
    assert report["structural_valid"] is False
    assert report["errors"][0].startswith("manifest:")
    json.dumps(report)


def test_missing_manifest_and_missing_bundle_are_reported(tmp_path):
    for bundle in (tmp_path, tmp_path / "absent"):
        assert check_candidate_bundle(bundle)["errors"][0].startswith("manifest:")


def test_crlf_is_the_only_normalization():
    assert canonical_text("Ａ\r\nB\rC\ufeff".encode()) == "Ａ\nB\rC\ufeff"


@pytest.mark.parametrize("valid,expected_exit", [(True, 0), (False, 1)])
def test_script_json_and_exit_status(candidate, monkeypatch, capsys, valid, expected_exit):
    bundle, _ = candidate
    if not valid:
        (bundle / "manifest.json").unlink()
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_c02_candidate.py"
    monkeypatch.setattr(sys, "argv", [str(script), str(bundle)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert exc.value.code == expected_exit
    report = json.loads(capsys.readouterr().out)
    assert report["structural_valid"] is valid
    assert report["acceptance_ready"] is False
