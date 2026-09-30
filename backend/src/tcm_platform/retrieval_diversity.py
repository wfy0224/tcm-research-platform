"""Deterministic, soft diversity over already authorized exact proof identities."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from uuid import UUID

DIVERSITY_POLICY = "source-context/v1"


def diversify(
    ordered: Sequence[UUID], *, scores: Mapping[UUID, float],
    provenance: Mapping[UUID, dict], limit: int,
) -> tuple[list[UUID], dict[UUID, dict]]:
    """Discount repeated sources and overlapping quotes without merging evidence.

    Context overlap is shared exact segment references within one SourceRevision,
    divided by the smaller quote's segment count. No textual similarity or
    cross-edition equivalence is inferred. Penalties are soft: a single source
    and distinct proofs of the same passage can still fill the requested limit.
    Scores must be positive relevance credits (RRF or reciprocal rerank rank),
    never arbitrary provider scores whose scales/signs differ between models.
    """
    remaining = list(dict.fromkeys(ordered))
    base_rank = {item: rank for rank, item in enumerate(remaining, 1)}
    segments = {item: set(provenance[item]["segment_revision_ids"]) for item in remaining}
    source_counts: dict[str, int] = defaultdict(int)
    overlaps: dict[UUID, float] = defaultdict(float)
    selected, explanations = [], {}
    while remaining and len(selected) < limit:
        def credit(item: UUID) -> float:
            return scores[item] / (
                (1 + source_counts[provenance[item]["source_id"]]) * (1 + overlaps[item])
            )

        best = min(remaining, key=lambda item: (-credit(item), base_rank[item]))
        proof = provenance[best]
        explanations[best] = {
            "policy": DIVERSITY_POLICY, "relevance_rank": base_rank[best],
            "source_occurrence": source_counts[proof["source_id"]] + 1,
            "context_overlap": overlaps[best], "selection_score": credit(best),
        }
        remaining.remove(best)
        selected.append(best)
        source_counts[proof["source_id"]] += 1
        for item in remaining:
            if provenance[item]["source_revision_id"] != proof["source_revision_id"]:
                continue
            shared = len(segments[item] & segments[best])
            if shared:
                overlaps[item] += shared / min(len(segments[item]), len(segments[best]))
    return selected, explanations
