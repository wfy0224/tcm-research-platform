"""Stopping must distinguish a response from an independent follow-up review."""

from tcm_platform.stop_service import WorkflowConfig, evaluate_snapshot


def snapshot(**overrides):
    return {"workflow_config": WorkflowConfig().model_dump(), "round_no": 2,
            "first_round_claim_count": 9, "current_critique_count": 5,
            "new_claim_count": 0, "supported_claim_count": 9,
            "open_dispute_ids": [], "open_gap_ids": [],
            "resolved_review_reasons": [], **overrides}


def test_reply_requires_another_independent_critic_pass_even_without_new_claims():
    assert evaluate_snapshot(snapshot()) == ("CONTINUE", "FOLLOWUP_REVIEW")
    assert evaluate_snapshot(snapshot(round_no=3, open_gap_ids=["gap"])) == (
        "CONTINUE", "FOLLOWUP_REVIEW")


def test_followup_can_finish_without_inventing_more_critiques_or_hiding_gaps():
    value = snapshot(round_no=3, current_critique_count=0, open_gap_ids=["gap"])
    assert evaluate_snapshot(value) == ("STOP", "NO_CRITIQUES")
    assert value["open_gap_ids"] == ["gap"]


def test_round_budget_preserves_unresolved_gaps_and_bounds_model_calls():
    assert evaluate_snapshot(snapshot(round_no=4, open_gap_ids=["gap"])) == (
        "STOP", "ROUND_LIMIT")


def test_legacy_frozen_policy_replays_its_original_decision():
    config = WorkflowConfig().model_dump(exclude={"review_replies"})
    config["max_debate_rounds"] = 1
    assert evaluate_snapshot(snapshot(workflow_config=config, open_gap_ids=["gap"])) == (
        "STOP", "ROUND_LIMIT")
    config["max_debate_rounds"] = 3
    assert evaluate_snapshot(snapshot(workflow_config=config)) == ("STOP", "STABLE_EVIDENCE")
    assert evaluate_snapshot(snapshot(workflow_config={}, open_gap_ids=["gap"])) == (
        "STOP", "ROUND_LIMIT")
