from pathlib import Path
import tempfile
import unittest

from axiom_forge.store import EvidenceStore
from axiom_forge.workflow import canonical, decode, fingerprint

FIXTURE = Path(__file__).parent / "fixtures" / "baseline.json"


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = EvidenceStore(Path(self.temp.name))
        self.raw = FIXTURE.read_bytes()

    def test_exact_inputs_deduplication_and_append_only_history(self):
        first = self.store.record(self.raw)
        path = self.store.root / "events" / "00000001.json"
        original = path.read_bytes()
        objects = set((self.store.root / "objects").iterdir())
        second = self.store.record(self.raw)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(second["previous"], fingerprint(original))
        self.assertEqual(objects, set((self.store.root / "objects").iterdir()))
        self.assertEqual(self.store.get(first["artifacts"]["input"]), self.raw)
        self.assertEqual(self.store.replay(1), self.store.replay(2))

    def test_contract_changes_preserve_historical_outcomes(self):
        self.store.record(self.raw)
        case = decode(self.raw)
        case["contract"]["version"] = "add-v2"
        self.store.record(canonical(case))
        self.assertEqual(self.store.replay(1)["totals"]["accepted"], 1)
        self.assertEqual(self.store.replay(2)["totals"]["unknown"], 5)

    def test_modified_object_is_detected_and_never_overwritten(self):
        event = self.store.record(self.raw)
        path = self.store.root / "objects" / event["artifacts"]["input"]
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            self.store.replay(1)
        with self.assertRaisesRegex(ValueError, "corrupt existing"):
            self.store.put(self.raw)
        self.assertEqual(path.read_bytes(), b"tampered")

    def test_broken_chain_and_deleted_event_are_detected(self):
        self.store.record(self.raw)
        self.store.record(self.raw)
        path = self.store.root / "events" / "00000001.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "lineage mismatch"):
            self.store.replay(2)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "sequence has a gap"):
            self.store.replay(2)

    def test_replay_rejects_forged_result_and_artifact_links(self):
        event = self.store.record(self.raw)
        path = self.store.root / "events" / "00000001.json"
        report = self.store.replay(1)
        report["human_approval"] = "approved"
        original_digest = event["artifacts"]["report"]
        event["artifacts"]["report"] = self.store.put(canonical(report))
        path.write_bytes(canonical(event))
        with self.assertRaisesRegex(ValueError, "replay result mismatch"):
            self.store.replay(1)
        event["artifacts"]["report"] = original_digest
        event["artifacts"]["contract"] = event["artifacts"]["policy"]
        path.write_bytes(canonical(event))
        with self.assertRaisesRegex(ValueError, "artifact lineage mismatch"):
            self.store.replay(1)

    def test_lock_blocks_writers_without_changing_history(self):
        (self.store.root / ".writer-lock").mkdir()
        with self.assertRaisesRegex(ValueError, "locked"):
            self.store.record(self.raw)
        self.assertFalse((self.store.root / "events").exists())

    def test_invalid_input_does_not_create_evidence(self):
        with self.assertRaises(ValueError):
            self.store.record(b'{}')
        self.assertEqual(list(self.store.root.iterdir()), [])

    def test_invalid_event_and_digest_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "event does not exist"):
            self.store.replay(1)
        with self.assertRaisesRegex(ValueError, "invalid object digest"):
            self.store.get("../secret")
