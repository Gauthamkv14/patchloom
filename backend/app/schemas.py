"""Pydantic schemas and data models for PatchLoom."""

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class HealthResponse(BaseModel):
    """Health status response."""

    status: str = "ok"
    demo_mode: bool
    environment: str
    has_gemini_key: bool
    has_github_token: bool


class ContributorProfile(BaseModel):
    """Contributor profile input."""

    skills: list[str] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Skills tags (e.g. python, react, sql)",
    )
    preferred_languages: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Preferred programming languages",
    )
    experience_level: Literal["beginner", "intermediate", "advanced"] = Field(
        default="beginner",
        description="Self-assessed open-source experience level",
    )
    available_hours: float = Field(
        ...,
        gt=0,
        le=100,
        description="Available hours for the contribution",
    )
    learning_goal: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Optional learning goal",
    )

    @field_validator("skills", "preferred_languages")
    @classmethod
    def clean_tags(cls, tags: list[str]) -> list[str]:
        cleaned = [t.strip().lower() for t in tags if t.strip()]
        return cleaned[:20]


class AnalyzeRequest(BaseModel):
    """Repository analysis request."""

    repo_url: str = Field(..., description="Canonical GitHub repo URL (https://github.com/OWNER/REPO)")
    profile: ContributorProfile
    provider: Optional[str] = Field(default=None, description="Optional explicit provider ('gemini' or 'ollama')")
    demo: Optional[bool] = Field(default=False, description="Request fixture demo mode")


EvidenceStatus = Literal["verified", "unknown", "inference"]


class SignalEvidence(BaseModel):
    """Signal evidence with provenance tracking."""

    status: EvidenceStatus
    source: str
    observed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    value: Any = None


class RepoMetadata(BaseModel):
    """Grounding repository metadata."""

    owner: str
    name: str
    description: Optional[str] = None
    default_branch: str = "main"
    languages: list[str] = Field(default_factory=list)
    open_issues_count: int = 0
    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    has_readme: bool = False
    has_contributing: bool = False
    has_ci: bool = False
    tree_truncated: bool = False


class CandidateIssue(BaseModel):
    """Candidate issue with viability signals and AI fit assessments."""

    number: int
    title: str
    url: str
    labels: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    comments_count: int = 0
    viability_score: int = Field(..., ge=0, le=100)
    viability_band: Literal["high", "medium", "low"]
    signals: dict[str, SignalEvidence] = Field(default_factory=dict)
    negative_factors: list[str] = Field(default_factory=list)
    unknown_factors: list[str] = Field(default_factory=list)

    # Gemma fit fields (None when AI not run or unavailable)
    fit_score: Optional[int] = Field(default=None, ge=0, le=100)
    final_score: Optional[float] = Field(default=None, ge=0, le=100)
    matching_skills: list[str] = Field(default_factory=list)
    skill_gaps: list[str] = Field(default_factory=list)
    estimated_hours: Optional[float] = None
    likely_files: list[str] = Field(default_factory=list)
    reason: Optional[str] = None
    risks: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)

    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    truncated: bool = False


class AnalyzeResponse(BaseModel):
    """Complete response for POST /api/analyze."""

    repo: RepoMetadata
    provider: str
    actual_model: str
    ai_status: Literal["complete", "partial", "unavailable_or_invalid"]
    issues: list[CandidateIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Safe structured error response."""

    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None


class PlanRequest(BaseModel):
    """Request schema for POST /api/plan."""

    repo_url: str = Field(..., description="Canonical GitHub repo URL (https://github.com/OWNER/REPO)")
    issue_number: int = Field(..., gt=0, description="Target issue number to plan for")
    profile: ContributorProfile
    provider: Optional[str] = Field(default=None, description="Optional explicit model provider")
    demo: Optional[bool] = Field(default=False, description="Request fixture demo mode")


class PlanStep(BaseModel):
    """Actionable step in the first-PR implementation plan."""

    title: str = Field(..., description="Short title for this step")
    detail: str = Field(..., description="Specific instructions grounded in code")
    kind: Literal["verified", "inference"] = Field(
        default="inference",
        description="Whether this step is based on verified facts or inference",
    )
    files: list[str] = Field(default_factory=list, description="Files to inspect or edit (must be in repo tree)")


class PlanNote(BaseModel):
    """Guidance note for setup or testing with evidence provenance."""

    status: Literal["verified", "unknown", "inference"]
    notes: str


class PlanResponse(BaseModel):
    """Complete response for POST /api/plan."""

    issue_number: int
    issue_title: str
    issue_url: str
    summary: str
    steps: list[PlanStep] = Field(..., min_length=1, max_length=10)
    setup_guidance: PlanNote
    test_guidance: PlanNote
    checklist: list[str] = Field(default_factory=list)
    pr_title: str
    pr_description_draft: str
    open_questions_for_maintainer: list[str] = Field(default_factory=list)
    ai_status: Literal["complete", "unavailable_or_invalid"]
    warnings: list[str] = Field(default_factory=list)
    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
