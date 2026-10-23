"""Accounting over supplied records only; never execute or approve candidates."""

from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import re

from .workflow import canonical, decode, fields, fingerprint, nonempty, require, validate_context

ENGINE = "cost-v1"
COMPONENTS = ("model", "compute", "review", "storage")
STATUSES = ("accepted", "refused", "unknown")


def records(value, names, label, limit):
    require(isinstance(value, list) and len(value) <= limit, f"invalid {label} list")
    ids = set()
    for item in value:
        fields(item, names | {"id"}, label)
        require(nonempty(item["id"]) and item["id"] not in ids, f"duplicate or invalid {label} id")
        ids.add(item["id"])
    return ids


def digest(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "expected lowercase SHA-256 digest")


def context(value):
    fields(value, {"baseline", "contract", "policy", "task"}, "run context")
    for value in value.values():
        digest(value)


def number(value):
    require(value is None or (isinstance(value, str) and
            re.fullmatch(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?", value) is not None),
            "measurements must be nonnegative decimal strings or null")


def reference(value, evidence):
    require(value is None or (isinstance(value, str) and value in evidence),
            "unknown evidence reference")


def candidate_digest(attempt):
    artifact = attempt["artifact"]
    return fingerprint(artifact.encode("utf-8")) if artifact is not None else None


def parse(raw: bytes) -> dict:
    require(len(raw) <= 1024 * 1024, "cost input exceeds 1 MiB")
    case = decode(raw)
    fields(case, {"version", "goal", "baseline", "contract", "policy", "data_kind",
                  "assumptions", "tasks", "evidence", "strategies", "acceptance"}, "cost input")
    require(type(case["version"]) is int and case["version"] == 1, "unsupported cost input version")
    require(nonempty(case["goal"]) and nonempty(case["assumptions"]), "goal and assumptions are required")
    require(case["data_kind"] in ("simulated", "recorded"), "invalid data kind")
    validate_context(case)
    require(len(case["contract"]["checks"]) <= 128, "too many acceptance checks")
    tasks = records(case["tasks"], {"input"}, "tasks", 64)
    require(bool(tasks), "tasks are required")
    for task in case["tasks"]:
        require(nonempty(task["input"]), "task input is required")
    evidence = records(case["evidence"], {"source", "text"}, "evidence", 2048)
    for item in case["evidence"]:
        require(nonempty(item["source"]) and nonempty(item["text"]), "evidence source and text are required")
        item["text"].encode("utf-8")
    records(case["strategies"], {"kind", "description", "runs"}, "strategies", 8)
    require(len(case["strategies"]) >= 2 and
            sum(s["kind"] == "plain" for s in case["strategies"]) == 1,
            "exactly one plain strategy and at least one alternative are required")
    attempts = set()
    for strategy in case["strategies"]:
        require(strategy["kind"] in ("plain", "cheap_first", "evidence_guided") and
                nonempty(strategy["description"]), "invalid strategy")
        require(isinstance(strategy["runs"], list) and len(strategy["runs"]) <= 64, "invalid runs")
        seen = set()
        for run in strategy["runs"]:
            fields(run, {"task_id", "context", "attempts_complete", "attempts", "final_attempt"}, "run")
            task_id = run["task_id"]
            require(isinstance(task_id, str) and task_id in tasks and task_id not in seen,
                    "duplicate or unknown task run")
            seen.add(task_id)
            context(run["context"])
            require(type(run["attempts_complete"]) is bool, "attempts_complete must be boolean")
            ids = records(run["attempts"], {"input", "generator", "artifact", "claim", "execution",
                          "failure", "costs", "latency"}, "attempts", 32)
            require(run["final_attempt"] is None or
                    (isinstance(run["final_attempt"], str) and run["final_attempt"] in ids),
                    "unknown final attempt")
            for attempt in run["attempts"]:
                attempts.add((strategy["id"], task_id, attempt["id"]))
                require(all(nonempty(attempt[n]) for n in ("input", "generator")),
                        "attempt input and generator are required")
                require(attempt["artifact"] is None or nonempty(attempt["artifact"]),
                        "candidate artifact must be nonempty text or null")
                candidate_digest(attempt)  # Reject unencodable text before storage.
                require(attempt["claim"] in STATUSES and
                        attempt["execution"] in ("succeeded", "failed", "unknown"), "invalid attempt outcome")
                require(nonempty(attempt["failure"]) if attempt["execution"] == "failed"
                        else attempt["failure"] is None, "failure detail must match execution status")
                require(isinstance(attempt["costs"], dict) and set(attempt["costs"]) <= set(COMPONENTS),
                        "invalid cost components")
                for cost in attempt["costs"].values():
                    fields(cost, {"amount", "currency", "quantity", "unit", "evidence_ref", "complete"}, "cost")
                    number(cost["amount"])
                    number(cost["quantity"])
                    require(isinstance(cost["currency"], str) and
                            re.fullmatch(r"[A-Z]{3}", cost["currency"]) is not None, "invalid currency label")
                    require(nonempty(cost["unit"]) and type(cost["complete"]) is bool, "invalid cost unit/completeness")
                    reference(cost["evidence_ref"], evidence)
                fields(attempt["latency"], {"seconds", "evidence_ref"}, "latency")
                number(attempt["latency"]["seconds"])
                reference(attempt["latency"]["evidence_ref"], evidence)
    require(isinstance(case["acceptance"], list) and len(case["acceptance"]) <= len(attempts),
            "invalid acceptance records")
    seen = set()
    for review in case["acceptance"]:
        fields(review, {"strategy_id", "task_id", "attempt_id", "reviewer", "evidence_ref",
                        "candidate_sha256", "context", "decision", "checks"}, "acceptance record")
        require(all(nonempty(review[n]) for n in ("strategy_id", "task_id", "attempt_id", "reviewer")),
                "acceptance identities must be text")
        key = (review["strategy_id"], review["task_id"], review["attempt_id"])
        require(key in attempts and key not in seen, "duplicate or dangling acceptance record")
        seen.add(key)
        reference(review["evidence_ref"], evidence)
        if review["candidate_sha256"] is not None:
            digest(review["candidate_sha256"])
        context(review["context"])
        require(review["decision"] in STATUSES, "invalid acceptance decision")
        fields(review["checks"], set(case["contract"]["checks"]), "acceptance checks")
        require(all(v is None or type(v) is bool for v in review["checks"].values()),
                "acceptance checks must be true, false, or null")
    return case


def independent(attempt, review, expected_context, run_context):
    if run_context != expected_context:
        return "unknown", "mismatched_run_context"
    if review is None or review["evidence_ref"] is None:
        return "unknown", "missing_external_acceptance_evidence"
    if review["reviewer"] == attempt["generator"]:
        return "unknown", "candidate_cannot_accept_itself"
    if review["context"] != expected_context or review["candidate_sha256"] != candidate_digest(attempt):
        return "unknown", "stale_acceptance_binding"
    checks = list(review["checks"].values())
    if review["decision"] == "unknown" or None in checks:
        return "unknown", "incomplete_acceptance"
    if review["decision"] == "refused" and False in checks:
        return "refused", "externally_supplied_refusal"
    if (review["decision"] == "accepted" and all(checks) and
            attempt["execution"] == "succeeded" and attempt["artifact"] is not None):
        return "accepted", "externally_supplied_acceptance"
    return "unknown", "inconsistent_acceptance_or_execution"


def rate(numerator, denominator, complete=True):
    return {"numerator": numerator, "denominator": denominator} if complete and denominator else None


def decimal_text(value):
    return format(value, "f")


def summarize(case, strategy, expected, reviews):
    runs = {run["task_id"]: run for run in strategy["runs"]}
    outcomes = []
    task_results = []
    subtotals = {}
    components = {}
    missing_costs = []
    missing_latency = []
    latency = Decimal(0)
    inventory_complete = True
    retries = 0
    for task in case["tasks"]:
        run = runs.get(task["id"])
        inventory_complete &= run is not None and run["attempts_complete"]
        selected = "unknown"
        if run is not None:
            retries += max(0, len(run["attempts"]) - 1)
            for attempt in run["attempts"]:
                key = (strategy["id"], task["id"], attempt["id"])
                status, reason = independent(attempt, reviews.get(key), expected[task["id"]], run["context"])
                outcomes.append({"task_id": task["id"], "attempt_id": attempt["id"], "status": status,
                                 "reason": reason, "claim": attempt["claim"], "execution": attempt["execution"],
                                 "failure": attempt["failure"], "candidate_sha256": candidate_digest(attempt)})
                if attempt["id"] == run["final_attempt"]:
                    selected = status
                for name in COMPONENTS:
                    cost = attempt["costs"].get(name)
                    known = cost is not None and cost["amount"] is not None and cost["evidence_ref"] is not None
                    if known:
                        currency = cost["currency"]
                        amount = Decimal(cost["amount"])
                        subtotals[currency] = subtotals.get(currency, Decimal(0)) + amount
                        bucket = components.setdefault(name, {})
                        bucket[currency] = bucket.get(currency, Decimal(0)) + amount
                    if not known or not cost["complete"]:
                        missing_costs.append({"task_id": task["id"], "attempt_id": attempt["id"], "component": name})
                duration = attempt["latency"]
                if duration["seconds"] is not None and duration["evidence_ref"] is not None:
                    latency += Decimal(duration["seconds"])
                else:
                    missing_latency.append({"task_id": task["id"], "attempt_id": attempt["id"]})
        task_results.append({"task_id": task["id"], "status": selected,
                             "final_attempt": run["final_attempt"] if run else None})
    totals = {s: sum(t["status"] == s for t in task_results) for s in STATUSES}
    attempt_totals = {s: sum(t["status"] == s for t in outcomes) for s in STATUSES}
    claims = {s: [a for a in outcomes if a["claim"] == s] for s in STATUSES}
    false_accepts = sum(a["status"] == "refused" for a in claims["accepted"])
    false_refusals = sum(a["status"] == "accepted" for a in claims["refused"])
    acceptance_complete = not totals["unknown"] and not attempt_totals["unknown"] and inventory_complete
    cost_complete = not missing_costs and inventory_complete and bool(outcomes) and len(subtotals) == 1
    currency = next(iter(subtotals)) if len(subtotals) == 1 else None
    return {
        "id": strategy["id"], "kind": strategy["kind"], "tasks": task_results, "totals": totals,
        "attempts": len(outcomes), "retries": retries, "failures": sum(a["execution"] == "failed" for a in outcomes),
        "unknown_executions": sum(a["execution"] == "unknown" for a in outcomes),
        "attempt_outcomes": outcomes, "attempt_totals": attempt_totals,
        "inventory_complete": inventory_complete, "acceptance_complete": acceptance_complete,
        "acceptance_rate": rate(totals["accepted"], len(task_results), acceptance_complete),
        "claims": {s: len(a) for s, a in claims.items()},
        "false_acceptances": false_accepts, "false_refusals": false_refusals,
        "unreviewed_accepted_claims": sum(a["status"] == "unknown" for a in claims["accepted"]),
        "false_acceptance_rate": rate(false_accepts, len(claims["accepted"]), inventory_complete and
                                      all(a["status"] != "unknown" for a in claims["accepted"])),
        "false_refusal_rate": rate(false_refusals, len(claims["refused"]), inventory_complete and
                                   all(a["status"] != "unknown" for a in claims["refused"])),
        "cost": {"known_subtotals": {c: decimal_text(v) for c, v in subtotals.items()},
                 "by_component": {n: {c: decimal_text(v) for c, v in b.items()} for n, b in components.items()},
                 "missing_or_partial": missing_costs, "complete": cost_complete, "currency": currency,
                 "total": decimal_text(subtotals[currency]) if cost_complete else None},
        "latency": {"unit": "seconds", "kind": "sum_of_attempt_durations", "known_subtotal": decimal_text(latency),
                    "missing": missing_latency, "total": decimal_text(latency) if inventory_complete and not missing_latency else None},
    }


def analyze(raw: bytes) -> dict:
    case = parse(raw)
    frozen = {n: fingerprint(canonical(case[n])) for n in ("baseline", "contract", "policy")}
    expected = {t["id"]: {**frozen, "task": fingerprint(canonical(t))} for t in case["tasks"]}
    reviews = {(r["strategy_id"], r["task_id"], r["attempt_id"]): r for r in case["acceptance"]}
    mismatches = []
    for strategy in case["strategies"]:
        runs = {r["task_id"]: r for r in strategy["runs"]}
        for task_id, identity in expected.items():
            if task_id not in runs or runs[task_id]["context"] != identity:
                mismatches.append({"strategy_id": strategy["id"], "task_id": task_id,
                                   "reason": "missing_task" if task_id not in runs else "context_mismatch"})
    # The bounded decimal inputs and record count fit exactly within 50 digits.
    with localcontext() as arithmetic:
        arithmetic.prec = 50
        arithmetic.rounding = ROUND_HALF_EVEN
        strategies = [summarize(case, s, expected, reviews) for s in case["strategies"]]
        currencies = {c for s in strategies for c in s["cost"]["known_subtotals"]}
        if len(currencies) > 1:
            mismatches.append({"reason": "mixed_currencies", "currencies": sorted(currencies)})
        for strategy in strategies:
            reasons = []
            if mismatches:
                reasons.append("incomparable_runs")
            if not strategy["cost"]["complete"]:
                reasons.append("incomplete_cost_or_attempt_inventory")
            if not strategy["acceptance_complete"]:
                reasons.append("incomplete_independent_acceptance")
            count = strategy["totals"]["accepted"]
            if count == 0:
                reasons.append("zero_independently_accepted_results")
            strategy["cost_per_independently_accepted_result"] = None
            strategy["ratio_unavailable_reasons"] = reasons
            if not reasons:
                with localcontext() as division:
                    division.prec = 28
                    strategy["cost_per_independently_accepted_result"] = {
                        "amount": decimal_text(Decimal(strategy["cost"]["total"]) / count),
                        "currency": strategy["cost"]["currency"], "total_cost": strategy["cost"]["total"],
                        "independently_accepted_results": count,
                    }
    return {
        "engine": ENGINE, "input_sha256": fingerprint(raw), "goal": case["goal"], "context": frozen,
        "data_kind": case["data_kind"],
        "notice": ("SIMULATED DATA: arithmetic demonstration only; no measured live-model savings or actual independent review."
                   if case["data_kind"] == "simulated" else
                   "USER-SUPPLIED RECORDS: source authenticity, completeness and reviewer independence are not authenticated."),
        "assumptions": case["assumptions"], "comparable": not mismatches, "incomparability": mismatches,
        "task_contexts": expected, "strategies": strategies, "human_approval": "pending",
        "evidence": {e["id"]: {"source": e["source"], "sha256": fingerprint(e["text"].encode("utf-8"))}
                     for e in case["evidence"]},
        "unknowns": ["Labels and hashes do not authenticate identities, provenance, review or inventory completeness.",
                     "No candidates or checks were executed; supplied external outcomes are not verified ground truth.",
                     "Commercial value, customer demand, generalization and diagnostic usefulness remain unmeasured."],
    }
