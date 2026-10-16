# Research team agent

A three-role [CrewAI](https://docs.crewai.com/en/concepts/crews) team researches a controlled local source pack. The researcher extracts claims, the checker challenges evidence and notes conflicting versions, and the writer prepares a JSON brief. An independent gate checks source IDs, exact quote anchors and conflicts tagged in the pack before marking a brief supported.

## Run

Requires Python 3.12+ and `uv`:

```sh
uv sync --extra test
uv run pytest -q
```

Set `RESEARCH_MODEL` to a CrewAI-supported provider/model value and the corresponding provider key, then run:

```sh
uv run python -m research_team fixtures/policy-conflict.json --output brief.report.json
```

The example pack has an archived 60-minute and current 30-minute incident acknowledgement target. A supported brief must call out that conflict. Every claim includes a source ID and an exact quote from the source text. Bad citations, missing conflicts, or no claims produce `needs_review` with issues in the saved report. The output file and source pack are local; the example does not browse or modify external systems.

The gate does not establish semantic entailment of a claim from its quote; the checker and a human reviewer still need to assess that. Local tests invoke the actual sequential CrewAI tasks with a stub LLM and test the independent gate. They do not prove a live model run. A real run requires provider credentials, model availability and measured output. Firedrill integration awaits qualification of its new released interface. Dependencies are locked in `uv.lock`.

Explore related applications in the [Firedrill example catalog](https://github.com/firedrill-tools/firedrill-example-catalog). Product and setup references: [Firedrill](https://firedrill.run/) and the [official developer documentation](https://docs.firedrill.run/). Use documentation matching the qualified release; this repository records its current integration limits above.


## Development checkpoint

16 local checks now cover the original three-role stub kickoff and strict bounded source/brief contracts, actual calendar dates, source uniqueness/tagged value anchors, nonblank text, duplicate/nonfinite role JSON and independent citation/conflict/handoff gates. Extra cross-topic/duplicate conflicts cannot be supported. A checked handoff must classify every candidate exactly once; writer claims must come from supported candidates, disagreements must match the checker and checker gaps remain explicit. These are structural checks; semantic entailment is still not established.

Native completion work is active. An actual three-role native OpenAI/CrewAI loopback probe at the original baseline accepted three finish_reason length responses and published a supported brief. That defect is not yet fixed by this contract checkpoint. Native async ownership/terminal and original measurement/partial failure receipts, explicit per-role mixed providers, normal CLI interruption, coherent datasets/private workspaces and fresh locked distributions remain in [PLAN.md](PLAN.md). Live provider/billing/Firedrill/publication gates stay parked; no paid model has been used.
