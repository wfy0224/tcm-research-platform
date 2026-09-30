from uuid import uuid4

from tcm_platform.retrieval_diversity import diversify


def test_overlapping_ranges_are_discounted_without_losing_distinct_proofs():
    a, b, c = (uuid4() for _ in range(3))
    provenance = {
        a: {"source_id": "same", "source_revision_id": "old", "segment_revision_ids": ["1", "2"]},
        b: {"source_id": "same", "source_revision_id": "old", "segment_revision_ids": ["2", "3"]},
        c: {"source_id": "same", "source_revision_id": "old", "segment_revision_ids": ["4"]},
    }
    ranked, reasons = diversify([a, b, c], scores={a: 1.0, b: 0.9, c: 0.85},
                                provenance=provenance, limit=3)
    assert ranked == [a, c, b]
    assert reasons[b]["context_overlap"] == 0.5
    assert reasons[b]["relevance_rank"] == 2


def test_identical_text_in_different_revisions_is_not_context_overlap():
    a, b = uuid4(), uuid4()
    provenance = {
        a: {"source_id": "same", "source_revision_id": "old", "segment_revision_ids": ["1"]},
        b: {"source_id": "same", "source_revision_id": "new", "segment_revision_ids": ["1"]},
    }
    ranked, reasons = diversify([a, a, b], scores={a: 1.0, b: 0.9},
                                provenance=provenance, limit=10)
    assert ranked == [a, b]
    assert reasons[b]["context_overlap"] == 0


def test_weak_other_source_does_not_override_strong_relevance():
    a, b, weak = (uuid4() for _ in range(3))
    provenance = {
        a: {"source_id": "strong", "source_revision_id": "s", "segment_revision_ids": ["1"]},
        b: {"source_id": "strong", "source_revision_id": "s", "segment_revision_ids": ["2"]},
        weak: {"source_id": "weak", "source_revision_id": "w", "segment_revision_ids": ["3"]},
    }
    ranked, _ = diversify([a, b, weak], scores={a: 1.0, b: 0.9, weak: 0.1},
                          provenance=provenance, limit=2)
    assert ranked == [a, b]
