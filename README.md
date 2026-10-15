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
