import json
from pathlib import Path

from crewai import BaseLLM

from research_team.schema import Claim, Conflict, ResearchBrief, SourcePack
from research_team.team import build_crew, grade_brief, run_team


PACK = SourcePack.model_validate_json(
    (Path(__file__).parent.parent / "fixtures" / "policy-conflict.json").read_text())


def supported_brief():
    return ResearchBrief(
        question=PACK.question,
        answer="The current target is 30 minutes; the archived edition said 60 minutes.",
        claims=[Claim(text="The current target is 30 minutes", source_id="ops-2026",
                      exact_quote="acknowledge a Sev 2 incident within 30 minutes")],
        conflicts=[Conflict(source_ids=["ops-2025", "ops-2026"],
                            explanation="The archived and current acknowledgement targets differ")],
        uncertainties=[],
    )


class StubLLM(BaseLLM):
    def __init__(self):
        super().__init__(model="synthetic-research-stub", temperature=0)
        self.calls = []

    def call(self, messages, tools=None, callbacks=None, available_functions=None, **kwargs):
        self.calls.append(messages)
        return supported_brief().model_dump_json()

    def supports_function_calling(self):
        return False


def test_actual_three_role_crew_kickoff_with_local_llm():
    llm = StubLLM()
    crew = build_crew(PACK, llm)
    assert [agent.role for agent in crew.agents] == [
        "Controlled-source researcher", "Evidence and disagreement checker", "Research brief writer"]
    report = run_team(PACK, llm)
    assert report["status"] == "supported"
    assert len(llm.calls) >= 3


def test_quote_and_source_gate():
    brief = supported_brief()
    brief.claims[0].exact_quote = "not in source"
    assert "quote is absent" in " ".join(grade_brief(PACK, brief)["issues"])
    brief.claims[0].source_id = "imaginary"
    assert "unknown source" in " ".join(grade_brief(PACK, brief)["issues"])


def test_disagreement_and_missing_evidence_gate():
    brief = supported_brief()
    brief.conflicts = []
    assert "unreported source conflict" in " ".join(grade_brief(PACK, brief)["issues"])
    brief.claims = []
    assert "no cited claims" in " ".join(grade_brief(PACK, brief)["issues"])
