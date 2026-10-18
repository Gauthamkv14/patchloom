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
  has_ci: boolean;
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
}

export interface AnalyzeResponse {
  repo: RepoMetadata;
  provider: string;
  actual_model: string;
  ai_status: 'complete' | 'partial' | 'unavailable_or_invalid';
  issues: CandidateIssue[];
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
