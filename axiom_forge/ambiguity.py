"""Bounded structural ambiguity checks. All supplied text is inert evidence."""

from itertools import combinations

from .workflow import canonical, decode, fields, fingerprint, nonempty, require, validate_context

ENGINE = "ambiguity-v1"
MAX_INPUT_BYTES = 1024 * 1024
LIMITS = {"requirements": 64, "assumptions": 64, "evidence": 128, "probes": 32}
UNKNOWN = [
    "Natural-language meaning and undeclared alternatives are not evaluated.",
    "Evidence presence does not establish correctness, execution, or independent review.",
    "Proposed checks require separate review; no acceptance criteria are changed.",
    "Human approval, diagnostic usefulness, completion, cost, and error rates are unmeasured.",
]


def records(value: object, names: set[str], label: str, limit: int) -> set[str]:
    require(isinstance(value, list) and len(value) <= limit,
            f"{label} must be a list of at most {limit} entries")
    ids = set()
    for item in value:
        fields(item, names | {"id"}, label)
        require(nonempty(item["id"]) and item["id"] not in ids,
                f"{label} ids must be unique nonempty text")
        ids.add(item["id"])
    return ids


def references(value: object, known: set[str], label: str) -> None:
    require(isinstance(value, list) and all(nonempty(v) for v in value),
            f"{label} must be a list of text references")
    require(len(set(value)) == len(value) and set(value) <= known,
            f"{label} must be unique known references")


def parse(raw: bytes) -> dict:
    require(len(raw) <= MAX_INPUT_BYTES, "ambiguity input exceeds 1 MiB")
    case = decode(raw)
    fields(case, {"version", "goal", "scope", "baseline", "contract", "policy",
                  "requirements", "assumptions", "probes", "evidence",
                  "acceptance_evidence"}, "ambiguity input")
    require(type(case["version"]) is int and case["version"] == 1,
            "unsupported ambiguity input version")
    require(nonempty(case["goal"]), "goal must be nonempty text")
    fields(case["scope"], {"kind", "id"}, "scope")
    require(case["scope"]["kind"] in ("project", "component") and nonempty(case["scope"]["id"]),
            "scope must name a project or component")
    validate_context(case, allow_empty_checks=True)
    checks = set(case["contract"]["checks"])
    require(len(checks) <= 128, "at most 128 acceptance checks are supported")
    evidence = records(case["evidence"], {"text"}, "evidence", LIMITS["evidence"])
    for item in case["evidence"]:
        require(nonempty(item["text"]), "evidence text must be nonempty")
        # Fail before storage on unencodable surrogate text.
        item["text"].encode("utf-8")
    probes = records(case["probes"], {"description"}, "probes", LIMITS["probes"])
    for probe in case["probes"]:
        require(nonempty(probe["description"]), "probe description must be nonempty")
    records(case["assumptions"], {"key", "value", "evidence_refs"},
            "assumptions", LIMITS["assumptions"])
    for item in case["assumptions"]:
        require(nonempty(item["key"]) and nonempty(item["value"]),
                "assumption key and value must be nonempty text")
        references(item["evidence_refs"], evidence, "assumption evidence")
    records(case["requirements"], {"statement", "checks", "evidence_refs", "interpretations"},
            "requirements", LIMITS["requirements"])
    require(bool(case["requirements"]), "at least one explicit requirement is required")
    for item in case["requirements"]:
        require(nonempty(item["statement"]), "requirement statement must be nonempty")
        references(item["checks"], checks, "requirement checks")
        references(item["evidence_refs"], evidence, "requirement evidence")
        records(item["interpretations"], {"statement", "expectations"}, "interpretations", 8)
        for alternative in item["interpretations"]:
            require(nonempty(alternative["statement"]), "interpretation statement must be nonempty")
            expected = alternative["expectations"]
            require(isinstance(expected, dict) and set(expected) <= probes and
                    all(nonempty(v) for v in expected.values()),
                    "expectations must map known probes to nonempty outcome labels")
    acceptance = case["acceptance_evidence"]
    require(isinstance(acceptance, dict) and set(acceptance) <= checks,
            "acceptance_evidence must map known checks to evidence references")
    for refs in acceptance.values():
        references(refs, evidence, "acceptance evidence")
    return case


def analyze(raw: bytes) -> dict:
    case = parse(raw)
    findings = []

    def add(kind, severity, sources, refs, clarification, proposals=None):
        findings.append({
            "id": f"finding-{len(findings) + 1}", "kind": kind, "severity": severity,
            "uncertainty": "Declared structure observed; intended meaning and truth remain unknown.",
            "sources": sources, "evidence_refs": sorted(set(refs)),
            "proposed_clarification": clarification, "proposed_checks": proposals or [],
            "approval": "pending",
        })

    for index, item in enumerate(case["requirements"]):
        source = f"/requirements/{index}"
        refs = item["evidence_refs"]
        if not item["checks"]:
            add("missing_acceptance_checks", "high", [source + "/checks"], refs,
                "Propose one observable example and expected outcome for this requirement; seek separate review.")
        if not refs:
            add("missing_requirement_evidence", "medium", [source + "/evidence_refs"], [],
                "Attach the source of this requirement without treating it as approval.")
        alternatives = item["interpretations"]
        if not alternatives:
            add("missing_interpretation_evidence", "medium", [source + "/interpretations"], refs,
                "Record the intended interpretation and any known alternatives; absence does not prove uniqueness.")
        elif len(alternatives) > 1:
            proposals = []
            for left, right in combinations(alternatives, 2):
                shared = set(left["expectations"]) & set(right["expectations"])
                distinguishing = sorted(p for p in shared
                                        if left["expectations"][p] != right["expectations"][p])
                probe = distinguishing[0] if distinguishing else None
                proposals.append({
                    "interpretations": [left["id"], right["id"]], "probe": probe,
                    "expected_outcomes": ({a["id"]: a["expectations"][probe]
                                           for a in (left, right)} if probe else {}),
                    "status": "proposed" if probe else "unknown",
                    "rationale": ("One supplied probe distinguishes this pair's declared outcomes; "
                                  "ties use probe ID order, not measured cost." if probe else
                                  "No supplied probe distinguishes this pair; request one example with differing outcomes."),
                })
            add("multiple_interpretations", "high", [source + "/interpretations", "/probes"], refs,
                "Review the competing interpretations and the proposed pairwise checks; do not select a winner automatically.",
                proposals)

    for index, check in enumerate(case["contract"]["checks"]):
        if not case["acceptance_evidence"].get(check):
            add("missing_acceptance_evidence", "high", [f"/contract/checks/{index}", "/acceptance_evidence"], [],
                "Attach a recorded observation for this check, including exact inputs and expected/actual outcomes; presence alone is not a pass.")

    groups = {}
    for index, assumption in enumerate(case["assumptions"]):
        groups.setdefault(assumption["key"], []).append((index, assumption))
        if not assumption["evidence_refs"]:
            add("unsupported_assumption", "medium", [f"/assumptions/{index}"], [],
                "Request source evidence for this declared assumption; keep it unapproved.")
    for group in groups.values():
        if len({item["value"] for _, item in group}) > 1:
            add("conflicting_assumptions", "high", [f"/assumptions/{i}" for i, _ in group],
                [ref for _, item in group for ref in item["evidence_refs"]],
                "Request one boundary example that selects between the declared values of this key, or clarify their separate scopes.")

    return {
        "engine": ENGINE, "input_sha256": fingerprint(raw), "goal": case["goal"],
        "scope": case["scope"],
        "context": {name: fingerprint(canonical(case[name]))
                    for name in ("baseline", "contract", "policy")},
        "status": "needs_clarification" if findings else "no_structural_findings",
        "semantic_status": "unknown", "human_approval": "pending",
        "findings": findings,
        "totals": {s: sum(f["severity"] == s for f in findings) for s in ("high", "medium")},
        "evidence": {item["id"]: fingerprint(item["text"].encode("utf-8"))
                     for item in case["evidence"]},
        "probes": case["probes"], "unknowns": UNKNOWN,
    }
