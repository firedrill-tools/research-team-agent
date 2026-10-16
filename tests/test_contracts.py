from copy import deepcopy
import pytest
from pydantic import ValidationError
from research_team.schema import SourcePack, ResearchBrief, ResearchNotes, CheckReport
from research_team.team import grade_brief, grade_handoff
from test_research import PACK, supported_brief


@pytest.mark.parametrize(
    "change",
    [
        {"question": " "},
        {"sources": []},
        {"sources": [PACK.sources[0].model_copy(update={"as_of": "2026-02-30"})]},
        {
            "sources": [
                PACK.sources[0].model_copy(
                    update={"fact_value": "invented tagged value"}
                )
            ]
        },
        {"sources": [PACK.sources[0], PACK.sources[0]]},
        {"sources": [PACK.sources[0].model_copy(update={"source_id": " padded"})]},
        {"sources": [PACK.sources[0].model_copy(update={"text": " "})]},
    ],
)
def test_invalid_source_contract_or_model_copy_is_refused(change):
    with pytest.raises(ValidationError):
        SourcePack.model_validate(PACK.model_copy(update=change))


def test_blank_answer_claim_anchor_and_invented_conflict_baseline_is_blocked():
    brief = supported_brief()
    brief.answer = " "
    brief.claims[0].exact_quote = " "
    with pytest.raises(ValidationError):
        grade_brief(PACK, brief)
    brief = supported_brief()
    from research_team.schema import Conflict

    brief.conflicts.append(
        Conflict(
            source_ids=["ops-2026", "pager-2026"],
            explanation="Invented cross-topic disagreement",
        )
    )
    result = grade_brief(PACK, brief)
    assert result["status"] == "needs_review" and any(
        "same-topic" in issue for issue in result["issues"]
    )


def test_handoff_requires_each_candidate_exactly_once_and_no_writer_invention():
    brief = supported_brief()
    notes = ResearchNotes(claims=brief.claims, gaps=[])
    checked = CheckReport(
        reviews=[
            {"claim_index": 0, "disposition": "supported", "reason": "Quote observed"}
        ],
        conflicts=brief.conflicts,
        gaps=[],
    )
    assert grade_handoff(PACK, notes, checked, brief)["status"] == "supported"
    checked.reviews = []
    report = grade_handoff(PACK, notes, checked, brief)
    assert report["status"] == "needs_review" and any(
        "every candidate" in issue for issue in report["issues"]
    )
    checked = CheckReport(
        reviews=[
            {
                "claim_index": 0,
                "disposition": "unsupported",
                "reason": "Claim is not entailed",
            }
        ],
        conflicts=brief.conflicts,
        gaps=[],
    )
    assert any(
        "not supported" in issue
        for issue in grade_handoff(PACK, notes, checked, brief)["issues"]
    )


def test_writer_cannot_drop_checker_conflicts_or_uncertainty():
    brief = supported_brief()
    notes = ResearchNotes(claims=brief.claims, gaps=[])
    checked = CheckReport(
        reviews=[
            {"claim_index": 0, "disposition": "supported", "reason": "Quote observed"}
        ],
        conflicts=brief.conflicts,
        gaps=["Semantic judgment remains uncertain"],
    )
    result = grade_handoff(PACK, notes, checked, brief)
    assert any("uncertainty" in issue for issue in result["issues"])
    brief.conflicts = []
    assert any(
        "differ from checker" in issue
        for issue in grade_handoff(PACK, notes, checked, brief)["issues"]
    )


@pytest.mark.parametrize(
    "raw", ['{"claims":[],"claims":[]}', '{"unknown":NaN}', '{"unknown":Infinity}']
)
def test_role_json_rejects_duplicate_and_nonfinite_measurements(raw):
    from research_team.team import _raw_json

    with pytest.raises(ValueError):
        _raw_json(raw)
