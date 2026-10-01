"""Inspect proposed C02 text with production local rules; never import or approve it."""

import argparse
import json
from dataclasses import asdict
from itertools import groupby
from pathlib import Path

from tcm_platform.corpus_preflight import check_candidate_bundle
from tcm_platform.knowledge_extraction import EXTRACTOR_VERSION
from tcm_platform.knowledge_formula_extraction import scan_formula_candidates
from tcm_platform.knowledge_service import CITABLE_SEGMENT_TYPES
from tcm_platform.parsing import PARSER_VERSION, parse_source_file
from tcm_platform.segmentation import RESOLVER_VERSION, resolve_structure


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    report = check_candidate_bundle(args.bundle)
    if not report["structural_valid"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    bundle = args.bundle.resolve()
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    inspections = []
    for excerpt in manifest["excerpts"]:
        parsed = parse_source_file(bundle / excerpt["file"], "txt")
        segments = resolve_structure(parsed, title=manifest["section"])
        eligible = {index for index, segment in enumerate(segments)
                    if segment.segment_type in CITABLE_SEGMENT_TYPES}
        citable = [segment for index, segment in enumerate(segments)
                   if index in eligible and segment.parent_index not in eligible]
        groups = []
        for _, siblings in groupby(citable, key=lambda s: (s.parent_index, s.segment_type)):
            group = list(siblings)
            candidates = scan_formula_candidates([segment.original_text for segment in group])
            groups.append({
                "segments": [{"sequence_no": segment.sequence_no,
                              "original_text": segment.original_text} for segment in group],
                "candidates": [asdict(candidate) for candidate in candidates],
            })
        count = sum(len(group["candidates"]) for group in groups)
        inspections.append({
            "file": excerpt["file"], "paragraph_count": len(citable),
            "formula_count": count,
            "result": "DRAFT_CANDIDATES_ONLY" if count else "MANUAL_COLLATION_REQUIRED",
            "groups": groups,
        })
    print(json.dumps({
        "purpose": "PROPOSED_CORPUS_RULE_INSPECTION", "acceptance_ready": False,
        "parser_version": PARSER_VERSION, "resolver_version": RESOLVER_VERSION,
        "extractor_version": EXTRACTOR_VERSION, "preflight": report,
        "inspections": inspections, "database_writes": 0, "model_calls": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
