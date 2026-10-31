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
