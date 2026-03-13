from __future__ import annotations

from pydantic import BaseModel, Field


class KeyPoint(BaseModel):
    point: str
    evidence: str
    confidence: float = Field(ge=0.0, le=1.0)


class Takeaway(BaseModel):
    takeaway: str
    why: str
    action: str


class EntityBlock(BaseModel):
    companies: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    papers: list[dict[str, str]] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    claim: str
    type: str
    needs_verification: bool


class L0SummaryOutput(BaseModel):
    language: str
    tldr: str
    key_points: list[KeyPoint]
    ai_pm_takeaways: list[Takeaway]
    tags: list[str]
    entities: EntityBlock
    claims: list[Claim]
    risk_flags: list[str]
    reading_time_min: int = Field(ge=0)
    summary_confidence: float = Field(ge=0.0, le=1.0)


class Relevance(BaseModel):
    agents: float = Field(ge=0.0, le=1.0)
    eval: float = Field(ge=0.0, le=1.0)
    product: float = Field(ge=0.0, le=1.0)
    engineering: float = Field(ge=0.0, le=1.0)
    biz: float = Field(ge=0.0, le=1.0)


class L1ScoreOutput(BaseModel):
    relevance: Relevance
    novelty: float = Field(ge=0.0, le=1.0)
    actionability: float = Field(ge=0.0, le=1.0)
    credibility: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    grade: str
    rationale: str
    push_recommended: bool


class Evidence(BaseModel):
    url: str
    snippet: str
    type: str


class VerifiedClaim(BaseModel):
    claim: str
    evidence: list[Evidence]


class UnverifiedClaim(BaseModel):
    claim: str
    reason: str


class RecommendedAction(BaseModel):
    action: str
    owner: str
    effort: str


class L2VerifyOutput(BaseModel):
    verdict: str
    confidence: float = Field(ge=0.0, le=1.0)
    verified_claims: list[VerifiedClaim]
    unverified_claims: list[UnverifiedClaim]
    evidence: list[Evidence]
    notes: str
    recommended_actions: list[RecommendedAction]


class ChatOutput(BaseModel):
    answer: str
    sources: list[dict[str, str | int]]
    followups: list[str]
