"""Strict bounded source and three-role deliverable contracts."""

from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Note = Annotated[str, Field(min_length=1, max_length=1000)]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, revalidate_instances="always", allow_inf_nan=False
    )

    @field_validator("*")
    @classmethod
    def nonblank(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("text must be nonblank")
        if isinstance(value, list) and any(
            isinstance(x, str) and not x.strip() for x in value
        ):
            raise ValueError("text entries must be nonblank")
        return value


class Source(Contract):
    source_id: ID
    title: str = Field(min_length=1, max_length=300)
    as_of: str = Field(min_length=10, max_length=10)
    topic: ID
    fact_value: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def source_facts(self):
        if date.fromisoformat(self.as_of).isoformat() != self.as_of:
            raise ValueError("as_of requires an ISO calendar date")
        if self.fact_value not in self.text:
            raise ValueError("tagged fact_value requires an exact source-text anchor")
        return self


class SourcePack(Contract):
    question: str = Field(min_length=1, max_length=2000)
    sources: list[Source] = Field(min_length=1, max_length=64)
    focus_topics: list[ID] | None = Field(default=None, min_length=1, max_length=8)

    @model_validator(mode="after")
    def coherent(self):
        if self.focus_topics is not None and len(set(self.focus_topics)) != len(
            self.focus_topics
        ):
            raise ValueError("requested focus topics must be unique")
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("source IDs must be unique")
        if len(self.model_dump_json().encode()) > 1048576:
            raise ValueError("source pack exceeds 1MiB serialized UTF8")
        return self


class Claim(Contract):
    text: str = Field(min_length=1, max_length=1000)
    source_id: ID
    exact_quote: str = Field(min_length=1, max_length=2000)


class Conflict(Contract):
    source_ids: list[ID] = Field(min_length=2, max_length=2)
    explanation: str = Field(min_length=1, max_length=1000)

    @field_validator("source_ids")
    @classmethod
    def distinct(cls, value):
        if len(set(value)) != 2:
            raise ValueError("conflict requires two distinct sources")
        return value


class ResearchBrief(Contract):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)
    claims: list[Claim] = Field(max_length=64)
    conflicts: list[Conflict] = Field(max_length=128)
    uncertainties: list[Note] = Field(max_length=32)


class ResearchNotes(Contract):
    claims: list[Claim] = Field(max_length=64)
    gaps: list[Note] = Field(max_length=32)


class ClaimReview(Contract):
    claim_index: int = Field(ge=0, le=63)
    disposition: Literal["supported", "unsupported"]
    reason: Note


class CheckReport(Contract):
    reviews: list[ClaimReview] = Field(max_length=64)
    conflicts: list[Conflict] = Field(max_length=128)
    gaps: list[Note] = Field(max_length=32)
