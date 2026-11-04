import type {
  ContributorProfile,
  DraftPR,
  GuidedImplementationPlan,
  IssueLearningBrief,
  TestExecutionResult,
  VerificationAnalysisReport,
} from '../types.ts';

export const CURRENT_SCHEMA_VERSION = 1;
export const SOFT_SESSION_LIMIT = 50;
export const MAX_IMPORT_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB

export type PillarType = 'm2_learn' | 'm3_guided' | 'm4_verify';
export type SessionStatus = 'active' | 'completed' | 'abandoned';
export type StepStatus = 'not_started' | 'in_progress' | 'understood' | 'completed';

export interface M2LearningSnapshot {
  brief: IssueLearningBrief;
  checkedChecklistKeys: Record<string, boolean>;
  completedChecklistCount: number;
  totalChecklistCount: number;
  savedAt: string;
}

export interface M3GuidedSnapshot {
  plan: GuidedImplementationPlan;
  activeStepIndex: number;
  stepStatuses: Record<string, StepStatus>;
  revealedHints: Record<string, boolean>;
  expandedPatches: Record<string, boolean>;
  completedStepsCount: number;
  totalStepsCount: number;
  savedAt: string;
}

export interface M4VerificationSnapshot {
  report: VerificationAnalysisReport;
  hasRawDiffStored: boolean;
  rawDiffText?: string;
  testExecutionResult?: TestExecutionResult | null;
  draftPR?: DraftPR | null;
  savedAt: string;
}

export interface SessionLearningMetrics {
  encounteredConcepts: string[];
  practicedConcepts: string[];
  userMarkedUnderstanding: string[];
  completedSteps: string[];
  filesTouched: string[];
}

export interface LearningSessionRecord {
  sessionId: string; // UUID
  schemaVersion: number;
  repoUrl: string;
  repoOwner: string;
  repoName: string;
  issueNumber: number;
  issueTitle: string;
  isDemo: boolean;
  status: SessionStatus;
  startedAt: string;
  lastUpdatedAt: string;
  lastActivePillar: PillarType;
  contributorProfile?: ContributorProfile | null;
  m2Snapshot?: M2LearningSnapshot | null;
  m3Snapshot?: M3GuidedSnapshot | null;
  m4Snapshot?: M4VerificationSnapshot | null;
  metrics: SessionLearningMetrics;
}

export interface ContributorGrowthProfile {
  profileVersion: number;
  isDemo: boolean;
  totalSessions: number;
  completedSessions: number;
  activeSessions: number;
  distinctRepositories: string[];
  encounteredConceptsCount: number;
  practicedConceptsCount: number;
  userMarkedUnderstandingCount: number;
  completedStepsCount: number;
  conceptsEncountered: Record<string, number>;
  conceptsPracticed: Record<string, number>;
  lastCalculatedAt: string;
}

export interface StorageQuotaInfo {
  count: number;
  softLimit: number;
  warning: boolean;
  message?: string;
}

export interface StorageExportPayload {
  format: 'patchloom_learning_history';
  version: number;
  exportedAt: string;
  sessionCount: number;
  sessions: LearningSessionRecord[];
  growthProfile?: ContributorGrowthProfile | null;
}

export interface ImportResult {
  success: boolean;
  importedSessionsCount: number;
  skippedSessionsCount: number;
  errors: string[];
}

export interface CreateSessionParams {
  repoUrl: string;
  issueNumber: number;
  issueTitle: string;
  isDemo: boolean;
  profile?: ContributorProfile | null;
  initialPillar?: PillarType;
}

export interface SessionFilter {
  isDemo?: boolean;
  repoUrl?: string;
  issueNumber?: number;
  status?: SessionStatus;
}
