"""Exact, immutable field provenance for formula revisions.

Offsets count Unicode characters in TextSegmentRevision.original_text, with an
inclusive start and exclusive end. Multiple spans may support the same field.
"""

import hashlib
from dataclasses import dataclass
from itertools import pairwise
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from tcm_platform.models import (
    EvidenceRevision,
    EvidenceSegmentRef,
    FormulaEvidence,
    FormulaFieldSource,
    FormulaIngredient,
    FormulaRevision,
    TextSegmentRevision,
)

FORMULA_FIELDS = (
    "original_name", "era", "school", "indications", "effects", "method",
    "dosage_form", "preparation", "cautions",
)
INGREDIENT_FIELDS = (
    "original_name", "herb_id", "amount_original", "amount_normalized", "unit",
    "dose_ratio", "role", "processing",
)
INTERPRETED_FIELDS = frozenset({
    "era", "school", "herb_id", "amount_normalized", "dose_ratio", "role",
})


@dataclass(frozen=True)
class FormulaFieldSourceSpec:
    field_key: str
    evidence_revision_id: UUID
    segment_revision_id: UUID
    start_offset: int
    end_offset: int
    basis: str | None = None


def _field_values(session: Session, revision: FormulaRevision) -> dict[str, str | None]:
    values = {key: getattr(revision, key) for key in FORMULA_FIELDS}
    for ingredient in session.scalars(select(FormulaIngredient).where(
        FormulaIngredient.formula_revision_id == revision.id
    ).order_by(FormulaIngredient.sequence_no)):
        for key in INGREDIENT_FIELDS:
            value = getattr(ingredient, key)
            values[f"ingredients.{ingredient.sequence_no}.{key}"] = (
                str(value) if value is not None else None
            )
    return values


def _span(session: Session, revision_id: UUID, source: FormulaFieldSourceSpec | FormulaFieldSource,
          value: str | None) -> TextSegmentRevision:
    if value is None or not value.strip():
        raise ValueError("formula field source cannot cite an empty field")
    if session.scalar(select(FormulaEvidence.id).where(
        FormulaEvidence.formula_revision_id == revision_id,
        FormulaEvidence.evidence_revision_id == source.evidence_revision_id,
    )) is None:
        raise ValueError("formula field source evidence is not linked to this revision")
    evidence = session.get(EvidenceRevision, source.evidence_revision_id)
    segment = session.get(TextSegmentRevision, source.segment_revision_id)
    ref = session.scalar(select(EvidenceSegmentRef.id).where(
        EvidenceSegmentRef.evidence_revision_id == source.evidence_revision_id,
        EvidenceSegmentRef.segment_revision_id == source.segment_revision_id,
    ))
    if evidence is None or segment is None or ref is None or (
        segment.source_revision_id != evidence.source_revision_id
    ):
        raise ValueError("formula field source segment does not belong to exact evidence revision")
    if hashlib.sha256(segment.original_text.encode("utf-8")).hexdigest() != segment.checksum:
        raise ValueError("formula field source segment checksum is inconsistent")
    if (type(source.start_offset) is not int or type(source.end_offset) is not int
            or not 0 <= source.start_offset < source.end_offset <= len(segment.original_text)):
        raise ValueError("formula field source offsets are invalid")
    if source.basis is not None and (
        not isinstance(source.basis, str) or not source.basis.strip()
    ):
        raise ValueError("formula field source basis must be nonempty when provided")
    if source.field_key.rsplit(".", 1)[-1] in INTERPRETED_FIELDS and (
        source.basis is None or not source.basis.strip()
    ):
        raise ValueError("formula field source basis is required for interpreted or changed values")
    return segment


def _validate_raw_quotes(rows: list[FormulaFieldSource]) -> None:
    """Exact adjacent spans can split a value; transformations need explicit basis."""
    grouped: dict[str, list[FormulaFieldSource]] = {}
    for row in rows:
        grouped.setdefault(row.field_key, []).append(row)
    for sources in grouped.values():
        unexplained = [row for row in sources if not row.basis]
        if not unexplained or all(row.value_snapshot == row.quote_text for row in unexplained):
            continue
        ordered = sorted(unexplained, key=lambda row: row.start_offset)
        same_segment = len({(row.evidence_revision_id, row.segment_revision_id)
                            for row in ordered}) == 1
        adjacent = all(left.end_offset == right.start_offset
                       for left, right in pairwise(ordered))
        if not (same_segment and adjacent and
                "".join(row.quote_text for row in ordered) == ordered[0].value_snapshot):
            raise ValueError("formula field source basis is required for changed values or separated spans")


def add_formula_field_sources(session: Session, revision_id: UUID,
                              sources: tuple[FormulaFieldSourceSpec, ...]) -> None:
    """Validate before inserting; caller owns the encompassing authoring transaction."""
    session.flush()
    revision = session.get(FormulaRevision, revision_id)
    if revision is None or revision.status != "DRAFT" or revision.provenance_version != 1:
        raise ValueError("formula field source requires a new provenance draft")
    values = _field_values(session, revision)
    seen = set()
    rows = []
    for source in sources:
        if source.field_key not in values:
            raise ValueError("formula field source field_key is unknown")
        segment = _span(session, revision_id, source, values[source.field_key])
        identity = (source.field_key, source.evidence_revision_id, source.segment_revision_id,
                    source.start_offset, source.end_offset)
        if identity in seen:
            raise ValueError("formula field source span is duplicated")
        seen.add(identity)
        rows.append(FormulaFieldSource(
            formula_revision_id=revision_id, field_key=source.field_key,
            value_snapshot=values[source.field_key],
            evidence_revision_id=source.evidence_revision_id,
            segment_revision_id=source.segment_revision_id,
            start_offset=source.start_offset, end_offset=source.end_offset,
            quote_text=segment.original_text[source.start_offset:source.end_offset],
            segment_checksum=segment.checksum,
            basis=source.basis.strip() if source.basis is not None else None,
        ))
    _validate_raw_quotes(rows)
    session.add_all(rows)
    session.flush()
    validate_formula_field_sources(session, revision_id)


def validate_formula_field_sources(session: Session, revision_id: UUID,
                                  require_complete: bool = False) -> list[dict]:
    """Reject changed values or broken spans; optionally enforce review completeness."""
    revision = session.get(FormulaRevision, revision_id)
    if revision is None:
        raise ValueError("formula revision does not exist")
    if require_complete and revision.provenance_version != 1:
        raise ValueError("legacy formula requires a new draft with field sources")
    values = _field_values(session, revision)
    if require_complete and any(value is not None and not value.strip() for value in values.values()):
        raise ValueError("formula field sources cannot validate empty fields")
    result = []
    sourced = set()
    rows = list(session.scalars(select(FormulaFieldSource).where(
        FormulaFieldSource.formula_revision_id == revision_id
    ).order_by(FormulaFieldSource.field_key, FormulaFieldSource.start_offset,
               FormulaFieldSource.end_offset, FormulaFieldSource.id)))
    for source in rows:
        if source.field_key not in values:
            raise ValueError("formula field source field_key is unknown")
        value = values[source.field_key]
        if source.value_snapshot != value:
            raise ValueError("formula field source value snapshot is inconsistent")
        segment = _span(session, revision_id, source, value)
        if source.quote_text != segment.original_text[source.start_offset:source.end_offset]:
            raise ValueError("formula field source quote snapshot is inconsistent")
        if source.segment_checksum != segment.checksum:
            raise ValueError("formula field source segment snapshot is inconsistent")
        sourced.add(source.field_key)
        result.append({
            "id": str(source.id), "field_key": source.field_key,
            "value_snapshot": source.value_snapshot,
            "evidence_revision_id": str(source.evidence_revision_id),
            "segment_revision_id": str(source.segment_revision_id),
            "source_revision_id": str(segment.source_revision_id),
            "structural_locator": segment.structural_locator,
            "start_offset": source.start_offset, "end_offset": source.end_offset,
            "quote_text": source.quote_text, "basis": source.basis,
            "segment_checksum": source.segment_checksum,
        })
    _validate_raw_quotes(rows)
    if require_complete:
        missing = sorted(key for key, value in values.items()
                         if value is not None and key not in sourced)
        if missing:
            raise ValueError("formula field sources missing: " + ", ".join(missing))
    return result
