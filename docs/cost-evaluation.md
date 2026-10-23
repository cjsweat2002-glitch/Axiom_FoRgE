# Proposed cost/quality experiment

Hypothesis: explicitly recorded cheap-first escalation can reduce wasted AI coding
attempts in one bounded Python workflow while preserving independently checked
results. This harness measures supplied records; it does not run models, candidates,
checks, or reviewers. Customer demand, willingness to pay, and live savings remain
unknown. No paid calls, outreach, execution adapter, deployment, or merge is included.

The implementation starts from main `8727a7a948189390f2cba90a16b99a9cd8012d4f`.
MON-9's ambiguity engine and MON-8's separate verification PR remain separate.
The contract is a fixed task roster, frozen baseline/contract/policy, a plain
generate-and-test comparator, and one or more evidence-guided or cheap-first
strategies. All supplied attempts, including failures and retries, contribute to
cost and latency. Each task contributes at most one independently accepted result,
through its explicitly selected final attempt. A passing candidate claim is never
independent acceptance. These rules and tests are proposals for separate review.

## Reproduce the simulated experiment

```sh
python3 -m axiom_forge cost-evaluate tests/fixtures/cost/matched.json
python3 -m axiom_forge cost-evaluate tests/fixtures/cost/matched.json --record --store /tmp/axiom-cost
python3 -m axiom_forge replay 1 --store /tmp/axiom-cost
python3 -m axiom_forge report 1 --store /tmp/axiom-cost
python3 -m unittest discover -s tests -v
```

Use a fresh store for event 1. Preview is read-only; `--record` preserves the exact
input bytes, embedded evidence and candidate bytes, context, and deterministic
report using the existing append-only store. Later corrections are new events,
never edits to prior evidence. Replay validates all engines in the store. Exit 0
means a report was produced, including unknown/incomparable reports; invalid input
or corrupt retained history exits 2. Strings are inert and ASCII-escaped on output.

The fixture's reproducible results are **SIMULATED**, not live-model savings:

| Strategy | Total USD | Accepted / refused / unknown tasks | False acceptances / accepted claims | Attempts / retries | Sum of seconds | USD per accepted result |
| --- | ---: | --- | --- | --- | ---: | ---: |
| Plain | 14 | 1 / 1 / 0 | 1 / 2 | 3 / 1 | 40 | 14 |
| Cheap-first | 8 | 2 / 0 / 0 | 0 / 2 | 3 / 1 | 20 | 4 |

Each failed attempt is included. The plain strategy's false acceptance is an
invented disagreement between a candidate claim and the separate review record.
No commercial conclusion follows from choosing these fixture values.

## Input contract (`cost-v1`, format version 1)

`tests/fixtures/cost/matched.json` is the complete, **SIMULATED** example. No fixture
reviewer, price, latency, success, or cost reduction is a live observation. Expected
arithmetic is curated separately in `expected.json`.

- `goal`, `baseline`, `contract`, `policy`: the existing frozen context format with
  nonempty acceptance checks and human approval still required.
- `data_kind`: `simulated` or `recorded`. The latter is the submitter's declaration,
  not a certification. Never relabel synthetic records as observed.
- `assumptions`: nonempty text explaining cost coverage, allocation, units, currency,
  measurement sources and recording limits. Include shared overhead exactly once
  through a documented allocation to attempts; no unrecorded overhead is inferred.
- `tasks`: unique `id` and exact `input` text. Freeze this roster before collecting
  results. Empty/missing runs remain visible; tasks cannot silently drop out.
- `evidence`: unique `id`, `source`, and embedded `text`. Preserve externally supplied
  observation/review/invoice content here. Sources are inert labels; URLs and paths
  are never opened. SHA-256 binds supplied bytes, not source authenticity.
- `strategies`: unique `id`, `kind`, `description`, and `runs`. Exactly one kind must
  be `plain`; alternatives are `cheap_first` or `evidence_guided`. Descriptions
  document the fixed selection/escalation rule. Routing is not executed or inferred.
- Each run: `task_id`, `context`, `attempts_complete` (boolean inventory declaration),
  ordered `attempts`, and `final_attempt` (ID or null). Context contains lowercase
  SHA-256 digests for `baseline`, `contract`, `policy`, and `task`; each hashes the
  canonical JSON of that snapshot (task includes both `id` and `input`). Missing
  tasks or mismatched context flag the entire comparison as incomparable. No records
  are discarded to improve a metric; strategy summaries still show all observations.
- Each attempt: unique within-run `id`, exact `input` (prompt/configuration record),
  `generator`, inert candidate `artifact` text (null when no candidate was produced),
  `claim` (`accepted`, `refused`, or
  `unknown`), `execution` (`succeeded`, `failed`, or `unknown`), `failure` (nonempty
  text for failed execution, otherwise null), `costs`, and `latency`.
- `costs` maps any of `model`, `compute`, `review`, `storage` to records with
  `amount` (nonnegative decimal string or null), `currency` (three uppercase letters),
  `quantity` (decimal string or null), `unit` (text), `evidence_ref` (ID or null),
  and `complete` (boolean). Amount is an explicitly supplied currency total, not a
  unit rate. Quantity/unit describe the source measurement; the harness never
  multiplies prices or converts currencies. Missing components are unknown. An
  explicit zero needs evidence and a completeness declaration, just like any cost.
  Partial amounts remain in observed subtotals but prevent a complete total.
- `latency`: `seconds` (nonnegative decimal string or null), `evidence_ref` (ID or
  null). Reported sums are sequential attempt durations, **not elapsed wall time**
  for parallel work. Missing durations keep totals unknown and known subtotals visible.
- `acceptance`: separate externally supplied records, at most one per attempt,
  with `strategy_id`, `task_id`, `attempt_id`, `reviewer`, `evidence_ref` (ID or null),
  `candidate_sha256` (UTF-8 artifact digest, or null for an absent candidate),
  `context`, `decision` (accepted/refused/
  unknown), and `checks` (every contract check mapped to true/false/null). Missing
  evidence, stale bindings, same generator/reviewer,
  unknown decisions/checks, or inconsistent decision/checks remain unknown.
  Accepted requires a candidate, successful execution and all checks true; refused
  requires at least one false check. A failed generation with no artifact retains
  its cost and may be externally refused, but cannot be accepted.
  A failed execution may be independently refused. Review labels cannot establish
  identity, truth, independence, or approval to apply a patch. No cryptographic
  authentication is claimed. Candidate claims are used only for disagreement counts.

Unknown fields, duplicate keys/IDs/reviews, dangling references, invalid numbers,
and unsupported versions fail closed. Decimal strings allow up to 18 integer and
12 fractional digits, no exponents/signs; input is capped at 1 MiB, 64 tasks,
8 strategies, 32 attempts per run, 2048 evidence entries, and 128 contract checks.

## Metric interpretation

Each strategy reports task accepted/refused/unknown totals over the full roster,
attempts, retries (attempts after the first in each run), failures, attempt-level
independent outcomes, and candidate-claim versus review counts. Acceptance rate
and false acceptance/refusal rates are exact numerator/denominator pairs; rates
are null if their population has missing independent evidence or a zero denominator.
False acceptance means an `accepted` claim independently `refused`; its denominator
is all accepted claims, including retries. Unknown claims are counted separately.
This measures recorded disagreements, not an independently established oracle error.

Cost subtotals retain every supplied amount grouped by currency and component.
Only fully evidenced amounts are counted as observed; amounts lacking provenance
remain unknown in the preserved input. Total cost and cost per independently
accepted final result require all four components for every attempt, complete
attempt inventories, full task coverage, and a single currency. The ratio
additionally requires matched context/currency across strategies, independent
outcomes for **every attempt and final result**
and at least one accepted final result. Zero acceptance, partial/missing cost,
unknown review, and incomparable task/context/currency records return null with
explicit reasons. No division by zero, currency mixing, or successful-attempt-only
cost is permitted. Exact decimal sums are used; division is rendered with 28
significant digits using half-even rounding and retains numerator/denominator.
Incomplete latency does not suppress an otherwise valid cost ratio.

## Future real records and proposed pilot gate

After separate approval of isolation, permissions and acceptance checks, a human
can collect records outside this harness for one frozen Python task roster. Supply
all prompts/configurations, candidates, failed attempts, retries, invoice/compute/
review/storage records and independently supplied check observations. Reviewers
must assess the frozen checks without adopting candidate-authored acceptance claims.
Document allocation and accounting periods, and reconcile the inventory against
the external run ledger. Supply missing values as null, not estimated free work.
Private evidence belongs in a local store, not this repository. Preserve originals;
transcribed text cannot establish the bytes or authenticity of an external source.

Proposed gate, to freeze with a separate reviewer before any real pilot: matched
roster/context and complete inventories; reproducible reports with all four cost
components and currency reconciled; no unknown acceptance outcomes; at least one
accepted result per strategy; no observed false acceptances; alternative acceptance
rate no lower than plain, cost per accepted result strictly lower, and latency and
retry counts reported against a pre-agreed budget. Include negative and inconclusive
results. Any numerical sample size, latency budget, economic threshold, and reviewer
independence checks must be agreed before collection. A small pilot would provide
bounded evidence only, not statistical superiority or revenue forecasts.

Still missing: real model/task records, verified external billing and review time,
authenticated independent judgments, measured diagnostic usefulness, customer
demand, and generalization beyond this workflow. Fixture arithmetic establishes
none of these. Human approval to apply/promote/deploy remains pending.

## Implementation verification

Local checks for this increment:

- `python3 -m unittest discover -s tests -v`: 55 passed on Python 3.15.1.
- Python 3.11.17, `python -m build --no-isolation`: sdist and wheel-from-sdist
  built using build 1.3.0, setuptools 80.9.0 and wheel 0.45.1.
- Fresh wheel installation, `python -m pip check`: passed. The sdist contains the
  cost documentation/fixtures; the wheel contains the new module.
- Outside the checkout, installed `axiom-forge --version`, `--help`, cost preview,
  cost recording, `replay 1`, and `report 1` succeeded; malformed cost input returned
  exit 2. Preview/replay/report agreed on the simulated results.
- Outside the checkout, `python -m unittest discover -s tests -v` against the
  installed Python 3.11.17 package: 55 passed, including original engines and
  cost arithmetic, failure, uncertainty, provenance, corruption and CLI checks.
- `git diff --check`: passed.

These are implementation checks, not independent acceptance approval or a real
commercial pilot. Existing CI configuration remains the separate MON-8 increment.
