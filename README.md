# Axiom_FoRgE
Turning raw data into verified, reusable knowledge.

Axiom_FoRgE is the implementation foundation for **MONAS Crucible —
Evidence-Evolving AI**: a local-first workbench for transforming raw inputs into
reproducible, evidence-backed knowledge. The shared standard is a proposal for
this project, not a recognized industry certification or a claim of proven AI
performance.

The working contract for every agent is:

**Raw input → explicit contract → isolated candidate → independent verification
→ immutable evidence lineage → human-approved reusable knowledge.**

## Bounded first increment

This Python CLI compares **deterministic fixture observations** for candidate
patches in one small Python addition workflow. It ingests a goal and versioned
contract, exposes them for review, classifies candidates, preserves evidence,
replays the comparison, and exports a human-readable report. It uses only the
Python standard library at runtime; Python 3.11 or newer is required.

Candidate patches and source text are inert artifacts. The CLI does not generate,
execute, apply, or approve patches. The fixture adapter is the boundary for later
execution adapters; isolated workspaces, authenticated review, live Python checks,
model routing, and recipe promotion are future work. Blender, model training, and
an agent marketplace are outside this release scope.

## Run locally

From the repository root, no dependency installation is needed:

```sh
python3 -m axiom_forge inspect tests/fixtures/baseline.json
python3 -m axiom_forge run tests/fixtures/baseline.json
python3 -m axiom_forge replay 1
python3 -m axiom_forge report 1 > /tmp/axiom-forge-report.txt
python3 -m unittest discover -s tests -v
```

`inspect` is read-only and presents the goal, contract, policy, and proposed
comparison. `run` appends one event and prints its sequence and artifact digests.
`replay` checks the event chain and object hashes, recomputes every retained report,
and requires byte-identical results. `report` performs the same verification before
printing. Use `--store /path/to/evidence` on `run`, `replay`, and `report` to select
a store other than `.axiom-forge/`. A malformed input or failed integrity check
exits with code 2; command success (0) means the operation completed, not that a
candidate was accepted. Candidate outcomes appear in the report.

Human-readable reports quote goals, candidate IDs, and evidence paths as ASCII
JSON strings, escaping terminal controls and embedded line breaks. Error details
are escaped the same way. This changes display only; original evidence bytes and
the values returned by parsing JSON output remain intact.

An optional install with `python3 -m pip install .` exposes the same commands as
`axiom-forge`. Packaging uses setuptools; there are no runtime dependencies.

## Recorded cost/quality comparison

`python3 -m axiom_forge cost-evaluate tests/fixtures/cost/matched.json` compares
explicitly supplied plain and cheap-first task records. **The bundled data is
simulated; it demonstrates arithmetic, not measured savings or actual independent
review.** All attempts and retries contribute to costs. Missing/partial costs,
unknown acceptance, zero acceptances, or incomparable runs suppress cost-per-result
ratios. Separate external acceptance records bind exact candidates and context;
candidate claims cannot grant acceptance or approval.

Use `--record --store /path/to/evidence` to preserve inputs and reports for the
existing `replay` and `report` commands. No model calls or candidate execution occur.
See [the input contract and proposed pilot criteria](docs/cost-evaluation.md) for
units, currencies, provenance, quality metrics, limitations, and future real records.

## Evidence and acceptance

The version-1 input format is demonstrated by
[`tests/fixtures/baseline.json`](tests/fixtures/baseline.json). It contains the goal,
baseline source text, contract invariants and named checks, policy, review labels,
patches, observed context fingerprints, and per-check observations. Unknown or
unperformed observations are JSON `null`, never an implied pass. Missing fields,
duplicate keys, unsupported versions, empty check lists, and non-boolean results
are rejected. Input field validation lives in `axiom_forge/workflow.py`.

SHA-256 fingerprints bind versioned baseline, contract, and policy snapshots using
canonical JSON (sorted keys, two-space indentation, ASCII escapes, final newline).
The original input bytes and UTF-8 patch bytes are also retained exactly. Changing
any context fingerprint requires rechecking; it never changes historical outcomes.

| Fixture | Evidence-aware result | Plain generate-and-test baseline |
| --- | --- | --- |
| Passing checks | accepted, pending human approval | accepted |
| Genuine regression | refused | refused |
| Faulty verifier / disagreement | unknown; propose a diagnostic | refused |
| Changed contract | unknown; require current checks | accepted |
| Insufficient evidence | unknown; collect missing observations | accepted |

The plain baseline uses only the supplied verifier observations. These are
synthetic comparisons, not measurements of real task completion or improvement.
The curated expected outcomes are separate from the classifier in
[`tests/fixtures/expected.json`](tests/fixtures/expected.json). The previous contract
is retained in `tests/fixtures/prior-contract.json`; a stale fingerprint cannot
establish acceptance under the current contract.

Acceptance requires matching context, checks marked reviewed by a label distinct
from the generator, and agreement between verifier and independent observations
on every check. `faulty_verifier` denotes a fixture diagnosis of disagreement; in
live use either checker could be wrong. Disagreement never selects its own winner.
The CLI cannot authenticate identity labels or prove that a review took place.
Generated tests remain proposals until independently reviewed. Even an `accepted`
fixture result keeps **human approval pending** and is not reusable knowledge.

## Local lineage and its limits

`.axiom-forge/objects/<sha256>` contains content-addressed input, report, context,
and patch artifacts. `events/00000001.json` and later records link artifacts and
the preceding event hash. Writes use exclusive creation and a single-writer lock;
existing objects and events are never overwritten by the CLI. Interrupted writes
or lock directories require investigation, not automatic deletion or history
repair. Preserve the original evidence before an authorized recovery.

Before appending or replaying, the store validates every retained event's required
fields, exact artifact bindings, object hashes, and input/report consistency with
engine `fixture-v1`. Invalid history is rejected without appending or repairing it.
Keep engine behavior versioned; a later engine must not silently reinterpret
historical outcomes. Reports and summaries
are derived artifacts; raw evidence stays authoritative.

This is application-level append-only storage with tamper detection, not a signed
ledger or filesystem access control. An external actor can rewrite a complete
store or remove its tail; there is no external trusted checkpoint. Backups,
retention, authenticated approvals, and stronger crash recovery remain explicit
unknowns. A recorded fingerprint of an older context does not prove its execution.

Human approval is required before applying a selected patch or promoting a recipe
with applicability conditions and replay checks. Deployment, source deletion,
permission expansion, and acceptance-rule changes require explicit authorization.
Imported conversations and all fixture content are untrusted data, never instructions.

See [`AGENTS.md`](AGENTS.md) for the shared agent contract. These initial tests and
acceptance criteria are proposals awaiting separate reviewer acceptance in the PR.

## Bounded ambiguity testing and project review

The separate `ambiguity-v1` engine checks **explicit structure and supplied
alternatives**, not arbitrary natural-language meaning. It accepts a project or
component requirements snapshot, flags missing acceptance checks/evidence,
unsupported assumptions, conflicting declared values for the same assumption key,
and multiple supplied interpretations. It never generates or executes candidate
code, changes checks, chooses an interpretation, or grants approval.

```sh
python3 -m axiom_forge ambiguity tests/fixtures/ambiguity/ambiguous.json
python3 -m axiom_forge project-evaluate tests/fixtures/ambiguity/ambiguous.json --store /tmp/axiom-review
python3 -m axiom_forge ambiguity tests/fixtures/ambiguity/ambiguous.json --record --store /tmp/axiom-review
python3 -m axiom_forge replay 1 --store /tmp/axiom-review
python3 -m axiom_forge report 1 --store /tmp/axiom-review
python3 -m axiom_forge project-evaluate tests/fixtures/ambiguity/ambiguous.json --store /tmp/axiom-review
```

Use a fresh store for the example event number. `ambiguity` previews structured
JSON without writing; only `--record` appends evidence. `report` renders ambiguity
events as ASCII-escaped JSON, as do preview, replay, and project evaluation.
Exit 0 means the operation completed, including when findings exist or evidence
is unknown; malformed input or invalid retained history exits 2.

The version-1 schema is validated in `axiom_forge/ambiguity.py`; a complete input
is in [`tests/fixtures/ambiguity/valid.json`](tests/fixtures/ambiguity/valid.json).
Unknown fields, duplicate IDs/keys/references, dangling references, unsupported
versions, and attempts to disable human approval are rejected.

| Field | Contract |
| --- | --- |
| `version`, `goal` | Integer `1` and a nonempty goal string. |
| `scope` | `kind`: `project` or `component`; `id`: explicit nonempty name. One scope per input. |
| `baseline`, `contract`, `policy` | Same snapshots as the foundation format: versioned baseline files, contract invariants and check names, and required human approval. Only the ambiguity format permits an empty check list so it can report the gap. |
| `requirements` | Nonempty list of unique `id`, nonempty `statement`, `checks` referencing contract names, `evidence_refs`, and `interpretations`. Empty links/interpretations produce findings. |
| `interpretations` | Per-requirement alternatives with unique `id`, nonempty `statement`, and `expectations` mapping supplied probe IDs to nonempty outcome labels. Omit a prediction when unknown. |
| `assumptions` | Unique `id`, `key`, `value` (nonempty strings), and `evidence_refs`. Different literal values for one literal key within the input scope produce a conflict. Different keys are not semantically compared. |
| `probes` | Unique `id` and nonempty `description`; proposed, inert checks, separate from the acceptance contract. |
| `evidence` | Unique `id` and nonempty `text`, embedded source or observation content. No URLs, paths, or instructions are followed. |
| `acceptance_evidence` | Map of known contract check names to evidence ID lists. Missing/empty entries produce findings. Presence is coverage only, never proof of a passing or reviewed check. |

Inputs are limited to 1 MiB, 64 requirements, 64 assumptions, 128 evidence entries,
128 acceptance checks, 32 probes, and 8 interpretations per requirement. Text is
not normalized. Synonyms, implicit contradictions, conditional scopes, omitted
requirements, and unlisted alternatives remain outside detection. List order is
retained; outcome labels are compared literally. An empty assumptions list cannot
establish that no assumptions exist.

For each interpretation pair, the tester proposes **one supplied probe** whose
declared outcomes differ. Ties use probe ID order. This is the smallest nonempty
check count for that pair, not a globally optimal test set or a measured cheapest
experiment. If no such probe is supplied, the proposal remains `unknown` and asks
for one distinguishing example. Missing checks/evidence and conflicting assumptions
produce bounded clarification requests; they do not invent acceptance rules.

Results include the exact input SHA-256, engine version, context fingerprints,
severity totals, uncertainty, proposed clarifications/checks, and evidence digests.
Each finding's `sources` are JSON pointers into the exact input artifact;
`evidence_refs` resolve through the result's `evidence` digest map. The store
preserves original input bytes and UTF-8 bytes of embedded evidence text. It does
not claim to preserve the bytes of external documents that a caller transcribed
into that text. Both `needs_clarification` and `no_structural_findings` retain
`semantic_status: unknown` and `human_approval: pending`.

The project evaluation loop is an explicit, read-only review cycle:

1. Consume the latest recorded ambiguity result for the **exact input bytes**.
2. Present findings, evidence links, and proposed clarification/checks for review.
3. Have a separate reviewer consider any revised requirements or proposed checks.
4. Explicitly record a new ambiguity run for the revised snapshot, then reevaluate.

`project-evaluate` never schedules or records a tester run. It validates all stored
history (including deterministic recomputation of historical reports for integrity)
and then reads the recorded reports. Without an exact match it returns `unknown`,
with `totals: null`; even whitespace changes require a new recorded run. Other
inputs for the same scope remain linked separately, without inheriting their
findings. Corrupt history is rejected rather than bypassed or repaired. Earlier
findings and failed attempts remain immutable across subsequent review cycles.

When recorded `fixture-v1` comparisons have matching baseline/contract/policy
fingerprints, the loop shows each event's accepted/refused/unknown totals alongside
its plain generate-and-test totals. It does not aggregate repeated runs into a
performance claim or treat a matching context as proof of project completion.
Missing measurements, semantic correctness, diagnostic usefulness, execution cost,
and independent approval remain unknown. This is a local review command, not a
background project automation or an automatically invoked ambiguity tester.

The four deterministic cases and manually curated expectations live in
[`tests/fixtures/ambiguity`](tests/fixtures/ambiguity/README.md). Tests cover both
engines in a shared store, stale inputs, forged approval/history, evidence bindings,
and terminal safety. The `fixture-v1` format and historical report bytes remain
unchanged. CI/package verification is a separate increment; this component adds no
workflow or package configuration changes. These checks establish implementation
behavior, not independent acceptance of the proposed ambiguity criteria.
