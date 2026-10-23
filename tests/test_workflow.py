import copy
from pathlib import Path
import unittest

from axiom_forge.workflow import canonical, decode, evaluate, fingerprint

FIXTURES = Path(__file__).parent / "fixtures"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.case = decode((FIXTURES / "baseline.json").read_bytes())

    def test_baseline_outcomes_match_curated_oracle(self):
        expected = decode((FIXTURES / "expected.json").read_bytes())
        report = evaluate(self.case)
        actual = {c["id"]: [c["status"], c["reason"], c["plain_baseline"]]
                  for c in report["candidates"]}
        self.assertEqual(actual, expected)
        self.assertEqual(report["totals"], {"accepted": 1, "refused": 1, "unknown": 3})
        self.assertEqual(report["plain_baseline_totals"],
                         {"accepted": 3, "refused": 2, "unknown": 0})
        self.assertEqual(sum(report["totals"].values()), len(self.case["candidates"]))
        self.assertEqual(report["human_approval"], "pending")
        self.assertTrue(report["unknowns"])
        prior = (FIXTURES / "prior-contract.json").read_bytes()
        self.assertEqual(self.case["candidates"][3]["context"]["contract"], fingerprint(prior))

    def test_evaluation_is_deterministic_and_does_not_mutate_inputs(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(canonical(evaluate(self.case)), canonical(evaluate(self.case)))
        self.assertEqual(self.case, original)

    def test_acceptance_requires_separate_review(self):
        for update in ({"checks_reviewed": False}, {"reviewer": "fixture-generator"}):
            with self.subTest(update=update):
                case = copy.deepcopy(self.case)
                case["acceptance"].update(update)
                result = evaluate(case)["candidates"][0]
                self.assertEqual((result["status"], result["reason"]),
                                 ("unknown", "unreviewed_acceptance"))

    def test_each_context_change_invalidates_acceptance(self):
        for name in ("baseline", "contract", "policy"):
            with self.subTest(name=name):
                case = copy.deepcopy(self.case)
                case[name]["version"] += "-changed"
                result = evaluate(case)["candidates"][0]
                self.assertEqual((result["status"], result["reason"]),
                                 ("unknown", f"changed_{name}"))

    def test_verifier_false_acceptance_stays_unknown(self):
        candidate = self.case["candidates"][0]
        for item in candidate["observations"].values():
            item["independent"] = False
        result = evaluate(self.case)["candidates"][0]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "faulty_verifier")
        self.assertEqual(result["plain_baseline"], "accepted")

    def test_missing_observation_is_unknown(self):
        self.case["candidates"][0]["observations"]["add(2, 3) == 5"]["verifier"] = None
        result = evaluate(self.case)["candidates"][0]
        self.assertEqual(result["status"], "unknown")

    def test_invalid_contracts_and_evidence_are_rejected(self):
        mutations = [
            lambda c: c.update(version=True),
            lambda c: c.update(goal=""),
            lambda c: c["contract"].update(checks=[]),
            lambda c: c["policy"].update(human_approval_required=False),
            lambda c: c["candidates"].append(copy.deepcopy(c["candidates"][0])),
            lambda c: c["candidates"][0]["observations"].clear(),
            lambda c: c["candidates"][0]["observations"]["add(2, 3) == 5"].update(verifier=1),
            lambda c: c["candidates"][0]["context"].update(contract="../../etc/passwd"),
            lambda c: c.update(unrecognized=True),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                case = copy.deepcopy(self.case)
                mutate(case)
                with self.assertRaises(ValueError):
                    evaluate(case)

    def test_ambiguous_json_is_rejected(self):
        for raw in (b'{"version": 1, "version": 2}', b'{"x": NaN}', b'[]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)
