"""Source and deliverable contracts for bounded research."""

from pydantic import BaseModel, ConfigDict, Field


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    fact_value: str = Field(min_length=1)
    text: str = Field(min_length=1)


class SourcePack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    exact_quote: str = Field(min_length=1)


class Conflict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ids: list[str] = Field(min_length=2)
    explanation: str = Field(min_length=1)


class ResearchBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    claims: list[Claim]
    conflicts: list[Conflict]
    uncertainties: list[str]
