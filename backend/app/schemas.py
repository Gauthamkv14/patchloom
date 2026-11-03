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


# -------------------------------------------------------------
# M2: Intelligent Issue Learning Brief Schemas (LEARN Pillar)
# -------------------------------------------------------------


class IssueExplanation(BaseModel):
    """Personalized, multi-facet plain-language explanation of a GitHub issue."""

    summary: str = Field(..., description="High-level plain-language summary adapted to experience level")
    problem_description: str = Field(..., description="Core problem or defect being reported")
    why_it_matters: Optional[str] = Field(default=None, description="Impact and rationale supported by evidence")
    expected_outcome: str = Field(..., description="Expected behavior once resolved")
    explicit_requirements: list[str] = Field(default_factory=list, description="Explicit requirements stated in the issue")
    constraints_and_conditions: list[str] = Field(default_factory=list, description="Constraints, edge cases, or conditions mentioned")
    ambiguities_and_unanswered_questions: list[str] = Field(default_factory=list, description="Unclear areas, missing reproduction details, or maintainer questions")
    experience_adaptation_note: str = Field(..., description="Explanation of how this brief is adapted to the contributor's experience level")


class IssueRequirement(BaseModel):
    """Structured requirement extracted from issue text or comments."""

    description: str = Field(..., description="Requirement description")
    source: str = Field(..., description="Source: issue_description | issue_comment | repository_docs")
    supporting_evidence: str = Field(..., description="Verbatim or close excerpt supporting this requirement")
    classification: Literal["explicit", "inferred"] = Field(..., description="Whether explicitly stated or inferred")
    confidence: Literal["high", "medium", "low"] = Field(default="medium", description="Confidence in this requirement")


class RelevantInvestigationFile(BaseModel):
    """Grounded repository file target with exploration instructions."""

    path: str = Field(..., description="File path strictly verified in repository tree")
    module_name: Optional[str] = Field(default=None, description="Logical component or module name")
    why_relevant: str = Field(..., description="Why this file is relevant to the issue")
    what_to_inspect: str = Field(..., description="Specific classes, functions, or patterns to inspect")
    kind: Literal["detected", "candidate"] = Field(default="candidate", description="Detected direct entrypoint or heuristic candidate")
    evidence: IntelligenceEvidence


class LearningConcept(BaseModel):
    """Technical concept to master before or while working on this issue."""

    name: str = Field(..., description="Concept name (e.g. Asynchronous I/O, Socket Timeout, RST syntax)")
    explanation: str = Field(..., description="Beginner-friendly explanation of the concept")
    why_it_matters: str = Field(..., description="Why understanding this concept is essential for this issue")
    prerequisites: list[str] = Field(default_factory=list, description="Prerequisite knowledge or foundational concepts")
    learning_order: int = Field(default=1, ge=1, le=10, description="Suggested sequence order for learning")
    difficulty: Literal["beginner", "intermediate", "advanced"] = Field(default="beginner", description="Difficulty level")


class LearningObjective(BaseModel):
    """Actionable, measurable educational objective for the contributor."""

    title: str = Field(..., description="Short objective title")
    description: str = Field(..., description="What the contributor will understand or identify")
    relevance: str = Field(..., description="Why this objective matters for solving the issue")
    completion_criterion: str = Field(..., description="How the contributor knows they achieved this objective")


class ReadinessChecklistItem(BaseModel):
    """Practical readiness checklist item to assess understanding before coding."""

    category: Literal[
        "problem_understanding",
        "expected_behavior",
        "architecture_components",
        "technical_concepts",
        "testing_approach",
        "remaining_uncertainties",
    ] = Field(..., description="Readiness dimension")
    item: str = Field(..., description="Readiness check question or statement")
    guidance: str = Field(..., description="Self-check guidance on how to confirm readiness")


class IssueLearningBrief(BaseModel):
    """Complete structured Issue Learning Brief for a selected issue (M2 - LEARN Pillar)."""

    issue_number: int
    issue_title: str
    issue_url: str
    experience_level: Literal["beginner", "intermediate", "advanced"]
    explanation: IssueExplanation
    requirements: list[IssueRequirement] = Field(default_factory=list)
    relevant_modules: list[str] = Field(default_factory=list)
    investigation_targets: list[RelevantInvestigationFile] = Field(default_factory=list)
    related_tests_and_docs: list[str] = Field(default_factory=list)
    concepts: list[LearningConcept] = Field(default_factory=list)
    learning_objectives: list[LearningObjective] = Field(default_factory=list)
    readiness_checklist: list[ReadinessChecklistItem] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    ai_status: Literal["complete", "unavailable_or_invalid"]
    warnings: list[str] = Field(default_factory=list)
    evidence: IntelligenceEvidence
    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class LearnRequest(BaseModel):
    """Request schema for POST /api/learn."""

    repo_url: str = Field(..., description="Canonical GitHub repo URL (https://github.com/OWNER/REPO)")
    issue_number: int = Field(..., description="GitHub issue number to generate learning brief for")
    profile: ContributorProfile
    provider: Optional[str] = Field(default=None, description="Optional explicit model provider")
    demo: Optional[bool] = Field(default=False, description="Request fixture demo mode")


# =====================================================================
# M3: Guided Implementation Schemas (LEARN & BUILD Pillar)
# =====================================================================


class StepCheckpoint(BaseModel):
    """Self-reflection question and verification guidance for an implementation step."""

    question: str = Field(..., description="Self-check reflection question")
    verification_guidance: str = Field(..., description="Actionable advice on how to confirm this step")


class ProgressiveHint(BaseModel):
    """Progressive hint revealing technical guidance step-by-step upon user request."""

    level: int = Field(..., ge=1, le=3, description="1: gentle direction, 2: specific investigation, 3: technical guidance")
    title: str = Field(..., description="Short hint title (e.g. 'Where to look', 'Inspecting parameters')")
    content: str = Field(..., description="Educational guidance text that gradually reduces ambiguity")
    kind: Literal["evidence_based", "conceptual_guidance"] = Field(
        default="evidence_based",
        description="Whether derived directly from verified repository evidence or conceptual pattern",
    )


class CodeExplorationTarget(BaseModel):
    """Relevant repository file with targeted exploration and navigation advice."""

    path: str = Field(..., description="File path strictly verified in repository tree")
    module_name: Optional[str] = Field(default=None, description="Component or module name")
    why_relevant: str = Field(..., description="Why this file matters to the issue")
    target_symbols: list[str] = Field(default_factory=list, description="Specific functions, classes, or sections to inspect")
    behavior_to_observe: str = Field(..., description="What runtime behavior, data flow, or error checks to observe")
    suggested_search_terms: list[str] = Field(default_factory=list, description="Helpful identifiers or terms to search for in this file")
    evidence: IntelligenceEvidence


class PatchSuggestion(BaseModel):
    """Optional, educational code or patch snippet requested explicitly by contributor."""

    target_path: str = Field(..., description="Target file path in repository tree")
    target_symbol: Optional[str] = Field(default=None, description="Relevant function, method, or class name")
    summary: str = Field(..., description="Plain-language explanation of the proposed change")
    code_snippet: str = Field(..., description="Educational code snippet or diff illustrating the approach")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions made about the surrounding code")
    expected_effect: str = Field(..., description="Expected behavior once this change is introduced")
    potential_risks: list[str] = Field(default_factory=list, description="Edge cases, regression risks, or compatibility caveats")
    verification_status: Literal["unverified_educational_draft"] = Field(
        default="unverified_educational_draft",
        description="Explicit notice that this suggestion has not been automatically tested or applied",
    )


class ImplementationApproach(BaseModel):
    """A viable implementation approach with design trade-offs and edge cases."""

    approach_id: str = Field(..., description="Unique slug for this approach (e.g. 'approach-adapter-timeout')")
    title: str = Field(..., description="Short title of the approach")
    summary: str = Field(..., description="Overview of how this approach addresses the issue")
    relevant_design_patterns: list[str] = Field(default_factory=list, description="Design patterns or repository idioms used")
    pros: list[str] = Field(default_factory=list, description="Advantages of this approach")
    cons_and_tradeoffs: list[str] = Field(default_factory=list, description="Trade-offs, complexity, or limitations")
    edge_cases: list[str] = Field(default_factory=list, description="Potential edge cases to guard against")
    regression_risks: list[str] = Field(default_factory=list, description="Potential risks to existing functionality")
    unanswered_questions: list[str] = Field(default_factory=list, description="Questions for maintainers or remaining uncertainties")


class ImplementationStep(BaseModel):
    """A practical, ordered step in the guided implementation roadmap."""

    id: str = Field(..., description="Unique step identifier (e.g. 'step-1')")
    order: int = Field(..., ge=1, description="Sequential order in the roadmap")
    title: str = Field(..., description="Step title")
    objective: str = Field(..., description="What the contributor will achieve or understand in this step")
    why_it_matters: str = Field(..., description="Why this step is necessary")
    files: list[str] = Field(default_factory=list, description="Repository files relevant to this step (strictly grounded in tree)")
    what_to_inspect: str = Field(..., description="Specific elements, signatures, or tests to inspect")
    expected_outcome: str = Field(..., description="Expected state or understanding upon completion")
    dependencies: list[str] = Field(default_factory=list, description="IDs of steps that should be completed before this step")
    completion_criteria: str = Field(..., description="Concrete criteria the contributor uses to self-verify completion")
    hints: list[ProgressiveHint] = Field(default_factory=list, description="Up to 3 progressive hints for this step")
    checkpoint: StepCheckpoint
    patch_suggestion: Optional[PatchSuggestion] = Field(default=None, description="Optional educational code suggestion")


class GuidedImplementationPlan(BaseModel):
    """Complete structured Guided Implementation workspace for an issue (M3 - LEARN & BUILD Pillar)."""

    issue_number: int
    issue_title: str
    issue_url: str
    experience_level: Literal["beginner", "intermediate", "advanced"]
    overview: str = Field(..., description="High-level implementation strategy adapted to contributor level")
    steps: list[ImplementationStep] = Field(default_factory=list)
    exploration_targets: list[CodeExplorationTarget] = Field(default_factory=list)
    approaches: list[ImplementationApproach] = Field(default_factory=list)
    recommended_approach_id: str = Field(..., description="ID of the recommended starting approach")
    ai_status: Literal["complete", "unavailable_or_invalid"]
    warnings: list[str] = Field(default_factory=list)
    evidence: IntelligenceEvidence
    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class GuidedImplementationRequest(BaseModel):
    """Request schema for POST /api/guided-implementation."""

    repo_url: str = Field(..., description="Canonical GitHub repo URL (https://github.com/OWNER/REPO)")
    issue_number: int = Field(..., description="GitHub issue number to generate guided implementation for")
    profile: ContributorProfile
    provider: Optional[str] = Field(default=None, description="Optional explicit model provider")
    demo: Optional[bool] = Field(default=False, description="Request fixture demo mode")
    learning_brief: Optional[IssueLearningBrief] = Field(default=None, description="Optional pre-existing IssueLearningBrief to reuse")


# =====================================================================
# M4: Verification & Review Schemas (VERIFY & CONTRIBUTE Pillar)
# =====================================================================


class DiffChangeFile(BaseModel):
    """A file touched by the contributor's diff."""

    path: str = Field(..., description="Relative file path")
    old_path: Optional[str] = Field(default=None, description="Original path if renamed or deleted")
    change_type: Literal["added", "modified", "deleted", "renamed"] = Field(..., description="Type of change")
    lines_added: int = Field(default=0, ge=0)
    lines_removed: int = Field(default=0, ge=0)
    detected_symbols: list[str] = Field(default_factory=list, description="Functions or classes modified in this file")


class ParsedDiff(BaseModel):
    """Deterministic structural breakdown of a contributor-provided git diff."""

    total_files: int = Field(default=0, ge=0)
    lines_added: int = Field(default=0, ge=0)
    lines_removed: int = Field(default=0, ge=0)
    files: list[DiffChangeFile] = Field(default_factory=list)
    raw_diff_sample: str = Field(default="", description="Bounded raw diff excerpt for display")
    is_truncated: bool = Field(default=False)
    warnings: list[str] = Field(default_factory=list)


class DiscoveredTest(BaseModel):
    """A candidate test file identified as relevant to the contributor's changes."""

    test_file: str = Field(..., description="Relative test file path")
    framework: str = Field(..., description="Test framework (e.g. pytest, Jest, Vitest)")
    test_command: str = Field(..., description="Specific command to run this test")
    confidence: Literal["high", "medium", "low"] = Field(..., description="Relevance confidence")
    selection_rationale: str = Field(..., description="Why this test was chosen based on evidence")
    kind: Literal["verified", "candidate"] = Field(default="candidate")
    target_module: Optional[str] = Field(default=None)
    evidence: IntelligenceEvidence


class TestExecutionPlan(BaseModel):
    """Strictly allowlisted test execution plan to be authorized by contributor."""

    __test__ = False
    test_runner: str = Field(..., description="Test runner identifier (e.g. pytest, vitest)")
    command: str = Field(..., description="Allowlisted execution command")
    arguments: list[str] = Field(default_factory=list, description="Structured arguments to pass")
    working_dir: str = Field(default=".")
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    is_allowlisted: bool = Field(default=True)
    disclaimer: str = Field(
        default="Execution runs in an isolated, network-disabled Docker container with dropped capabilities."
    )


class TestExecutionResult(BaseModel):
    """Deterministic result of an isolated test execution."""

    __test__ = False
    status: Literal[
        "passed",
        "failed",
        "timed_out",
        "execution_unavailable",
        "invalid_or_unsupported",
        "error",
    ]
    runner: str
    command: str
    duration_seconds: float = Field(default=0.0, ge=0.0)
    exit_code: Optional[int] = Field(default=None)
    tests_total: Optional[int] = Field(default=None)
    tests_passed: Optional[int] = Field(default=None)
    tests_failed: Optional[int] = Field(default=None)
    tests_skipped: Optional[int] = Field(default=None)
    stdout_bounded: str = Field(default="")
    stderr_bounded: str = Field(default="")
    failure_details: list[str] = Field(default_factory=list)
    failure_locations: list[str] = Field(default_factory=list)
    ai_likely_causes: list[str] = Field(default_factory=list, description="AI explanations clearly labeled as inference")
    ai_suggested_next_steps: list[str] = Field(default_factory=list, description="AI investigation suggestions")
    simulated: bool = Field(default=False, description="True if executed in fixture/demo mode")
    executed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ReviewFinding(BaseModel):
    """Evidence-grounded code review finding from diff analysis."""

    finding_id: str = Field(..., description="Stable identifier (e.g. 'finding-1')")
    severity: Literal["critical", "high", "medium", "low", "informational"]
    category: Literal[
        "logic_error",
        "edge_case",
        "error_handling",
        "input_validation",
        "security",
        "resource_management",
        "regression",
        "test_coverage",
        "other",
    ]
    title: str = Field(..., description="Concise finding headline")
    explanation: str = Field(..., description="Detailed explanation of potential issue")
    evidence: str = Field(..., description="Excerpt or citation from the diff")
    file_path: str = Field(..., description="Target file path")
    line_range: Optional[str] = Field(default=None, description="Line number or range (e.g. '42-45')")
    why_it_matters: str = Field(..., description="Impact of leaving this unaddressed")
    suggested_action: str = Field(..., description="Actionable suggestion for contributor")
    confidence: Literal["high", "medium", "low"]


class RegressionRisk(BaseModel):
    """Identified regression risk to existing repository modules."""

    affected_module_or_file: str = Field(..., description="Module or component at risk")
    risk_type: Literal["directly_affected", "potentially_affected", "unknown"]
    evidence: str = Field(..., description="Evidence connecting change to risk")
    potential_impact: str = Field(..., description="What could break if regression occurs")
    suggested_verification: str = Field(..., description="How contributor can verify safety")
    confidence: Literal["high", "medium", "low"]


class ReadinessAssessment(BaseModel):
    """Transparent assessment of whether diff is ready for maintainer review."""

    status: Literal["ready_for_review", "needs_attention", "insufficient_evidence"]
    summary: str = Field(..., description="Clear rationale explaining the status")
    outstanding_items: list[str] = Field(default_factory=list, description="Items that require contributor attention")
    checklist_status: dict[str, bool] = Field(default_factory=dict, description="Status of required contributor checks")


class DraftPR(BaseModel):
    """Maintainer-ready draft PR package built strictly from verified context."""

    title: str = Field(..., description="Suggested pull request title following project conventions")
    summary_of_changes: str = Field(..., description="Executive summary of modifications")
    problem_addressed: str = Field(..., description="Issue context and problem resolved")
    implementation_overview: str = Field(..., description="Description of changes made")
    tests_performed: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Structured test results (executed_passed, executed_failed, not_executed, manually_verified)",
    )
    known_limitations: list[str] = Field(default_factory=list, description="Known boundary conditions or out-of-scope items")
    remaining_concerns: list[str] = Field(default_factory=list, description="Questions or open items for maintainer")
    manual_verification_checklist: list[str] = Field(default_factory=list, description="Final contributor verification checklist")


class VerificationAnalysisReport(BaseModel):
    """Complete response for POST /api/verification/analyze (M4 VERIFY & CONTRIBUTE Pillar)."""

    issue_number: int
    issue_title: str
    repo_url: str
    parsed_diff: ParsedDiff
    roadmap_alignment_summary: str = Field(..., description="How well changes align with M3 implementation roadmap")
    potentially_unrelated_files: list[str] = Field(default_factory=list)
    discovered_tests: list[DiscoveredTest] = Field(default_factory=list)
    suggested_execution_plan: Optional[TestExecutionPlan] = None
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    regression_risks: list[RegressionRisk] = Field(default_factory=list)
    readiness: ReadinessAssessment
    ai_status: Literal["complete", "unavailable_or_invalid"]
    warnings: list[str] = Field(default_factory=list)
    evidence: IntelligenceEvidence
    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class VerificationAnalyzeRequest(BaseModel):
    """Request schema for POST /api/verification/analyze."""

    repo_url: str = Field(..., description="Canonical GitHub repo URL (https://github.com/OWNER/REPO)")
    issue_number: int = Field(..., description="GitHub issue number")
    diff_text: str = Field(..., description="Contributor git diff text")
    profile: Optional[ContributorProfile] = Field(default=None)
    provider: Optional[str] = Field(default=None)
    demo: Optional[bool] = Field(default=False)


class VerificationExecuteRequest(BaseModel):
    """Request schema for POST /api/verification/execute."""

    repo_url: str = Field(..., description="Canonical GitHub repo URL (https://github.com/OWNER/REPO)")
    issue_number: int = Field(..., description="GitHub issue number")
    execution_plan: TestExecutionPlan = Field(..., description="Validated execution plan")
    diff_text: Optional[str] = Field(default="", description="Optional diff text for isolated workspace patching")
    authorized: bool = Field(..., description="Explicit contributor authorization to run isolated test container")
    demo: Optional[bool] = Field(default=False)


class VerificationPreparePRRequest(BaseModel):
    """Request schema for POST /api/verification/prepare-pr."""

    repo_url: str = Field(..., description="Canonical GitHub repo URL (https://github.com/OWNER/REPO)")
    issue_number: int = Field(..., description="GitHub issue number")
    diff_text: str = Field(..., description="Contributor git diff text")
    profile: Optional[ContributorProfile] = Field(default=None)
    execution_result: Optional[TestExecutionResult] = Field(default=None)
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    regression_risks: list[RegressionRisk] = Field(default_factory=list)
    readiness: Optional[ReadinessAssessment] = Field(default=None)
    provider: Optional[str] = Field(default=None)
    demo: Optional[bool] = Field(default=False)



# Resolve forward references
CandidateIssue.model_rebuild()
