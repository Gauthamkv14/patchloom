export interface HealthData {
  status: string;
  demo_mode: boolean;
  environment: string;
  has_gemini_key: boolean;
  has_github_token: boolean;
}

export interface ContributorProfile {
  skills: string[];
  preferred_languages: string[];
  experience_level: 'beginner' | 'intermediate' | 'advanced';
  available_hours: number;
  learning_goal?: string;
}

export interface SignalEvidence {
  status: 'verified' | 'unknown' | 'inference';
  source: string;
  observed_at: string;
  value: any;
}

export interface IntelligenceEvidence {
  status: 'verified' | 'unknown' | 'inference';
  source: string;
  observed_at: string;
  detail: string;
}

export interface TechnologyItem {
  name: string;
  category: 'framework' | 'library' | 'build_tool' | 'linter' | 'runtime' | 'database' | 'container' | 'other';
  confidence: 'detected' | 'candidate';
  source: string;
  evidence: IntelligenceEvidence;
}

export interface LanguageDistribution {
  primary: string | null;
  secondary: string[];
  source: string;
}

export interface EntryPoint {
  path: string;
  kind: 'application' | 'library' | 'cli' | 'backend' | 'frontend' | 'configuration' | 'manifest' | 'build_deployment' | 'documentation';
  confidence: 'detected' | 'candidate';
  reason: string;
  evidence: IntelligenceEvidence;
}

export interface TestProfile {
  status: 'detected' | 'not_detected' | 'unknown';
  test_directories: string[];
  test_file_count: number;
  frameworks: string[];
  configuration_files: string[];
  ci_configuration?: SignalEvidence | null;
  likely_commands: string[];
  evidence: IntelligenceEvidence;
  limitations: string[];
}

export interface DocSectionSummary {
  heading: string;
  content_excerpt: string;
  category: 'purpose' | 'setup' | 'testing' | 'contributing' | 'architecture' | 'other';
}

export interface DocFileSummary {
  path: string;
  doc_type: 'readme' | 'contributing' | 'architecture' | 'setup' | 'license' | 'other';
  exists: boolean;
  key_sections: DocSectionSummary[];
  extracted_purpose?: string | null;
  setup_commands: string[];
  test_commands: string[];
  evidence: IntelligenceEvidence;
}

export interface DocumentationProfile {
  has_readme: boolean;
  has_contributing: boolean;
  project_purpose?: string | null;
  docs: DocFileSummary[];
  setup_instructions?: string | null;
  test_instructions?: string | null;
  contributing_guidelines_summary?: string | null;
  architecture_overview?: string | null;
  evidence: IntelligenceEvidence;
}

export interface ModuleSummary {
  name: string;
  root_path: string;
  files: string[];
  file_count: number;
  likely_responsibility: string;
  component_type: 'core_logic' | 'api_routes' | 'ui_components' | 'tests' | 'configuration' | 'documentation' | 'utility' | 'cli' | 'service';
  confidence: 'high' | 'medium' | 'low';
  evidence: IntelligenceEvidence;
  key_entry_files: string[];
}

export interface IssueCandidateMapping {
  path: string;
  module_name?: string | null;
  relevance_score: number;
  reasons: string[];
  evidence: IntelligenceEvidence;
}

export interface IssueToModuleMapping {
  issue_number: number;
  issue_title: string;
  candidate_modules: string[];
  candidate_files: IssueCandidateMapping[];
  rationale: string;
  unknowns_and_limitations: string[];
  evidence: IntelligenceEvidence;
}

export interface RepositoryIntelligenceReport {
  repo_owner: string;
  repo_name: string;
  languages: LanguageDistribution;
  project_type: 'web_application' | 'api_service' | 'library_or_sdk' | 'cli_tool' | 'monorepo' | 'documentation_or_static' | 'other';
  project_type_rationale: string;
  structure_type: 'monorepo' | 'single_package' | 'multi_module' | 'standard_flat';
  technologies: TechnologyItem[];
  package_managers: string[];
  manifest_files: string[];
  configuration_files: string[];
  entry_points: EntryPoint[];
  test_profile: TestProfile;
  documentation_profile: DocumentationProfile;
  modules: ModuleSummary[];
  issue_mappings: IssueToModuleMapping[];
  inspected_paths_count: number;
  tree_truncated: boolean;
  evidence: IntelligenceEvidence;
  warnings: string[];
}

export interface RepoMetadata {
  owner: string;
  name: string;
  description?: string;
  default_branch: string;
  languages: string[];
  open_issues_count: number;
  checked_at: string;
  has_readme: boolean;
  has_contributing: boolean;
  has_ci?: boolean | null;
  ci_status?: 'detected' | 'none_detected' | 'unknown';
  ci_evidence?: SignalEvidence;
  tree_truncated: boolean;
}

export interface CandidateIssue {
  number: number;
  title: string;
  url: string;
  labels: string[];
  created_at: string;
  updated_at: string;
  comments_count: number;
  viability_score: number;
  viability_band: 'high' | 'medium' | 'low';
  signals: Record<string, SignalEvidence>;
  negative_factors: string[];
  unknown_factors: string[];
  fit_score?: number;
  final_score?: number;
  matching_skills: string[];
  skill_gaps: string[];
  estimated_hours?: number;
  likely_files: string[];
  reason?: string;
  risks: string[];
  inferences: string[];
  checked_at: string;
  truncated: boolean;
  module_mapping?: IssueToModuleMapping | null;
}

export interface AnalyzeResponse {
  repo: RepoMetadata;
  provider: string;
  actual_model: string;
  ai_status: 'complete' | 'partial' | 'unavailable_or_invalid';
  issues: CandidateIssue[];
  intelligence?: RepositoryIntelligenceReport | null;
  warnings: string[];
}

export interface PlanStep {
  title: string;
  detail: string;
  kind: 'verified' | 'inference';
  files: string[];
}

export interface PlanNote {
  status: 'verified' | 'unknown' | 'inference';
  notes: string;
}

export interface PlanResponse {
  issue_number: number;
  issue_title: string;
  issue_url: string;
  summary: string;
  steps: PlanStep[];
  setup_guidance: PlanNote;
  test_guidance: PlanNote;
  checklist: string[];
  pr_title: string;
  pr_description_draft: string;
  open_questions_for_maintainer: string[];
  ai_status: 'complete' | 'unavailable_or_invalid';
  warnings: string[];
  checked_at: string;
}

export interface IssueExplanation {
  summary: string;
  problem_description: string;
  why_it_matters?: string | null;
  expected_outcome: string;
  explicit_requirements: string[];
  constraints_and_conditions: string[];
  ambiguities_and_unanswered_questions: string[];
  experience_adaptation_note: string;
}

export interface IssueRequirement {
  description: string;
  source: string;
  supporting_evidence: string;
  classification: 'explicit' | 'inferred';
  confidence: 'high' | 'medium' | 'low';
}

export interface RelevantInvestigationFile {
  path: string;
  module_name?: string | null;
  why_relevant: string;
  what_to_inspect: string;
  kind: 'detected' | 'candidate';
  evidence: IntelligenceEvidence;
}

export interface LearningConcept {
  name: string;
  explanation: string;
  why_it_matters: string;
  prerequisites: string[];
  learning_order: number;
  difficulty: 'beginner' | 'intermediate' | 'advanced';
}

export interface LearningObjective {
  title: string;
  description: string;
  relevance: string;
  completion_criterion: string;
}

export interface ReadinessChecklistItem {
  category:
    | 'problem_understanding'
    | 'expected_behavior'
    | 'architecture_components'
    | 'technical_concepts'
    | 'testing_approach'
    | 'remaining_uncertainties';
  item: string;
  guidance: string;
}

export interface IssueLearningBrief {
  issue_number: number;
  issue_title: string;
  issue_url: string;
  experience_level: 'beginner' | 'intermediate' | 'advanced';
  explanation: IssueExplanation;
  requirements: IssueRequirement[];
  relevant_modules: string[];
  investigation_targets: RelevantInvestigationFile[];
  related_tests_and_docs: string[];
  concepts: LearningConcept[];
  learning_objectives: LearningObjective[];
  readiness_checklist: ReadinessChecklistItem[];
  unresolved_questions: string[];
  ai_status: 'complete' | 'unavailable_or_invalid';
  warnings: string[];
  evidence: IntelligenceEvidence;
  checked_at: string;
}

// =====================================================================
// M3: Guided Implementation Types (LEARN & BUILD Pillar)
// =====================================================================

export interface StepCheckpoint {
  question: string;
  verification_guidance: string;
}

export interface ProgressiveHint {
  level: number;
  title: string;
  content: string;
  kind: 'evidence_based' | 'conceptual_guidance';
}

export interface CodeExplorationTarget {
  path: string;
  module_name?: string | null;
  why_relevant: string;
  target_symbols: string[];
  behavior_to_observe: string;
  suggested_search_terms: string[];
  evidence: IntelligenceEvidence;
}

export interface PatchSuggestion {
  target_path: string;
  target_symbol?: string | null;
  summary: string;
  code_snippet: string;
  assumptions: string[];
  expected_effect: string;
  potential_risks: string[];
  verification_status: 'unverified_educational_draft';
}

export interface ImplementationApproach {
  approach_id: string;
  title: string;
  summary: string;
  relevant_design_patterns: string[];
  pros: string[];
  cons_and_tradeoffs: string[];
  edge_cases: string[];
  regression_risks: string[];
  unanswered_questions: string[];
}

export interface ImplementationStep {
  id: string;
  order: number;
  title: string;
  objective: string;
  why_it_matters: string;
  files: string[];
  what_to_inspect: string;
  expected_outcome: string;
  dependencies: string[];
  completion_criteria: string;
  hints: ProgressiveHint[];
  checkpoint: StepCheckpoint;
  patch_suggestion?: PatchSuggestion | null;
}

export interface GuidedImplementationPlan {
  issue_number: number;
  issue_title: string;
  issue_url: string;
  experience_level: 'beginner' | 'intermediate' | 'advanced';
  overview: string;
  steps: ImplementationStep[];
  exploration_targets: CodeExplorationTarget[];
  approaches: ImplementationApproach[];
  recommended_approach_id: string;
  ai_status: 'complete' | 'unavailable_or_invalid';
  warnings: string[];
  evidence: IntelligenceEvidence;
  checked_at: string;
}

export interface DiffChangeFile {
  path: string;
  old_path?: string | null;
  change_type: 'added' | 'modified' | 'deleted';
  lines_added: number;
  lines_removed: number;
  detected_symbols: string[];
}

export interface ParsedDiff {
  files: DiffChangeFile[];
  total_files: number;
  lines_added: number;
  lines_removed: number;
  raw_diff_sample?: string;
  is_truncated: boolean;
  warnings: string[];
}

export interface DiscoveredTest {
  test_file: string;
  framework: string;
  test_command: string;
  confidence: 'high' | 'medium' | 'low';
  selection_rationale: string;
  kind: 'counterpart_test' | 'module_test' | 'roadmap_step_test' | 'profile_test' | 'candidate';
  target_module?: string | null;
  evidence: IntelligenceEvidence;
}

export interface TestExecutionPlan {
  test_runner: string;
  command: string;
  arguments: string[];
  working_dir: string;
  timeout_seconds: number;
  is_allowlisted: boolean;
  disclaimer: string;
}

export interface TestExecutionResult {
  status: 'passed' | 'failed' | 'timed_out' | 'execution_unavailable' | 'invalid_or_unsupported' | 'error';
  runner: string;
  command: string;
  duration_seconds: number;
  exit_code: number;
  tests_total?: number | null;
  tests_passed?: number | null;
  tests_failed?: number | null;
  tests_skipped?: number | null;
  stdout_bounded: string;
  stderr_bounded: string;
  failure_details: string[];
  failure_locations: string[];
  ai_likely_causes: string[];
  ai_suggested_next_steps: string[];
  simulated: boolean;
  executed_at: string;
}

export interface ReviewFinding {
  finding_id: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'informational';
  category: 'logic_error' | 'edge_case' | 'error_handling' | 'input_validation' | 'security' | 'resource_management' | 'regression' | 'test_coverage' | 'other';
  title: string;
  explanation: string;
  evidence: string;
  file_path: string;
  line_range?: string | null;
  why_it_matters: string;
  suggested_action: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface RegressionRisk {
  risk_id: string;
  affected_module_or_file: string;
  risk_type: 'directly_affected' | 'potentially_affected' | 'unknown';
  evidence: string;
  potential_impact: string;
  suggested_verification: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface ReadinessAssessment {
  status: 'ready_for_review' | 'needs_attention' | 'insufficient_evidence';
  summary: string;
  outstanding_items: string[];
  checklist_status: Record<string, boolean>;
}

export interface DraftPR {
  title: string;
  summary_of_changes: string;
  problem_addressed: string;
  implementation_overview: string;
  tests_performed: Record<string, string[]>;
  known_limitations: string[];
  remaining_concerns: string[];
  manual_verification_checklist: string[];
}

export interface VerificationAnalysisReport {
  issue_number: number;
  issue_title: string;
  repo_url: string;
  parsed_diff: ParsedDiff;
  roadmap_alignment_summary: string;
  potentially_unrelated_files: string[];
  discovered_tests: DiscoveredTest[];
  suggested_execution_plan?: TestExecutionPlan | null;
  review_findings: ReviewFinding[];
  regression_risks: RegressionRisk[];
  readiness: ReadinessAssessment;
  ai_status: 'complete' | 'unavailable_or_invalid';
  warnings: string[];
  evidence: IntelligenceEvidence;
  checked_at: string;
}

