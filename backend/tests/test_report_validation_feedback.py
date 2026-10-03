"""Exercise actual drafting loop: invalid content must reach the next writer."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock, patch
from uuid import uuid4

from tcm_platform import report_narrative as report


class ReportValidationFeedbackTests(TestCase):
    def run_loop(self, drafts, accept=True, fail_transport=False, snapshot=None,
                 old_writers=(), reviews=(), revision=None, decisions=None):
        snapshot = snapshot or {"question": "比较方剂", "claims": [{
            "claim_id": "c1", "allowed_category": "CONDITIONAL", "evidence": []}],
            "gaps": [], "disputes": []}
        task = SimpleNamespace(execution_context={
            "generation_model": "test/model", "frozen_prompts": {"ReportWriter": "frozen"}})
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.return_value = task
        session.scalar.side_effect = [SimpleNamespace(input_snapshot=snapshot), revision]
        session.scalars.side_effect = [list(old_writers), list(reviews)]
        self.calls, self.saved, self.prepared = [], {}, {}

        def prepare(task_id, role, attempt, payload, guard):
            key = (role, attempt)
            self.prepared[key] = deepcopy(payload)
            return key, None

        def complete(task_id, run_id, role, model, prompt, payload):
            self.calls.append((role, deepcopy(payload)))
            if fail_transport:
                raise TimeoutError("real transport failure")
            if role == "ReportWriter":
                return deepcopy(drafts.pop(0))
            accepted = decisions.pop(0) if decisions is not None else accept
            return {"accepted": accepted, "issues": [] if accepted else ["保留条件限定"],
                    "review_summary": "实际测试的复核结果"}

        with patch.object(report, "SessionLocal", return_value=session), \
                patch.object(report, "_prepare", side_effect=prepare), \
                patch.object(report, "_save",
                             side_effect=lambda key, value, guard: self.saved.update(
                                 {key: deepcopy(value)})), \
                patch.object(report, "recorded_complete", side_effect=complete):
            report.execute_report_narrative(uuid4(), model=SimpleNamespace(
                model_version="test/model"))

    def draft(self, kind):
        return {"paragraphs": [{"text": "教材提出的解释尚有条件限制。", "kind": kind,
                                "claim_ids": ["c1"]}]}

    def test_conditional_finding_is_revised_without_worker_failure(self):
        self.run_loop([self.draft("finding"), self.draft("explanation")])
        writers = [payload for role, payload in self.calls if role == "ReportWriter"]
        self.assertEqual(len(writers), 2)
        self.assertIn("CONDITIONAL", writers[1]["feedback"][0])
        self.assertIn("explanation", writers[1]["feedback"][0])
        self.assertIn("paragraph_contract", writers[0])
        self.assertNotIn("paragraph_contract", self.prepared[("ReportWriter", 0)])
        self.assertFalse(self.saved[("ReportValidator", 0)]["accepted"])
        self.assertEqual([role for role, _ in self.calls],
                         ["ReportWriter", "ReportWriter", "ReportReviewer"])

    def test_schema_failure_also_reaches_next_writer(self):
        self.run_loop([{"paragraphs": []}, self.draft("explanation")])
        writers = [payload for role, payload in self.calls if role == "ReportWriter"]
        self.assertIn("JSON段落结构", writers[1]["feedback"][0])

    def test_exhaustion_is_review_required_not_unhandled_value_error(self):
        drafts = [self.draft("finding") for _ in range(3)]
        for index, draft in enumerate(drafts):
            draft["paragraphs"][0]["text"] += f"第{index + 1}稿。"
        with self.assertRaises(report.ReportReviewExhausted):
            self.run_loop(drafts)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len([key for key in self.saved if key[0] == "ReportValidator"]), 3)

    def test_transport_error_still_propagates_for_worker_retry(self):
        with self.assertRaises(TimeoutError):
            self.run_loop([], fail_transport=True)
        self.assertFalse(self.saved)

    def test_validation_keeps_unresolved_feedback_across_drafts(self):
        self.run_loop([self.draft("finding"), {"paragraphs": []}, self.draft("explanation")])
        writers = [payload for role, payload in self.calls if role == "ReportWriter"]
        self.assertEqual(len(writers[2]["feedback"]), 2)
        self.assertIn("CONDITIONAL", writers[2]["feedback"][0])
        self.assertIn("JSON段落结构", writers[2]["feedback"][1])

    def test_validation_feedback_survives_a_new_revision_cycle(self):
        run = SimpleNamespace(role="ReportValidator", input_snapshot={"feedback": ["补回局部比较"]},
                              output={"issues": ["修正段落类型"], "review_summary": "未通过"})
        self.assertEqual(report.review_feedback(run), ["补回局部比较", "修正段落类型"])
        run.role = "ReportReviewer"
        self.assertEqual(report.review_feedback(run), ["修正段落类型"])

    def test_completion_restores_frozen_context_without_rewriting_checkpoint(self):
        snapshot = {"question": "比较方剂", "claims": [{
            "claim_id": "c1", "allowed_category": "CONDITIONAL", "evidence": [{
                "evidence_revision_id": "e1", "quote_text": "直接引文",
                "context_before": "原文前文", "context_after": "原文后文",
                "evidence_strength": "TEXTUAL"}]}], "gaps": [], "disputes": []}
        checkpoint = report.writer_input(snapshot, ["上一稿意见"])
        before = deepcopy(checkpoint)
        payload = report.writer_completion_input(checkpoint, snapshot)
        evidence = payload["claims"][0]["evidence"][0]
        self.assertEqual(evidence["context_before"], "原文前文")
        self.assertEqual(evidence["context_after"], "原文后文")
        self.assertEqual(evidence["quote_text"], "直接引文")
        payload["claims"][0]["evidence"][0]["context_after"] = "不能回写"
        self.assertEqual(checkpoint, before)
        self.assertEqual(snapshot["claims"][0]["evidence"][0]["context_after"], "原文后文")

    def test_writer_and_reviewer_share_scope_but_review_remains_independent(self):
        snapshot = {"question": "比较方剂", "claims": [{
            "claim_id": "c1", "allowed_category": "CONDITIONAL", "evidence": []}],
            "gaps": [], "disputes": []}
        payload = report.writer_input(snapshot, ["上轮修改意见"])
        candidate = self.draft("explanation")
        writer = report.writer_completion_input(payload, snapshot)
        reviewer = report.reviewer_completion_input(
            report.reviewer_input(payload, candidate), snapshot)
        self.assertEqual(writer["answer_contract"], reviewer["answer_contract"])
        self.assertNotIn("feedback", reviewer)
        self.assertIn("证据", reviewer["answer_contract"]["coverage"])

    def test_writer_receives_previous_draft_for_targeted_revision(self):
        rejected = self.draft("explanation")
        revised = {"paragraphs": [{"text": "按意见保留条件的修订。", "kind": "explanation",
                                   "claim_ids": ["c1"]}]}
        self.run_loop([rejected, revised], decisions=[False, True])
        writers = [payload for role, payload in self.calls if role == "ReportWriter"]
        self.assertEqual(writers[1]["previous_candidate"], rejected)
        self.assertEqual(writers[1]["feedback"], ["保留条件限定"])
        reviewer = [payload for role, payload in self.calls if role == "ReportReviewer"][-1]
        self.assertNotIn("previous_candidate", reviewer)
        self.assertNotIn("feedback", reviewer)

    def test_new_cycle_recovers_draft_referenced_by_the_last_review(self):
        rejected = self.draft("finding")
        old = SimpleNamespace(role="ReportWriter", round_no=8, status="COMPLETED",
                              input_snapshot={"input_schema": report.INPUT_SCHEMA}, output=rejected)
        review = SimpleNamespace(role="ReportValidator", round_no=8, status="COMPLETED",
                                 input_snapshot={"candidate": rejected, "feedback": ["内容意见"]},
                                 output={"accepted": False, "issues": ["修正类型"],
                                         "review_summary": "未通过"})
        self.run_loop([self.draft("explanation")], old_writers=[old], reviews=[review],
                      revision=SimpleNamespace(payload={"start_attempt": 9}))
        payload = self.calls[0][1]
        self.assertEqual(payload["previous_candidate"], rejected)
        self.assertEqual(payload["feedback"], ["内容意见", "修正类型"])

    def test_validator_reports_every_bad_paragraph_and_citation_in_one_pass(self):
        snapshot = {"claims": [{"claim_id": "c1", "allowed_category": "CONDITIONAL"}]}
        bad = {"paragraphs": [self.draft("finding")["paragraphs"][0],
                              {"text": "误引", "kind": "explanation", "claim_ids": ["unknown"]}]}
        with self.assertRaises(ValueError) as caught:
            report.validate_narrative(bad, snapshot)
        feedback = report.validation_feedback(caught.exception)
        self.assertIn("第1段", feedback)
        self.assertIn("c1", feedback)
        self.assertIn("第2段", feedback)
        self.assertIn("unknown", feedback)

    def captured_trace(self):
        if "CAPTURED_TRACE" in globals():
            return globals()["CAPTURED_TRACE"]
        path = Path(__file__).resolve().parents[2] / (
            "docs/acceptance-artifacts/server-rebuttal-contract/OFFLINE_REPLAY.json")
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def test_real_final_draft_identifies_every_conditional_finding(self):
        trace = self.captured_trace()
        draft = next(row["output"] for row in trace["drafts"] if row["round"] == 20)
        categories = {c["claim_id"]: c["allowed_category"] for c in trace["snapshot"]["claims"]}
        with self.assertRaises(ValueError) as caught:
            report.validate_narrative(draft, trace["snapshot"])
        feedback = report.validation_feedback(caught.exception)
        for index, paragraph in enumerate(draft["paragraphs"], 1):
            conditional = [key for key in paragraph["claim_ids"]
                           if categories[key] == "CONDITIONAL"]
            if paragraph["kind"] == "finding" and conditional:
                self.assertIn(f"第{index}段", feedback)
                for key in conditional:
                    self.assertIn(key, feedback)

    def test_real_missing_kind_draft_reports_all_five_locations_without_raw_dump(self):
        trace = self.captured_trace()
        draft = next(row["output"] for row in trace["drafts"] if row["round"] == 16)
        with self.assertRaises(ValueError) as caught:
            report.validate_narrative(draft, trace["snapshot"])
        feedback = report.validation_feedback(caught.exception)
        for index in range(1, 6):
            self.assertIn(f"第{index}段字段kind", feedback)
        self.assertNotIn("input_value=", feedback)

    def test_real_failed_drafts_replay_without_cloud_calls_or_false_acceptance(self):
        trace = self.captured_trace()
        draft = next(row["output"] for row in trace["drafts"] if row["round"] == 20)
        original = deepcopy(draft)
        with self.assertRaises(report.ReportReviewExhausted):
            self.run_loop([deepcopy(draft) for _ in range(3)], snapshot=trace["snapshot"])
        self.assertEqual([role for role, _ in self.calls], ["ReportWriter"] * 2)
        self.assertEqual(self.calls[1][1]["previous_candidate"], original)
        self.assertTrue(all(not value["accepted"] for key, value in self.saved.items()
                            if key[0] == "ReportValidator"))
        self.assertEqual(draft, original)

    def test_identical_rejected_draft_stops_before_another_paid_review(self):
        draft = self.draft("explanation")
        with self.assertRaises(report.ReportReviewExhausted):
            self.run_loop([deepcopy(draft), deepcopy(draft)], accept=False)
        self.assertEqual([role for role, _ in self.calls],
                         ["ReportWriter", "ReportReviewer", "ReportWriter"])
        self.assertFalse(self.saved[("ReportValidator", 1)]["accepted"])

    def test_review_only_receives_gaps_and_disputes_for_the_cited_claims(self):
        snapshot = {"question": "比较", "claims": [{"claim_id": "c1",
                    "allowed_category": "CONDITIONAL", "evidence": []}],
                    "gaps": [{"claim_id": "c1", "rationale_summary": "应保留的本段限制"},
                             {"claim_id": "old", "rationale_summary": "不属于本稿引用的旧意见"},
                             {"claim_id": None, "rationale_summary": "总体材料缺口"}],
                    "disputes": [{"target_claim_id": "old", "competing_claim_id": "c1"},
                                 {"target_claim_id": "old", "competing_claim_id": "other"}]}
        payload = report.reviewer_input(report.writer_input(snapshot, []), self.draft("explanation"))
        frozen = deepcopy(payload)
        result = report.reviewer_completion_input(payload, snapshot)
        self.assertEqual([row["claim_id"] for row in result["gaps"]], ["c1", None])
        self.assertEqual(len(result["disputes"]), 1)
        self.assertEqual(payload, frozen)
        self.assertEqual(result["citation_checklist"][0]["paragraph_no"], 1)
        self.assertEqual(result["citation_checklist"][0]["claim_ids"], ["c1"])


if __name__ == "__main__":
    main()
