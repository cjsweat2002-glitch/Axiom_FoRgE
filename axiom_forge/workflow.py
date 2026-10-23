"""Deterministic fixture evaluation; imported patches are data, never executed."""

import hashlib
import json
from typing import Protocol

ENGINE = "fixture-v1"
STATUSES = ("accepted", "refused", "unknown")


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
                       allow_nan=False) + "\n").encode("utf-8")


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    value = json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def fields(value: object, names: set[str], label: str) -> None:
    require(isinstance(value, dict) and set(value) == names,
            f"{label} must contain exactly: {', '.join(sorted(names))}")


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(case: dict) -> None:
    fields(case, {"version", "goal", "baseline", "contract", "policy",
                  "acceptance", "candidates"}, "case")
    require(type(case["version"]) is int and case["version"] == 1,
            "unsupported case version")
    require(nonempty(case["goal"]), "goal must be nonempty text")
    fields(case["baseline"], {"version", "files"}, "baseline")
    files = case["baseline"]["files"]
    require(isinstance(files, dict) and bool(files) and
            all(nonempty(k) and isinstance(v, str) for k, v in files.items()),
            "baseline files must map names to source text")
    fields(case["contract"], {"version", "invariants", "checks"}, "contract")
    for name in ("invariants", "checks"):
        values = case["contract"][name]
        require(isinstance(values, list) and bool(values) and
                all(nonempty(v) for v in values) and len(set(values)) == len(values),
                f"contract {name} must be distinct nonempty strings")
    fields(case["policy"], {"version", "human_approval_required"}, "policy")
    require(case["policy"]["human_approval_required"] is True,
            "human approval must remain required")
    for name in ("baseline", "contract", "policy"):
        require(nonempty(case[name]["version"]), f"{name} version must be text")
    fields(case["acceptance"], {"reviewer", "checks_reviewed"}, "acceptance")
    require(nonempty(case["acceptance"]["reviewer"]), "reviewer must be named")
    require(type(case["acceptance"]["checks_reviewed"]) is bool,
            "checks_reviewed must be boolean")
    candidates = case["candidates"]
    require(isinstance(candidates, list) and bool(candidates), "candidates are required")
    ids = set()
    for candidate in candidates:
        fields(candidate, {"id", "generator", "patch", "context", "observations"},
               "candidate")
        for name in ("id", "generator", "patch"):
            require(nonempty(candidate[name]), f"candidate {name} must be text")
        require(candidate["id"] not in ids, "candidate ids must be unique")
        ids.add(candidate["id"])
        fields(candidate["context"], {"baseline", "contract", "policy"}, "context")
        for digest in candidate["context"].values():
            require(isinstance(digest, str) and len(digest) == 64 and
                    all(c in "0123456789abcdef" for c in digest),
                    "context fingerprints must be lowercase SHA-256 digests")
        fields(candidate["observations"], set(case["contract"]["checks"]),
               "observations")
        for observation in candidate["observations"].values():
            fields(observation, {"verifier", "independent"}, "observation")
            require(all(v is None or type(v) is bool for v in observation.values()),
                    "observations must be true, false, or null (unknown)")


class Adapter(Protocol):
    """Future adapters supply observations; acceptance remains in the workflow."""

    def observe(self, candidate: dict) -> dict: ...


class FixtureAdapter:
    def observe(self, candidate: dict) -> dict:
        return candidate["observations"]


def plain_baseline(observations: dict) -> str:
    values = [item["verifier"] for item in observations.values()]
    if False in values:
        return "refused"
    return "accepted" if all(v is True for v in values) else "unknown"


def classify(case: dict, candidate: dict, observations: dict, context: dict) -> tuple:
    for name in ("baseline", "contract", "policy"):
        if candidate["context"][name] != context[name]:
            return "unknown", f"changed_{name}", "Recheck against the current context."
    acceptance = case["acceptance"]
    if not acceptance["checks_reviewed"] or acceptance["reviewer"] == candidate["generator"]:
        return "unknown", "unreviewed_acceptance", "Obtain a separate review of the checks."
    values = list(observations.values())
    if any(v["verifier"] is None or v["independent"] is None for v in values):
        return "unknown", "insufficient_evidence", "Collect the missing check observations."
    if any(v["verifier"] != v["independent"] for v in values):
        return "unknown", "faulty_verifier", "Replay a minimal case with a separately reviewed checker."
    if any(v["independent"] is False for v in values):
        return "refused", "genuine_regression", "Isolate the failing invariant before another candidate."
    return "accepted", "checks_passed", "Request human review before applying or reusing the patch."


def evaluate(case: dict) -> dict:
    validate(case)
    adapter: Adapter = FixtureAdapter()
    context = {name: fingerprint(canonical(case[name]))
               for name in ("baseline", "contract", "policy")}
    results = []
    for candidate in case["candidates"]:
        observations = adapter.observe(candidate)
        status, reason, diagnostic = classify(case, candidate, observations, context)
        results.append({
            "id": candidate["id"], "status": status, "reason": reason,
            "diagnostic_proposal": diagnostic,
            "plain_baseline": plain_baseline(observations),
            "patch_sha256": fingerprint(candidate["patch"].encode("utf-8")),
            "observed_context": candidate["context"],
            "observations": observations,
        })
    return {
        "engine": ENGINE, "goal": case["goal"], "context": context,
        "acceptance": case["acceptance"], "candidates": results,
        "totals": {s: sum(c["status"] == s for c in results) for s in STATUSES},
        "plain_baseline_totals": {
            s: sum(c["plain_baseline"] == s for c in results) for s in STATUSES},
        "human_approval": "pending",
        "unknowns": ["Fixture observations are asserted, not live execution evidence.",
                     "Reviewer identities are labels, not authenticated approvals.",
                     "Real task completion, cost, diagnostic usefulness, and error rates are unmeasured."],
    }
