from copy import deepcopy
from decimal import localcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from axiom_forge import cost
from axiom_forge.store import EvidenceStore
from axiom_forge.workflow import canonical, decode, fingerprint

FIXTURES = Path(__file__).parent / "fixtures"
RAW = (FIXTURES / "cost" / "matched.json").read_bytes()


class CostTests(unittest.TestCase):
    def setUp(self):
        self.case = decode(RAW)

    def report(self):
        return cost.analyze(canonical(self.case))

    def first(self):
        return self.report()["strategies"][0]

    def attempt(self):
        return self.case["strategies"][0]["runs"][0]["attempts"][0]

    def test_curated_arithmetic_includes_failed_attempts_and_retries(self):
        expected = decode((FIXTURES / "cost" / "expected.json").read_bytes())
        report = self.report()
        self.assertIn("SIMULATED", report["notice"])
        self.assertTrue(report["comparable"])
        for strategy in report["strategies"]:
            want = expected[strategy["id"]]
            self.assertEqual(strategy["cost"]["total"], want["total"])
            self.assertEqual(strategy["totals"], {s: want[s] for s in cost.STATUSES})
            for field in ("attempts", "retries", "failures", "false_acceptances"):
                self.assertEqual(strategy[field], want[field])
            self.assertEqual(strategy["latency"]["total"], want["latency"])
            self.assertEqual(strategy["cost_per_independently_accepted_result"]["amount"], want["cost_per_accepted"])
            self.assertEqual(sum(strategy["totals"].values()), 2)
        self.assertEqual(report["strategies"][0]["false_acceptance_rate"], {"numerator": 1, "denominator": 2})
        self.assertEqual(report["strategies"][1]["acceptance_rate"], {"numerator": 2, "denominator": 2})
        self.assertEqual(report["strategies"][0]["cost"]["by_component"]["review"], {"USD": "4"})

    def test_zero_acceptance_is_not_zero_cost_or_infinity(self):
        self.case["strategies"][0]["runs"][0]["final_attempt"] = "a1"
        report = self.first()
        self.assertTrue(report["acceptance_complete"])
        self.assertEqual(report["totals"], {"accepted": 0, "refused": 2, "unknown": 0})
        self.assertEqual(report["cost"]["total"], "14")
        self.assertIsNone(report["cost_per_independently_accepted_result"])
        self.assertEqual(report["ratio_unavailable_reasons"], ["zero_independently_accepted_results"])

    def test_multiple_accepted_attempts_count_only_the_selected_task_result(self):
        attempt = self.attempt()
        attempt["execution"] = "succeeded"
        attempt["failure"] = None
        review = self.case["acceptance"][0]
        review["decision"] = "accepted"
        review["checks"] = {c: True for c in review["checks"]}
        report = self.first()
        self.assertEqual(report["attempt_totals"]["accepted"], 2)
        self.assertEqual(report["totals"]["accepted"], 1)
        self.assertEqual(report["false_refusals"], 1)
        self.assertEqual(report["false_refusal_rate"], {"numerator": 1, "denominator": 1})
        self.assertEqual(report["cost_per_independently_accepted_result"]["amount"], "14")

    def test_partial_missing_and_unprovenanced_costs_preserve_subtotals(self):
        original = deepcopy(self.case)
        for field, value, subtotal in (("amount", None, "12"), ("complete", False, "14"),
                                       ("evidence_ref", None, "12")):
            with self.subTest(field=field):
                self.case = deepcopy(original)
                self.attempt()["costs"]["model"][field] = value
                report = self.first()
                self.assertIsNone(report["cost"]["total"])
                self.assertEqual(report["cost"]["known_subtotals"], {"USD": subtotal})
                self.assertEqual(len(report["cost"]["missing_or_partial"]), 1)
                self.assertIsNone(report["cost_per_independently_accepted_result"])
        self.case = deepcopy(original)
        self.attempt()["costs"].pop("storage")
        self.assertIsNone(self.first()["cost"]["total"])
        for strategy in self.case["strategies"]:
            for run in strategy["runs"]:
                for attempt in run["attempts"]:
                    attempt["costs"] = {}
        self.assertEqual(self.first()["cost"]["known_subtotals"], {})

    def test_unknown_acceptance_cannot_make_a_smaller_denominator_look_complete(self):
        self.case["acceptance"].pop(0)  # Even an unselected failed attempt needs review.
        report = self.first()
        self.assertEqual(report["totals"]["accepted"], 1)
        self.assertFalse(report["acceptance_complete"])
        self.assertIsNone(report["cost_per_independently_accepted_result"])
        self.assertIsNone(report["false_refusal_rate"])

    def test_claims_and_self_review_never_grant_independent_acceptance(self):
        original = deepcopy(self.case)
        for field, value in (("reviewer", "synthetic-generator"), ("evidence_ref", None),
                             ("decision", "unknown"), ("candidate_sha256", "0" * 64)):
            with self.subTest(field=field):
                self.case = deepcopy(original)
                self.case["acceptance"][1][field] = value
                report = self.first()
                self.assertEqual(report["totals"]["accepted"], 0)
                self.assertEqual(report["unreviewed_accepted_claims"], 1)
                self.assertIsNone(report["false_acceptance_rate"])
                self.assertIsNone(report["cost_per_independently_accepted_result"])
        self.case = deepcopy(original)
        self.case["acceptance"] = []
        self.assertEqual(self.first()["attempt_totals"], {"accepted": 0, "refused": 0, "unknown": 3})

    def test_stale_review_and_unknown_or_contradictory_checks(self):
        original = deepcopy(self.case)
        for value in (False, None):
            self.case = deepcopy(original)
            check = self.case["contract"]["checks"][0]
            self.case["acceptance"][1]["checks"][check] = value
            self.assertEqual(self.first()["totals"]["unknown"], 1)
        for name in ("baseline", "contract", "policy", "task"):
            self.case = deepcopy(original)
            self.case["acceptance"][1]["context"][name] = "0" * 64
            self.assertEqual(self.first()["attempt_outcomes"][1]["reason"], "stale_acceptance_binding")
        self.case = deepcopy(original)
        self.case["strategies"][0]["runs"][0]["attempts"][1]["execution"] = "unknown"
        self.assertEqual(self.first()["totals"]["unknown"], 1)

    def test_missing_tasks_and_mismatched_context_never_drop_observations(self):
        original = deepcopy(self.case)
        for name in ("baseline", "contract", "policy", "task"):
            with self.subTest(name=name):
                self.case = deepcopy(original)
                self.case["strategies"][1]["runs"][0]["context"][name] = "0" * 64
                report = self.report()
                self.assertFalse(report["comparable"])
                self.assertEqual(report["strategies"][1]["attempts"], 3)
                self.assertTrue(all(s["cost_per_independently_accepted_result"] is None for s in report["strategies"]))
        self.case = deepcopy(original)
        self.case["strategies"][1]["runs"].pop()
        self.case["acceptance"] = [r for r in self.case["acceptance"] if not
                                    (r["strategy_id"] == "cheap" and r["task_id"] == "negative")]
        report = self.report()
        self.assertEqual(report["incomparability"][0]["reason"], "missing_task")
        self.assertEqual(sum(report["strategies"][1]["totals"].values()), 2)
        self.assertEqual(report["strategies"][1]["totals"]["unknown"], 1)

    def test_mixed_currency_is_not_converted_or_summed(self):
        self.attempt()["costs"]["model"]["currency"] = "EUR"
        report = self.report()
        self.assertFalse(report["comparable"])
        self.assertEqual(report["strategies"][0]["cost"]["known_subtotals"], {"EUR": "2", "USD": "12"})
        self.assertIsNone(report["strategies"][0]["cost"]["total"])
        self.assertTrue(all(s["cost_per_independently_accepted_result"] is None for s in report["strategies"]))

    def test_incomplete_inventory_and_missing_final_selection(self):
        self.case["strategies"][0]["runs"][0]["attempts_complete"] = False
        report = self.first()
        self.assertIsNone(report["cost"]["total"])
        self.assertIsNone(report["latency"]["total"])
        self.assertIsNone(report["false_acceptance_rate"])
        self.case["strategies"][0]["runs"][0]["attempts_complete"] = True
        self.case["strategies"][0]["runs"][0]["final_attempt"] = None
        self.assertEqual(self.first()["totals"]["unknown"], 1)

    def test_missing_latency_does_not_invent_zero_or_hide_valid_costs(self):
        self.attempt()["latency"]["seconds"] = None
        report = self.first()
        self.assertIsNone(report["latency"]["total"])
        self.assertEqual(report["latency"]["known_subtotal"], "30")
        self.assertEqual(len(report["latency"]["missing"]), 1)
        self.assertEqual(report["cost_per_independently_accepted_result"]["amount"], "14")

    def test_failed_generation_without_candidate_retains_cost_and_refusal(self):
        self.attempt()["artifact"] = None
        self.attempt()["failure"] = "Recorded generation failed before producing output"
        self.case["acceptance"][0]["candidate_sha256"] = None
        report = self.first()
        self.assertEqual(report["attempt_outcomes"][0]["status"], "refused")
        self.assertIsNone(report["attempt_outcomes"][0]["candidate_sha256"])
        self.assertEqual(report["cost_per_independently_accepted_result"]["amount"], "14")
        with tempfile.TemporaryDirectory() as temp:
            store = EvidenceStore(Path(temp))
            event = store.record(canonical(self.case), engine=cost.ENGINE)
            self.assertNotIn("candidate:0:0:0", event["artifacts"])
            self.assertEqual(store.replay(1)["strategies"][0], report)
        self.attempt().update(execution="succeeded", failure=None)
        self.case["acceptance"][0].update(decision="accepted", checks={c: True for c in self.case["contract"]["checks"]})
        self.assertEqual(self.first()["attempt_outcomes"][0]["status"], "unknown")

    def test_decimal_precision_is_explicit_and_not_ambient(self):
        self.attempt()["costs"]["model"]["amount"] = "999999999999999999.123456789012"
        with localcontext() as ambient:
            ambient.prec = 3
            report = self.first()
        self.assertEqual(report["cost"]["total"], "1000000000000000011.123456789012")
        # The exact numerator is preserved even when the rendered quotient rounds.
        self.assertEqual(report["cost_per_independently_accepted_result"]["total_cost"], report["cost"]["total"])

    def test_invalid_measurements_fail_closed(self):
        for value in (-1, 1, True, [], "-1", "NaN", "Infinity", "1e2", "01", "1.0000000000001", "9" * 19):
            with self.subTest(value=value):
                self.attempt()["costs"]["model"]["amount"] = value
                with self.assertRaises(ValueError):
                    self.report()

    def test_duplicate_unknown_and_malformed_records_fail_closed(self):
        mutations = [
            lambda c: c.update(version=True),
            lambda c: c.update(extra="not allowed"),
            lambda c: c["tasks"].append(c["tasks"][0]),
            lambda c: c["evidence"].append(c["evidence"][0]),
            lambda c: c["strategies"].append(c["strategies"][0]),
            lambda c: c["strategies"][1].update(kind="plain"),
            lambda c: c["strategies"][0]["runs"].append(c["strategies"][0]["runs"][0]),
            lambda c: c["strategies"][0]["runs"][0].update(final_attempt="missing"),
            lambda c: c["acceptance"].append(c["acceptance"][0]),
            lambda c: c["acceptance"][0].update(attempt_id="missing"),
            lambda c: c["acceptance"][0].update(evidence_ref="missing"),
            lambda c: c["acceptance"][0].update(checks={}),
            lambda c: c["policy"].update(human_approval_required=False),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.case = decode(RAW)
                mutate(self.case)
                with self.assertRaises(ValueError):
                    self.report()
        for raw in (b'{"version":1,"version":1}', b'{"version":NaN}', b' ' * (1024 * 1024 + 1)):
            with self.assertRaises(ValueError):
                cost.analyze(raw)

    def test_exact_input_artifacts_and_mixed_engine_replay(self):
        raw = json.dumps(self.case, ensure_ascii=False, indent=4).encode() + b"\n\n"
        with tempfile.TemporaryDirectory() as temp:
            store = EvidenceStore(Path(temp))
            store.record((FIXTURES / "baseline.json").read_bytes())
            store.record((FIXTURES / "ambiguity" / "valid.json").read_bytes(), engine="ambiguity-v1")
            event = store.record(raw, engine=cost.ENGINE)
            self.assertEqual(store.get(event["artifacts"]["input"]), raw)
            self.assertEqual(store.get(event["artifacts"]["candidate:0:0:0"]), self.attempt()["artifact"].encode())
            self.assertEqual(store.get(event["artifacts"]["acceptance"]), canonical(self.case["acceptance"]))
            self.assertEqual(store.get(event["artifacts"]["evidence:ledger"]), self.case["evidence"][0]["text"].encode())
            self.assertEqual(store.replay(3), cost.analyze(raw))
            self.assertEqual(store.replay(3)["input_sha256"], fingerprint(raw))
            before = {p: p.read_bytes() for p in Path(temp).rglob("*") if p.is_file()}
            self.case["assumptions"] += " New observation; original remains intact."
            store.record(canonical(self.case), engine=cost.ENGINE)
            self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))
            report_path = store.root / "objects" / event["artifacts"]["report"]
            report = decode(report_path.read_bytes())
            report["strategies"][0]["cost"]["total"] = "0"
            event["artifacts"]["report"] = store.put(canonical(report))
            (store.root / "events" / "00000003.json").write_bytes(canonical(event))
            with self.assertRaisesRegex(ValueError, "replay result mismatch"):
                store.record(raw, engine=cost.ENGINE)
            self.assertEqual(len(list((store.root / "events").iterdir())), 4)

    def test_changed_acceptance_binding_cannot_be_replayed_as_old_report(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EvidenceStore(Path(temp))
            event = store.record(RAW, engine=cost.ENGINE)
            event["artifacts"]["acceptance"] = store.put(b"[]\n")
            (store.root / "events" / "00000001.json").write_bytes(canonical(event))
            with self.assertRaisesRegex(ValueError, "artifact lineage mismatch"):
                store.replay(1)


class CostCliTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "axiom_forge", *map(str, args)],
                              capture_output=True, text=True, check=False)

    def test_preview_record_replay_and_terminal_safety(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "never-execute"
            case = decode(RAW)
            payload = f"__import__('pathlib').Path({str(marker)!r}).touch()\n\x1b[2J\u202e"
            case["goal"] = payload
            case["evidence"][0]["text"] = payload
            case["strategies"][0]["runs"][0]["attempts"][0]["artifact"] = payload
            source = root / "input.json"
            raw = json.dumps(case, ensure_ascii=False).encode() + b"\n"
            source.write_bytes(raw)
            store = root / "store"
            result = self.cli("cost-evaluate", source, "--store", store)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(store.exists())
            for command in (("cost-evaluate", source, "--record"), ("replay", 1), ("report", 1)):
                result = self.cli(*command, "--store", store)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.isascii())
                self.assertNotIn("\x1b", result.stdout)
                self.assertEqual(result.stderr, "")
            report = json.loads(result.stdout)
            self.assertEqual(report["goal"], payload)
            self.assertEqual(report["human_approval"], "pending")
            self.assertFalse(marker.exists())
            evidence = EvidenceStore(store)
            self.assertEqual(evidence.get(evidence.events()[0]["artifacts"]["input"]), raw)

    def test_invalid_input_and_corrupt_history_exit_two_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "invalid.json"
            source.write_text('{"bad\\u001b":1,"bad\\u001b":2}')
            root = Path(temp) / "store"
            result = self.cli("cost-evaluate", source, "--record", "--store", root)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("\x1b", result.stderr)
            self.assertFalse(root.exists())
            store = EvidenceStore(root)
            event = store.record(RAW, engine=cost.ENGINE)
            (root / "objects" / event["artifacts"]["input"]).write_bytes(b"corrupt")
            result = self.cli("cost-evaluate", FIXTURES / "cost" / "matched.json", "--record", "--store", root)
            self.assertEqual(result.returncode, 2)
            self.assertIn("fingerprint mismatch", result.stderr)
            self.assertEqual(len(list((root / "events").iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
