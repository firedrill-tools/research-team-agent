# Research team agent

A three-role [CrewAI](https://docs.crewai.com/en/concepts/crews) team researches a controlled local source pack. The researcher extracts claims, the checker challenges evidence and notes conflicting versions, and the writer prepares a JSON brief. An independent gate checks source IDs, exact quote anchors and conflicts tagged in the pack before marking a brief supported.

## Run

Requires Python 3.12+ and `uv`:

```sh
uv sync --locked --extra test
OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true uv run --locked pytest -q
```

Set `RESEARCH_MODEL` to an explicit `openai/MODEL`, `anthropic/MODEL` or `gemini/MODEL` and the corresponding provider key, then run:

```sh
OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true uv run --locked python -m research_team fixtures/policy-conflict.json --output brief.report.json
```

The example pack has an archived 60-minute and current 30-minute incident acknowledgement target. A supported brief must call out that conflict. Every claim includes a source ID and an exact quote from the source text. Bad citations, missing conflicts, or no claims produce `needs_review` with issues in the saved report. The output file and source pack are local; the example does not browse or modify external systems.

The gate does not establish semantic entailment of a claim from its quote; the checker and a human reviewer still need to assess that. Local tests invoke the actual sequential CrewAI tasks with a stub LLM and test the independent gate. They do not prove a live model run. A real run requires provider credentials, model availability and measured output. Firedrill integration awaits qualification of its new released interface. Dependencies are locked in `uv.lock`.

Explore related applications in the [Firedrill example catalog](https://github.com/firedrill-tools/firedrill-example-catalog). Product and setup references: [Firedrill](https://firedrill.run/) and the [official developer documentation](https://docs.firedrill.run/). Use documentation matching the qualified release; this repository records its current integration limits above.


## Initial contract checkpoint

16 local checks now cover the original three-role stub kickoff and strict bounded source/brief contracts, actual calendar dates, source uniqueness/tagged value anchors, nonblank text, duplicate/nonfinite role JSON and independent citation/conflict/handoff gates. Extra cross-topic/duplicate conflicts cannot be supported. A checked handoff must classify every candidate exactly once; writer claims must come from supported candidates, disagreements must match the checker and checker gaps remain explicit. These are structural checks; semantic entailment is still not established.

At the original contract checkpoint native completion work was still active. An actual three-role native OpenAI/CrewAI loopback probe at the original baseline accepted three finish_reason length responses and published a supported brief. The native checkpoint below now blocks that defect. Data and distribution qualification is documented below. Live provider/billing/Firedrill/publication gates stay parked; no paid model has been used.


## Native role checkpoint

56 checks pass locally. Three actual pinned CrewAI provider paths (OpenAI2.54.0, Anthropic1.14.0 and Google GenAI2.31.0) run independently or as a mixed three-role team. Use `RESEARCHER_MODEL`, `CHECKER_MODEL` and `WRITER_MODEL` (or `--researcher-model`, `--checker-model`, `--writer-model`) to choose `provider/MODEL` per role. `RESEARCH_MODEL` is the explicit common fallback. No model is substituted. Credentials come from `RESEARCHER_API_KEY`/`CHECKER_API_KEY`/`WRITER_API_KEY`, then the selected provider's `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`/`GEMINI_API_KEY`. Keys are never placed in role metadata, request evidence or CLI arguments. Invalid control-character credentials fail before client creation.

Each role can use `--ROLE-base-url` or `ROLE_BASE_URL`: HTTPS or loopback HTTP without URL credentials/query/fragment. Gemini is the explicit Developer API backend; ambient Vertex/enterprise selection is refused. Explicit credential/auth headers prevent token/profile borrowing, and clients disable environment proxies and redirects. The pinned Anthropic SDK no longer accepts temperature; its native integration receives `temperature=None` so that unsupported parameter is omitted. Google GenAI requires tenacity<9.2 and websockets<17; the lockfile changes only those required constraints plus its new dependencies.

The actual CrewAI sequence preserves three distinct agents/tasks and controlled source context. Researcher notes, complete checker classifications/conflicts/gaps and writer output have independent strict contracts. A checker cannot support a missing quote and continue to the writer. The writer cannot add claims beyond checked candidates, invent conflicts or drop checker gaps. Final `supported` is a structural source/handoff result; semantic entailment is explicitly not established by this gate.

Native async `Crew.akickoff` still runs its model router in a worker thread in CrewAI1.15.28. A tracked bridge forwards that sync seam to the inherited native async provider method on the owned event loop. Narrow constructor/accessor subclasses prevent eager unowned clients without replacing native request formatting, parsing or the CrewAI role loop. A private per-run actual CrewAI task SQLite store avoids shared latest-kickoff records. On failure, an internal BaseException carrier crosses the framework's retry/repair loops and is translated back to the original public error after cleanup. Both native tasks and bridge calls drain before final evidence. No vendor caches, global provider clients or private retry variables are modified.

Exactly one prepared HTTP request per role is permitted, with zero SDK retries and2048 requested output tokens per role. The operation defaults120 seconds (configurable up to300), with requested30-second HTTP phases. Original HTTP JSON/decoded bytes/hash, unknown fields, model/IDs/finish, errors and observed/unknown/invalid counters precede SDK interpretation. OpenAI needs one stop text completion, Anthropic one end_turn text message, Gemini one unblocked STOP text candidate; truncated/refused/pending/tool/inconsistent results cannot release a role. Original provider counters stay separate from CrewAI-normalized usage; cost is unknown. Actual request permits also block format repair/additional requests. A controlled429 test verifies CrewAI's rate wrapper cannot sleep or dispatch again.

Each run writes a0700 directory/0600 atomic flushed trace before credentials/native work and a final record after cleanup. Partial role/provider/source evidence survives failure. Recording faults prevent later calls/release; persistent final recording faults expose failed in-memory evidence with unknown durable status. The CLI prints one JSON result/error, with detailed native diagnostics retained privately. Success returns0, needs_review2, failure1; SIGINT/SIGTERM/SIGHUP returns130/143/129 after failed evidence and owned cleanup. `--output` publishes an exclusive private report without replacing existing files. `--output-root` and `--timeout-seconds` configure attempts. Original source bytes/identity/hash remain bound to model input and are checked before role callbacks/release; changed source cannot publish supported output.

Tests include actual normal CLI over local HTTP for a mixed team, original length rejection, explicit auth/proxy policy and all three signals. These are controlled synthetic calls, never paid providers. The1MiB caps bound retained decoded response/request evidence, not upstream wire/peak heap. Synchronous CrewAI/file/SQLite/flush work and cleanup are outside a hard whole-run wall promise; the bridge does not establish hostile-code/process containment. CrewAI tracing is explicitly off; run the CLI/tests with the documented telemetry environment flags before library initialization. Caller-injected BaseLLM remains a separately labeled caller-owned stub path.

Versioned cases and fresh distribution qualification are documented below. Live model availability, paid semantic/billing review, qualified new Firedrill and publication/license stay parked. See [COMPATIBILITY.md](COMPATIBILITY.md) and [PLAN.md](PLAN.md).


## Versioned controlled source packs

89 checks pass locally. `controlled-research-cases`1.0.0 has twelve source-hash-bound cases/four profiles. All documents/editions are fictional source facts, with no invented prior model/usage/authentication/paid provider observations. Task and dataset identity remain separate from model source context.

| Profile | Cases |
| --- | --- |
| Starter | incident-target, consistent-guidance, corroborating-sources |
| Busy | busy-handbooks:36 coherent editions across12 topics, with two topics requested |
| Ambiguous | missing-topic, equal-date-conflict, unapproved-draft, retired-only |
| Boundary | hostile-import, three-way-disagreement, unicode-anchors, maximum-source-count (64 sources) |

A pack may specify `focus_topics` (up to8 unique IDs). Claims and conflict pairs must stay within that explicit scope; unrelated documents remain supplied context. A requested topic without sources produces needs_review. When omitted, all supplied topics remain in scope for backward compatibility. This does not infer topical relevance or semantic entailment from the natural-language question. Date, draft, archived and Unicode source qualifications remain original text for the model and human to interpret.

List, initialize and inspect without provider keys or model calls:

```sh
OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true uv run --locked research-team datasets
OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true uv run --locked research-team init --case busy-handbooks --directory /tmp/research-busy
OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true uv run --locked research-team workspace /tmp/research-busy
```

Initialization validates a source-pinned index and case hashes, creates an exclusive0700 directory with0600 `pack.json`, `workspace.json` and `TASK.md`, and preserves existing paths/files/symlinks. Readback validates current source and reports its exact hash and whether it matches the original seed. Valid human edits are preserved and clearly differ from the seed; malformed/missing source and changed seed identity are refused without repair. Native execution binds the actual selected source snapshot, never an assumed unchanged seed.

Reset materializes the original case into a fresh private destination after checking the current workspace instance, preserving old source/work/evidence:

```sh
OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true uv run --locked research-team reset /tmp/research-busy --to /tmp/research-busy-fresh --instance CURRENT_INSTANCE_UUID
```

To investigate an initialized pack with configured roles/keys, use `research-team /tmp/research-busy/pack.json --output-root /tmp/research-runs`. Model work remains explicit and separate from setup. Every one of the twelve packs is qualified through the actual native three-role sequence with controlled HTTP responses. Busy retains its unrelated history while the structural gate limits answer authority to its two requested topics. Hostile text placement and controlled responses do not prove live model obedience or semantic quality.

All crew builds, including the caller-injected stub path, now use private task storage. This avoids constructing or resetting CrewAI's shared latest-kickoff database; independent private crews cannot erase each other's records. Native task storage stays in the private run; a direct caller's crew keeps a private temporary directory for its own lifetime.

## Distribution qualification

```sh
uv run --locked python scripts/build_datasets.py --check
uv build
OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true uv run --locked python scripts/check_distribution.py
```

The wheel includes all thirteen JSON files; the sdist includes source/data/original fixture/tests/helpers/scripts/docs/CI/lockfiles. A separate deterministic complete source archive contains an exact per-file SHA256/size/mode manifest and is generated without Git or installed caches. Fresh locked wheel/sdist/complete-source environments outside checkout qualify console/module CLI, all twelve private cases/reset, real installed three-role SDK/CLI over owned HTTP, exclusive report publication and missing-key failure receipts. The entire89-check suite runs from the complete archived source and preserves every original archived file hash. Repeated archive bytes agree. CI uploads distributions plus qualification.json; no public release/license choice is implied.

Independent application implementation is complete; exact final Linux/data/distribution evidence is recorded in the catalog. Live provider/semantic/billing review, qualified new Firedrill and publication/license remain parked. [PLAN.md](PLAN.md) retains the portfolio handoff.

## Current Firedrill integration

Released CLI/SDK 2.2.2, current command invocation, remote operator MCP and recovery are documented in [firedrill/README.md](firedrill/README.md). Offline checks preserve actual private source/native-key behavior and explicit model/budget selection. Authenticated persisted runs and live quality/cost remain separate parked gates.
