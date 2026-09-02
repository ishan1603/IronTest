# Agents

Four agents run in sequence. Each consumes the previous one's output; none of
them holds a database session — the orchestrator injects any history they need.

## Story Agent

`agents/story_agent.py`

Turns free-form requirement text into structure: intent, affected modules,
acceptance criteria, risk factors, security vectors, microservices.

Output is validated before it is accepted. Intent must be a real sentence, the
lists must be non-empty, and the intent must share vocabulary with the
submitted text — a small model that drifts into a generic answer is rejected
and re-asked rather than silently passed downstream.

## Test Agent

Two implementations, chosen by whether a repository is attached.

### `agents/repo_test_agent.py` — repository runs

Receives the stack profile, the ranked source files, the public symbols and
signatures extracted from them, and the importable module paths derived from
those file paths. It is instructed never to invent a path that contradicts the
context.

Mode changes the instruction, not the machinery:

- **existing_code** — the behavior ships. Write tests that verify it; a failure
  is a genuine defect.
- **specification** — the behavior does not exist. Write the tests that *should*
  pass once it is built, importing the paths where the code should live. They
  will fail now, and that red phase is the deliverable.

### `agents/test_agent.py` — standalone runs

No repository, so snippets must be self-contained. Validation is
correspondingly strict: no imports, no network, must define a collectable
`test_*` function, and **must be able to fail**.

That last check ([`_is_tautological`](../backend/agents/test_agent.py)) rejects
the degenerate shape where a snippet defines a dict literal and then asserts
keys back out of it. Such a test passes unconditionally and exercises nothing.
A rejected snippet is reported as skipped with the reason — never swapped for a
substitute.

## Execution Agent

`agents/execution_agent.py` for standalone runs; `runners/` for repository runs.

Runs the suite and reports what happened. No sampling, no target pass band, no
synthesized output. A fully passing suite reports as fully passing.

Repository suites are assembled by `agents/suite_builder.py`, which names each
function `test_TC_001_...` so the runner's JUnit report maps every outcome back
to the case that produced it.

## Risk Agent

`agents/defect_agent.py`

Combines this run against the user's own history for the same story to produce
per-module risk, a confidence score, and a GO / CONDITIONAL GO / NO-GO verdict.

The model proposes a score; deterministic logic then reconciles it against the
measured pass rate, module risk, and execution penalties, and the stricter of
the model's and the derived recommendation wins. A model cannot talk its way to
GO past a suite that failed.

A module with no history reports `has_history: false` and omits a defect
probability entirely, rather than defaulting to a number that would look like a
measurement.

## Learning across runs

Runs of the same requirement are grouped by a hash of its text. On later runs
the test agent receives:

- fingerprints of cases already generated, so it can tell new coverage from
  repeated coverage;
- failure signatures from the previous run;
- signatures that have recurred across runs.

Recurring real failures produce targeted regression guards. These are marked
`learning_source: adaptive` and carry the signature they descend from.

Guards derived from history are **not** given a generated snippet — a template
cannot meaningfully reproduce a past failure — so they surface as manual
follow-ups rather than as tests that would pass without checking anything.
