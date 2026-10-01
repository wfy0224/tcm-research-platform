"""Print C02 local bundle integrity as JSON; pending approvals are not an error exit."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tcm_platform.corpus_preflight import check_candidate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Directory containing manifest.json")
    args = parser.parse_args()
    report = check_candidate_bundle(args.bundle)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["structural_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
