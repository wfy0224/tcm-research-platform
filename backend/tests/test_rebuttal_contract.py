"""Regression checks for the model input that caused server Rebuttal rejection."""

from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock, patch
from uuid import uuid4

from tcm_platform import debate_service
from tcm_platform.research_service import CLAIM_TYPES


class RebuttalContractTests(TestCase):
    def test_legacy_frozen_targets_receive_role_specific_types_without_mutation(self):
        for role, allowed in CLAIM_TYPES.items():
            with self.subTest(role=role):
                snapshot = {
                    "critiques": [{"critique_id": str(uuid4()), "agent_role": role,
                                   "claim_type": min(allowed)}],
                    "run_fingerprint": "legacy-frozen",
                    "prompt_version": "rebuttal-v1",
                }
                before = deepcopy(snapshot)
                run = SimpleNamespace(role="Rebuttal", round_no=2,
                                      input_snapshot=snapshot, visible_evidence_ids=[])
                session = MagicMock()
                session.__enter__.return_value = session
                session.get.return_value = run
                with patch.object(debate_service, "SessionLocal", return_value=session):
                    payload = debate_service.rebuttal_visible_context(uuid4())
                self.assertEqual(payload["critiques"][0]["allowed_claim_types"],
                                 sorted(allowed))
                self.assertEqual(snapshot, before)
                payload["critiques"][0]["allowed_claim_types"].append("INVALID")
                self.assertEqual(snapshot, before)

    def test_prompt_requires_target_role_types_instead_of_fixed_direct_text(self):
        self.assertIn("allowed_claim_types", debate_service.REBUTTAL_PROMPT)
        self.assertNotIn('"claim_type":"DIRECT_TEXT"', debate_service.REBUTTAL_PROMPT)


if __name__ == "__main__":
    main()
