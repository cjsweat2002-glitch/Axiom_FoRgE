"""Local content-addressed objects and an append-only, hash-linked event log."""

import os
from pathlib import Path

from . import ambiguity
from .workflow import ENGINE, canonical, decode, evaluate, fields, fingerprint, require


def prepare(raw: bytes, engine: str) -> dict[str, bytes]:
    """Versioned deterministic artifacts; fixture-v1 output stays unchanged."""
    require(engine in (ENGINE, ambiguity.ENGINE), "unsupported event engine")
    if engine == ambiguity.ENGINE:
        report = ambiguity.analyze(raw)
        case = decode(raw)
        extra = {f"evidence:{item['id']}": item["text"].encode("utf-8")
                 for item in case["evidence"]}
    else:
        case = decode(raw)
        report = evaluate(case)
        extra = {f"patch:{item['id']}": item["patch"].encode("utf-8")
                 for item in case["candidates"]}
    return {"input": raw, "report": canonical(report),
            **{name: canonical(case[name]) for name in ("baseline", "contract", "policy")},
            **extra}


class EvidenceStore:
    def __init__(self, root: Path):
        self.root = root

    def put(self, data: bytes) -> str:
        digest = fingerprint(data)
        directory = self.root / "objects"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / digest
        try:
            with path.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            require(path.read_bytes() == data, f"corrupt existing object: {digest}")
        return digest

    def get(self, digest: str) -> bytes:
        require(isinstance(digest, str) and len(digest) == 64 and
                all(c in "0123456789abcdef" for c in digest), "invalid object digest")
        data = (self.root / "objects" / digest).read_bytes()
        require(fingerprint(data) == digest, f"object fingerprint mismatch: {digest}")
        return data

    def events(self) -> list[dict]:
        events = []
        previous = None
        for sequence, path in enumerate(sorted((self.root / "events").glob("*.json")), 1):
            require(path.name == f"{sequence:08d}.json", "event sequence has a gap")
            data = path.read_bytes()
            event = decode(data)
            fields(event, {"sequence", "previous", "engine", "artifacts"}, "event")
            require(type(event["sequence"]) is int and event["sequence"] == sequence
                    and event["previous"] == previous,
                    "event lineage mismatch")
            require(event["engine"] in (ENGINE, ambiguity.ENGINE), "unsupported event engine")
            # Every retained event must be coherent before append or replay.
            self._validate_artifacts(event["artifacts"], event["engine"])
            previous = fingerprint(data)
            events.append(event)
        return events

    def _validate_artifacts(self, artifacts: dict, engine: str) -> None:
        required = {"input", "report", "baseline", "contract", "policy"}
        require(isinstance(artifacts, dict) and required <= artifacts.keys(),
                "invalid event artifacts")
        for digest in artifacts.values():
            self.get(digest)
        content = prepare(self.get(artifacts["input"]), engine)
        require(content["report"] == self.get(artifacts["report"]), "replay result mismatch")
        expected = {name: fingerprint(data) for name, data in content.items()}
        require(artifacts == expected, "artifact lineage mismatch")

    def record(self, raw: bytes, *, engine: str = ENGINE) -> dict:
        content = prepare(raw, engine)
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / ".writer-lock"
        try:
            lock.mkdir()
        except FileExistsError:
            raise ValueError("evidence store is locked; another writer or interrupted run needs review") from None
        try:
            events = self.events()
            artifacts = {name: self.put(data) for name, data in content.items()}
            directory = self.root / "events"
            directory.mkdir(exist_ok=True)
            sequence = len(events) + 1
            previous = None
            if events:
                previous = fingerprint((directory / f"{sequence - 1:08d}.json").read_bytes())
            event = {"sequence": sequence, "previous": previous, "engine": engine,
                     "artifacts": artifacts}
            with (directory / f"{sequence:08d}.json").open("xb") as stream:
                stream.write(canonical(event))
                stream.flush()
                os.fsync(stream.fileno())
            return event
        finally:
            lock.rmdir()

    def replay(self, sequence: int) -> dict:
        events = self.events()
        require(1 <= sequence <= len(events), "event does not exist")
        event = events[sequence - 1]
        # events() already recomputed and checked every report against its input.
        return decode(self.get(event["artifacts"]["report"]))
