# Firedrill agent-first integration

The optional toolchain pins released `@firedrill-run/cli` and `@firedrill-run/sdk` **2.2.2** (October 19, 2026), Node 22+. The app retains its locked native provider/framework dependencies.

## Set up Firedrill

From the repository root, install this application's locked dependencies and the optional simulation clients:

```sh
uv sync --locked --extra test
npm ci --prefix firedrill --ignore-scripts --no-audit --no-fund
```

Sign in and choose the Firedrill project and environment once:

```sh
npx firedrill-run init
```

Complete browser authorization when prompted. Initialization writes `firedrill.config.json` in this repository; it does not run the AI agent. Installation choices are optional: skip duplicate SDK/client installation if you are using the locked `firedrill/` toolchain above. Keep this application's runtime requirements from the root README; the clients' Node.js minimum does not replace them.

Automation uses protected `FIREDRILL_TOKEN`, `FIREDRILL_PROJECT_ID`, `FIREDRILL_ENVIRONMENT_ID`. Model operations independently need provider-specific keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) and explicit reviewed provider/model identifiers. Do not put credentials in recipes.

After scope and provider budget are authorized:

```sh
node firedrill/simulate.mjs --preview
node firedrill/simulate.mjs
```

The bounded sequential recipe initializes an actual hash-bound private source pack and invokes the normal researcher/checker/writer CrewAI CLI and native providers. Each role has an explicit input.models provider/model identifier; optional configuration.parameters.model applies one reviewed provider/model to all three. Native role keys remain independent and must match the selected provider. No model/client/factory is injected. Existing source-hash/citation/freshness/contradiction/support checks decide whether a report is supported or needs_review; CLI exit2 for unsupported/review remains nonzero. A sequential team completion does not establish source accuracy or human approval. Busy inspection reads the actual 36-source pack without inference. No open-web connector is added.

Each attempt saves outer run/attempt/scenario IDs in private `.runs/firedrill/attempt-*/invocation.json` before a distinct absent workspace leaf. Initialized paths are checked inside that workspace, and actual source files, partial reports, original native receipts and unknown outcomes remain inspectable. New attempts never reset earlier evidence/journals. Only reviewed explicit input/model configuration is accepted; current ID-only invocation rejects controller assessment data and unsupported Tool bindings, and operator/CI authority is removed from child environments. Local files are not uploaded platform artifacts. Existing cancellation/close/bounds remain authoritative; local termination does not establish remote billing completion, rollback or live quality. Provider credentials/accounts, model enablement and authorized budgets remain separate from platform execution scope.

## Offline verification

These checks are optional when getting started; they do not authorize an account or run a paid model:

```sh
node firedrill/node_modules/@firedrill-run/cli/bin/firedrill.mjs validate firedrill/scenario.json --json --non-interactive
npm test --prefix firedrill
```

The saved recipe is an observation/exploration example, not a claim of agent correctness. It has no Firedrill rubric or CI gate. Execution success and any application-owned checks are distinct from a scored assessment. Local evidence paths are not uploaded captures; the evidence and proof limits described in this guide remain in effect.

## MCP and recovery

Configure remote OAuth operator MCP at **https://mcp.firedrill.run/mcp** using [host setup](https://docs.firedrill.run/guides/coding-agents). MCP prepares, queues and inspects; the local SDK/CLI executes the command target. Host OAuth and execution login are separate. Use `--run BATCH_ID` to attach queued work, `--resume OPERATION_ID` after uncertainty, and `--result BATCH_ID` to read retained results. Preserve SDK journals and local evidence. These scripts retain public SDK diagnostics and whole-batch exit status; a new simulation starts new work.

CI and the fresh locked source archive run offline integration tests with actual private business state and the native missing-key boundary. They establish wiring and cleanup, not live model quality, platform persistence, or uploaded captures. The observation recipe defines no grader/gate. Authenticated persisted happy/negative runs, paid model quality/cost, and licensing remain separate gates.

References: [SDK](https://docs.firedrill.run/sdk/typescript), [command targets](https://docs.firedrill.run/guides/callbacks), [operator MCP](https://docs.firedrill.run/guides/control-mcp), [CI](https://docs.firedrill.run/guides/ci).
