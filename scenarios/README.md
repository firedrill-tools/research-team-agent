# Scenario set

The `policy-conflict.json` pack has an archived 60-minute Sev 2 acknowledgement target and a current 30-minute target. A supported brief quotes the current source, identifies the archived/current disagreement, and notes any uncertainty beyond the supplied records.

Boundary cases: a quote absent from its cited source; a nonexistent source ID; a missing disagreement between differing source values; a brief with no claims. The independent gate marks these `needs_review`. It verifies source IDs, exact quote substrings and explicitly tagged conflicts, but it cannot prove that a prose claim is semantically entailed by a quote. The checker agent and human review cover that remaining judgment.

Tests exercise a real three-task CrewAI kickoff with a local `BaseLLM` stub, then exercise each evidence gate. They do not claim a live provider result.
