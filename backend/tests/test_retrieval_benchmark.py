from uuid import uuid4

import pytest

from tcm_platform.retrieval_benchmark import score_ranked


def test_golden_metrics_credit_counter_evidence_and_penalize_hard_negative():
    gold, counter, optional, negative = (uuid4() for _ in range(4))
    labels = {
        gold: "GOLD", counter: "COUNTER", optional: "OPTIONAL",
        negative: "HARD_NEGATIVE",
    }
    metrics = score_ranked(
        [negative, counter, gold], labels, k=3, resolved_ids={counter, gold},
    )
    assert metrics["precision_at_k"] == pytest.approx(2 / 3)
    assert metrics["recall_at_k"] == 1
    assert metrics["mrr"] == 0.5
    assert 0 < metrics["ndcg_at_k"] < 1
    assert metrics["counter_evidence_recall_at_k"] == 1
    assert metrics["evidence_resolution_rate"] == pytest.approx(2 / 3)


def test_empty_results_have_zero_metrics():
    gold = uuid4()
    assert all(value == 0 for value in score_ranked([], {gold: "GOLD"}, k=10).values())
