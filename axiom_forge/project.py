"""A read-only project review cycle over recorded evidence, never a tool runner."""

from . import ambiguity
from .store import EvidenceStore
from .workflow import ENGINE, canonical, decode, fingerprint


def evaluate_project(raw: bytes, store: EvidenceStore) -> dict:
    case = ambiguity.parse(raw)
    digest = fingerprint(raw)
    context = {name: fingerprint(canonical(case[name]))
               for name in ("baseline", "contract", "policy")}
    # Full-history replay is integrity validation, not a new ambiguity test run.
    events = store.events()
    matches = []
    prior = []
    comparisons = []
    for event in events:
        report = decode(store.get(event["artifacts"]["report"]))
        reference = {"sequence": event["sequence"], "artifacts": event["artifacts"]}
        if event["engine"] == ambiguity.ENGINE and report["scope"] == case["scope"]:
            if report["input_sha256"] == digest:
                matches.append((reference, report))
            else:
                prior.append(reference)
        elif event["engine"] == ENGINE and report["context"] == context:
            comparisons.append({**reference, "totals": report["totals"],
                                "plain_baseline_totals": report["plain_baseline_totals"],
                                "limitation": "Recorded fixture comparison only; matching context does not prove project completion."})
    selected, report = matches[-1] if matches else (None, None)
    steps = ([{"finding": f["id"], "clarification": f["proposed_clarification"],
               "proposed_checks": f["proposed_checks"]} for f in report["findings"]]
             if report else [])
    if not report:
        steps.append({"clarification": "Request an explicit ambiguity run for this exact input; no applicable recorded result is available."})
    elif not steps:
        steps.append({"clarification": "Request separate review of coverage and intended meaning; no structural findings is not acceptance."})
    return {
        "engine": "project-review-v1", "scope": case["scope"], "input_sha256": digest,
        "context": context, "status": report["status"] if report else "unknown",
        "recorded_result": selected, "other_inputs_same_scope": prior,
        "findings": report["findings"] if report else [],
        "totals": report["totals"] if report else None,
        "recorded_fixture_comparisons": comparisons,
        "proposed_next_steps": steps,
        "cycle": "Review recorded evidence, request clarification, separately review changes, explicitly record a new run, then reevaluate.",
        "tester_execution": "not_requested", "human_approval": "pending",
        "unknowns": ambiguity.UNKNOWN + [
            "This cycle consumes recorded results only; it does not schedule or execute new tests.",
            "Missing comparisons and real performance measurements remain unknown; no improvement is established.",
        ],
    }
