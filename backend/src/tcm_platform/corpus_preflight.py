"""Read-only integrity checks for a proposed C02 source bundle.

This verifies local materials, not their historical authenticity, legal sufficiency,
expert acceptance, or authorization to publish/import them.
"""

import hashlib
import json
from pathlib import Path, PureWindowsPath
from urllib.parse import parse_qs, unquote, urlsplit

SCHEMA = "c02-candidate/v1"
CANONICALIZATION = "CRLF_TO_LF_UTF8"
BLOCKERS = [
    "OWNER_SELECTION_PENDING",
    "EXPERT_REVIEW_PENDING",
    "PHYSICAL_EDITION_UNVERIFIED",
]
ROLES = {"UPSTREAM_TEXT", "EXCERPT", "RIGHTS_NOTICE"}


def canonical_text(raw: bytes) -> str:
    """Decode strict UTF-8 and normalize CRLF only; preserve all other characters."""
    return raw.decode("utf-8").replace("\r\n", "\n")


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _bundle_file(root: Path, name: object) -> Path:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("file must be a nonempty relative path")
    windows_path = PureWindowsPath(name)
    if Path(name).is_absolute() or windows_path.drive or windows_path.root:
        raise ValueError("absolute file paths are forbidden")
    if ".." in windows_path.parts or ".." in Path(name).parts:
        raise ValueError("parent traversal is forbidden")
    target = (root / name).resolve(strict=True)
    if not target.is_relative_to(root):
        raise ValueError("file escapes bundle (including symlinks)")
    if not target.is_file():
        raise ValueError("file is not a regular file")
    return target


def _https_url(value: object) -> bool:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username


def _revision_errors(manifest: dict) -> list[str]:
    """Check the MediaWiki permanent-revision locator without using the network."""
    errors = []
    for field in ("source_url", "revision_url", "license_notice_url"):
        if not _https_url(manifest.get(field)):
            errors.append(f"{field}: a valid HTTPS URL is required")
    revision_id = manifest.get("upstream_revision_id")
    if type(revision_id) is not int or revision_id <= 0:
        errors.append("upstream_revision_id: a positive integer is required")
    if errors:
        return errors
    source = urlsplit(manifest["source_url"])
    revision = urlsplit(manifest["revision_url"])
    source_query = parse_qs(source.query, keep_blank_values=True)
    revision_query = parse_qs(revision.query, keep_blank_values=True)
    if revision_query.get("oldid") != [str(revision_id)]:
        errors.append("revision_url: oldid must equal upstream_revision_id exactly")
    if source.netloc.lower() != revision.netloc.lower():
        errors.append("revision_url: host must match source_url")
    source_title = source_query.get("title", [unquote(source.path.removeprefix("/wiki/"))])
    revision_title = revision_query.get(
        "title", [unquote(revision.path.removeprefix("/wiki/"))]
    )
    if source_title != revision_title:
        errors.append("revision_url: page title must match source_url")
    if "oldid" in source_query and source_query["oldid"] != [str(revision_id)]:
        errors.append("source_url: oldid conflicts with upstream_revision_id")
    return errors


def check_candidate_bundle(bundle: str | Path) -> dict:
    """Return a JSON-serializable report; no database, network, or writes are used."""
    report = {
        "schema_version": "c02-preflight-report/v1",
        "structural_valid": False,
        "acceptance_ready": False,
        "verification_scope": "LOCAL_MATERIAL_INTEGRITY_ONLY",
        "blockers": list(BLOCKERS),
        "errors": [],
    }
    errors = report["errors"]
    try:
        root = Path(bundle).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("bundle is not a directory")
        manifest_path = _bundle_file(root, "manifest.json")
        manifest = json.loads(
            canonical_text(manifest_path.read_bytes()), object_pairs_hook=_unique_object
        )
        if not isinstance(manifest, dict):
            raise TypeError("manifest root must be an object")
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        errors.append(f"manifest: {exc}")
        return report

    expected = {
        "schema_version": SCHEMA,
        "selection_status": "PROPOSED",
        "data_owner_role": "测试人员",
        "expert_review_status": "PENDING",
        "outbound_authorized": False,
        "physical_page_mapping": None,
    }
    for field, value in expected.items():
        if (
            field not in manifest
            or type(manifest[field]) is not type(value)
            or manifest[field] != value
        ):
            errors.append(f"{field}: expected {value!r}")
    for field in ("section", "rights_basis"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            errors.append(f"{field}: nonempty text is required")
    errors.extend(_revision_errors(manifest))

    artifacts = manifest.get("artifacts")
    texts, roles, resolved_paths = {}, {}, set()
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts: a nonempty array is required")
        artifacts = []
    for index, artifact in enumerate(artifacts):
        prefix = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        name, role = artifact.get("file"), artifact.get("role")
        try:
            path = _bundle_file(root, name)
            if path in resolved_paths or name in texts or path == manifest_path:
                raise ValueError("duplicate artifact or manifest used as artifact")
            resolved_paths.add(path)
            text = canonical_text(path.read_bytes())
            if not text.strip():
                raise ValueError("artifact is empty")
            texts[name] = text
            if role not in ROLES:
                raise ValueError("unknown artifact role")
            roles[name] = role
            if artifact.get("canonicalization") != CANONICALIZATION:
                raise ValueError("unsupported canonicalization")
            if artifact.get("canonical_sha256") != text_sha256(text):
                raise ValueError("canonical_sha256 mismatch")
        except (OSError, ValueError, UnicodeError, TypeError) as exc:
            errors.append(f"{prefix}: {exc}")
    for role in ROLES:
        if role not in roles.values():
            errors.append(f"artifacts: missing {role} material")

    excerpts = manifest.get("excerpts")
    if not isinstance(excerpts, list) or not excerpts:
        errors.append("excerpts: a nonempty array is required")
        excerpts = []
    referenced_excerpts = set()
    for index, excerpt in enumerate(excerpts):
        prefix = f"excerpts[{index}]"
        if not isinstance(excerpt, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        try:
            name, source = excerpt.get("file"), excerpt.get("source_file")
            if roles.get(name) != "EXCERPT" or roles.get(source) != "UPSTREAM_TEXT":
                raise ValueError("file/source_file must reference EXCERPT/UPSTREAM_TEXT artifacts")
            if name in referenced_excerpts:
                raise ValueError("duplicate excerpt mapping")
            referenced_excerpts.add(name)
            start, end = excerpt.get("source_start"), excerpt.get("source_end")
            if (
                type(start) is not int
                or type(end) is not int
                or not 0 <= start < end <= len(texts[source])
            ):
                raise ValueError("invalid Unicode character offsets")
            if texts[source][start:end] != texts[name]:
                raise ValueError("excerpt differs from source slice")
            if excerpt.get("text_sha256") != text_sha256(texts[name]):
                raise ValueError("text_sha256 mismatch")
        except (ValueError, TypeError) as exc:
            errors.append(f"{prefix}: {exc}")
    if referenced_excerpts != {name for name, role in roles.items() if role == "EXCERPT"}:
        errors.append("excerpts: every EXCERPT artifact must have one mapping")
    report["structural_valid"] = not errors
    report["artifact_count"] = len(artifacts)
    report["excerpt_count"] = len(excerpts)
    report["candidate"] = {field: manifest.get(field) for field in expected}
    return report
