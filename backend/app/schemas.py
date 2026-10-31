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
    has_ci: Optional[bool] = None
    ci_status: Literal["detected", "none_detected", "unknown"] = "unknown"
    ci_evidence: Optional[SignalEvidence] = None
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

    # Issue-to-module mapping (M1 Repository Intelligence)
    module_mapping: Optional["IssueToModuleMapping"] = None

    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    truncated: bool = False


# -------------------------------------------------------------
# M1: Repository Intelligence Schemas
# -------------------------------------------------------------


class IntelligenceEvidence(BaseModel):
    """Evidence supporting an intelligence finding."""

    status: EvidenceStatus
    source: str
    observed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    detail: Optional[str] = None


class TechnologyItem(BaseModel):
    """Detected technology, framework, library or build tool."""

    name: str
    category: Literal[
        "framework", "library", "runtime", "tool", "ci_cd", "database", "bundler", "test_framework"
    ]
    evidence: IntelligenceEvidence
    matched_paths: list[str] = Field(default_factory=list)


class LanguageDistribution(BaseModel):
    """Primary and secondary programming languages with provenance."""

    primary: Optional[str] = None
    secondary: list[str] = Field(default_factory=list)
    source: str = "github_languages_and_tree"


class EntryPoint(BaseModel):
    """Identified key repository entry point or manifest."""

    path: str
    kind: Literal[
        "application",
        "library",
        "cli",
        "backend",
        "frontend",
        "configuration",
        "manifest",
        "build_deployment",
        "documentation",
    ]
    confidence: Literal["detected", "candidate"]
    reason: str
    evidence: IntelligenceEvidence


class TestProfile(BaseModel):
    """Deterministic repository test infrastructure assessment."""

    status: Literal["detected", "not_detected", "unknown"]
    test_directories: list[str] = Field(default_factory=list)
    test_file_count: int = 0
    frameworks: list[str] = Field(default_factory=list)
    configuration_files: list[str] = Field(default_factory=list)
    ci_configuration: Optional[SignalEvidence] = None
    likely_commands: list[str] = Field(default_factory=list)
    evidence: IntelligenceEvidence
    limitations: list[str] = Field(default_factory=list)


class DocSectionSummary(BaseModel):
    """Structured section extracted from repository documentation."""

    heading: str
    content_excerpt: str
    category: Literal["purpose", "setup", "testing", "contributing", "architecture", "other"]


class DocFileSummary(BaseModel):
    """Summary of an inspected documentation file."""

    path: str
    doc_type: Literal["readme", "contributing", "architecture", "setup", "license", "other"]
    exists: bool = True
    key_sections: list[DocSectionSummary] = Field(default_factory=list)
    extracted_purpose: Optional[str] = None
    setup_commands: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    evidence: IntelligenceEvidence


class DocumentationProfile(BaseModel):
    """Extracted documentation intelligence with bounded scope."""

    has_readme: bool = False
    has_contributing: bool = False
    project_purpose: Optional[str] = None
    docs: list[DocFileSummary] = Field(default_factory=list)
    setup_instructions: Optional[str] = None
    test_instructions: Optional[str] = None
    contributing_guidelines_summary: Optional[str] = None
    architecture_overview: Optional[str] = None
    evidence: IntelligenceEvidence


class ModuleSummary(BaseModel):
    """Identified repository component or functional module."""

    name: str
    root_path: str
    files: list[str] = Field(default_factory=list)
    file_count: int = 0
    likely_responsibility: str
    component_type: Literal[
        "core_logic",
        "api_routes",
        "ui_components",
        "tests",
        "configuration",
        "documentation",
        "utility",
        "cli",
        "service",
    ]
    confidence: Literal["high", "medium", "low"]
    evidence: IntelligenceEvidence
    key_entry_files: list[str] = Field(default_factory=list)


class IssueCandidateMapping(BaseModel):
    """Mapped candidate file for a specific GitHub issue."""

    path: str
    module_name: Optional[str] = None
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    evidence: IntelligenceEvidence


class IssueToModuleMapping(BaseModel):
    """Deterministic connection between a GitHub issue and repository components."""

    issue_number: int
    issue_title: str
    candidate_modules: list[str] = Field(default_factory=list)
    candidate_files: list[IssueCandidateMapping] = Field(default_factory=list)
    rationale: str
    unknowns_and_limitations: list[str] = Field(default_factory=list)
    evidence: IntelligenceEvidence


class RepositoryIntelligenceReport(BaseModel):
    """Comprehensive evidence-backed repository intelligence report."""

    repo_owner: str
    repo_name: str
    languages: LanguageDistribution
    project_type: Literal[
        "web_application",
        "api_service",
        "library_or_sdk",
        "cli_tool",
        "monorepo",
        "documentation_or_static",
        "other",
    ]
    project_type_rationale: str
    structure_type: Literal["monorepo", "single_package", "multi_module", "standard_flat"]
    technologies: list[TechnologyItem] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    manifest_files: list[str] = Field(default_factory=list)
    configuration_files: list[str] = Field(default_factory=list)
    entry_points: list[EntryPoint] = Field(default_factory=list)
    test_profile: TestProfile
    documentation_profile: DocumentationProfile
    modules: list[ModuleSummary] = Field(default_factory=list)
    issue_mappings: list[IssueToModuleMapping] = Field(default_factory=list)
    inspected_paths_count: int = 0
    tree_truncated: bool = False
    evidence: IntelligenceEvidence
    warnings: list[str] = Field(default_factory=list)


class IntelligenceRequest(BaseModel):
    """Request schema for POST /api/intelligence."""

    repo_url: str = Field(..., description="Canonical GitHub repo URL (https://github.com/OWNER/REPO)")
    demo: Optional[bool] = Field(default=False, description="Request fixture demo mode")


class AnalyzeResponse(BaseModel):
    """Complete response for POST /api/analyze."""

    repo: RepoMetadata
    provider: str
    actual_model: str
    ai_status: Literal["complete", "partial", "unavailable_or_invalid"]
    issues: list[CandidateIssue] = Field(default_factory=list)
    intelligence: Optional[RepositoryIntelligenceReport] = None
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


# Resolve forward references
CandidateIssue.model_rebuild()
