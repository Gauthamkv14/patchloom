import { useState, useEffect } from 'react';
import {
  AnalyzeResponse,
  CandidateIssue,
  ContributorProfile,
  GuidedImplementationPlan,
  HealthData,
  IssueLearningBrief,
  PlanResponse,
  TestExecutionPlan,
  TestExecutionResult,
  DraftPR,
  VerificationAnalysisReport,
} from './types';
import { learningHistoryStorage } from './storage/indexedDb';
import type { StepStatus } from './types/learningHistory';
import { InputForm } from './components/InputForm';
import { EvidenceLegend } from './components/EvidenceLegend';
import { IssueCard } from './components/IssueCard';
import { PlanModal } from './components/PlanModal';
import { LearnModal } from './components/LearnModal';
import { GuidedImplementationModal } from './components/GuidedImplementationModal';
import { VerificationModal } from './components/VerificationModal';
import { RepoIntelligenceView } from './components/RepoIntelligenceView';

export default function App() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [analysisResult, setAnalysisResult] = useState<AnalyzeResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const [planningIssueId, setPlanningIssueId] = useState<number | null>(null);
  const [activePlan, setActivePlan] = useState<PlanResponse | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);

  const [learningIssueId, setLearningIssueId] = useState<number | null>(null);
  const [activeLearningBrief, setActiveLearningBrief] = useState<IssueLearningBrief | null>(null);
  const [learnError, setLearnError] = useState<string | null>(null);

  const [guidedIssueId, setGuidedIssueId] = useState<number | null>(null);
  const [activeGuidedPlan, setActiveGuidedPlan] = useState<GuidedImplementationPlan | null>(null);
  const [guidedError, setGuidedError] = useState<string | null>(null);

  const [verifyingIssueId, setVerifyingIssueId] = useState<number | null>(null);
  const [activeVerificationReport, setActiveVerificationReport] = useState<VerificationAnalysisReport | null>(null);
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [isAnalyzingVerification, setIsAnalyzingVerification] = useState<boolean>(false);
  const [isExecutingTests, setIsExecutingTests] = useState<boolean>(false);
  const [testExecutionResult, setTestExecutionResult] = useState<TestExecutionResult | null>(null);
  const [isPreparingPR, setIsPreparingPR] = useState<boolean>(false);
  const [activeDraftPR, setActiveDraftPR] = useState<DraftPR | null>(null);

  const [currentRepoUrl, setCurrentRepoUrl] = useState<string>('');
  const [currentProfile, setCurrentProfile] = useState<ContributorProfile | null>(null);
  const [currentDemo, setCurrentDemo] = useState<boolean>(false);

  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [activeChecklistState, setActiveChecklistState] = useState<Record<string, boolean>>({});
  const [activeStepStatuses, setActiveStepStatuses] = useState<Record<string, StepStatus>>({});
  const [activeRevealedHints, setActiveRevealedHints] = useState<Record<string, boolean>>({});
  const [activeDiffText, setActiveDiffText] = useState<string>('');
  const [optInStoreDiff, setOptInStoreDiff] = useState<boolean>(false);
  const [quotaWarning, setQuotaWarning] = useState<string | null>(null);
  const [storageMode, setStorageMode] = useState<'indexeddb' | 'memory'>('indexeddb');
  const [storageWarning, setStorageWarning] = useState<string | null>(null);

  const checkQuota = async () => {
    try {
      const q = await learningHistoryStorage.checkStorageQuota();
      if (q.warning) {
        setQuotaWarning(q.message || 'Storage soft limit reached');
      } else {
        setQuotaWarning(null);
      }
    } catch {
      // Storage errors handled gracefully
    }
  };

  const getOrCreateSession = async (
    issueNumber: number,
    issueTitle: string,
    initialPillar: 'm2_learn' | 'm3_guided' | 'm4_verify',
  ) => {
    try {
      let session = await learningHistoryStorage.findActiveSession(currentRepoUrl, issueNumber, currentDemo);
      if (!session) {
        session = await learningHistoryStorage.createSession({
          repoUrl: currentRepoUrl,
          issueNumber,
          issueTitle,
          isDemo: currentDemo,
          profile: currentProfile,
          initialPillar,
        });
      }
      setCurrentSessionId(session.sessionId);

      // Restore checklist / steps / hints from prior session if present
      if (session.m2Snapshot?.checkedChecklistKeys) {
        setActiveChecklistState(session.m2Snapshot.checkedChecklistKeys);
      } else {
        setActiveChecklistState({});
      }

      if (session.m3Snapshot?.stepStatuses) {
        setActiveStepStatuses(session.m3Snapshot.stepStatuses);
      } else {
        setActiveStepStatuses({});
      }

      if (session.m3Snapshot?.revealedHints) {
        setActiveRevealedHints(session.m3Snapshot.revealedHints);
      } else {
        setActiveRevealedHints({});
      }

      // Restore M4 verification snapshot if present
      if (session.m4Snapshot?.report) {
        setActiveVerificationReport(session.m4Snapshot.report);
        setTestExecutionResult(session.m4Snapshot.testExecutionResult || null);
        setActiveDraftPR(session.m4Snapshot.draftPR || null);
        setActiveDiffText(session.m4Snapshot.rawDiffText || session.m4Snapshot.report.parsed_diff?.raw_diff_sample || '');
        setOptInStoreDiff(session.m4Snapshot.hasRawDiffStored || false);
      } else {
        setActiveDiffText('');
        setOptInStoreDiff(false);
      }

      return session;
    } catch (e) {
      console.warn('Storage operation failed, proceeding in stateless mode:', e);
      return null;
    }
  };

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        return res.json();
      })
      .then((data: HealthData) => {
        setHealth(data);
        setHealthLoading(false);
      })
      .catch((err: Error) => {
        setHealthError(err.message);
        setHealthLoading(false);
      });

    learningHistoryStorage
      .checkStorageStatus()
      .then((status) => {
        setStorageMode(status.mode);
        if (status.warning) {
          setStorageWarning(status.warning);
        }
      })
      .catch(() => {
        setStorageMode('memory');
        setStorageWarning('Local storage is unavailable. Session progress is temporary.');
      });
  }, []);

  const handleAnalyze = async (repoUrl: string, profile: ContributorProfile, isDemo: boolean) => {
    setAnalyzing(true);
    setAnalysisError(null);
    setAnalysisResult(null);
    setCurrentRepoUrl(repoUrl);
    setCurrentProfile(profile);
    setCurrentDemo(isDemo);

    try {
      const resp = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: repoUrl,
          profile,
          demo: isDemo,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }

      setAnalysisResult(data);
    } catch (err: any) {
      setAnalysisError(err.message || 'Failed to analyze repository');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleSelectPlan = async (issue: CandidateIssue) => {
    if (!currentProfile || !currentRepoUrl) return;

    setPlanningIssueId(issue.number);
    setPlanError(null);

    try {
      const resp = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: currentRepoUrl,
          issue_number: issue.number,
          profile: currentProfile,
          demo: currentDemo,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }

      setActivePlan(data);
    } catch (err: any) {
      setPlanError(`Failed to generate plan for #${issue.number}: ${err.message}`);
    } finally {
      setPlanningIssueId(null);
    }
  };

  const handleSelectLearn = async (issue: CandidateIssue) => {
    if (!currentProfile || !currentRepoUrl) return;

    setLearningIssueId(issue.number);
    setLearnError(null);

    try {
      const session = await getOrCreateSession(issue.number, issue.title, 'm2_learn');

      if (session?.m2Snapshot?.brief) {
        setActiveLearningBrief(session.m2Snapshot.brief);
        setActiveChecklistState(session.m2Snapshot.checkedChecklistKeys || {});
        return;
      }

      const resp = await fetch('/api/learn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: currentRepoUrl,
          issue_number: issue.number,
          profile: currentProfile,
          demo: currentDemo,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }

      setActiveLearningBrief(data);

      if (session) {
        await learningHistoryStorage.updateSessionM2Snapshot(session.sessionId, {
          brief: data,
          checkedChecklistKeys: {},
          completedChecklistCount: 0,
          totalChecklistCount: data.readiness_checklist?.length || 0,
          savedAt: new Date().toISOString(),
        });
        checkQuota();
      }
    } catch (err: any) {
      setLearnError(`Failed to generate learning brief for #${issue.number}: ${err.message}`);
    } finally {
      setLearningIssueId(null);
    }
  };

  const handleChecklistChange = async (checkedItems: Record<string, boolean>) => {
    setActiveChecklistState(checkedItems);
    if (currentSessionId && activeLearningBrief) {
      try {
        const completedCount = activeLearningBrief.readiness_checklist.filter((_, idx) => !!checkedItems[`chk-${idx}`]).length;
        await learningHistoryStorage.updateSessionM2Snapshot(currentSessionId, {
          brief: activeLearningBrief,
          checkedChecklistKeys: checkedItems,
          completedChecklistCount: completedCount,
          totalChecklistCount: activeLearningBrief.readiness_checklist.length,
          savedAt: new Date().toISOString(),
        });
        checkQuota();
      } catch (e) {
        console.warn('Failed to update M2 checklist state:', e);
      }
    }
  };

  const handleSelectGuided = async (issueNumber: number) => {
    if (!currentProfile || !currentRepoUrl) return;

    setGuidedIssueId(issueNumber);
    setGuidedError(null);

    try {
      const issueTitle =
        activeLearningBrief?.issue_number === issueNumber
          ? activeLearningBrief.issue_title
          : `Issue #${issueNumber}`;
      const session = await getOrCreateSession(issueNumber, issueTitle, 'm3_guided');

      if (session?.m3Snapshot?.plan) {
        setActiveGuidedPlan(session.m3Snapshot.plan);
        setActiveStepStatuses(session.m3Snapshot.stepStatuses || {});
        setActiveRevealedHints(session.m3Snapshot.revealedHints || {});
        return;
      }

      const resp = await fetch('/api/guided-implementation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: currentRepoUrl,
          issue_number: issueNumber,
          profile: currentProfile,
          demo: currentDemo,
          learning_brief: activeLearningBrief?.issue_number === issueNumber ? activeLearningBrief : null,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }

      setActiveGuidedPlan(data);

      if (session) {
        await learningHistoryStorage.updateSessionM3Snapshot(session.sessionId, {
          plan: data,
          activeStepIndex: 0,
          stepStatuses: {},
          revealedHints: {},
          expandedPatches: {},
          completedStepsCount: 0,
          totalStepsCount: data.steps?.length || 0,
          savedAt: new Date().toISOString(),
        });
        checkQuota();
      }
    } catch (err: any) {
      setGuidedError(`Failed to generate guided implementation for #${issueNumber}: ${err.message}`);
    } finally {
      setGuidedIssueId(null);
    }
  };

  const handleStepStatusesChange = async (statuses: Record<string, StepStatus>) => {
    setActiveStepStatuses(statuses);
    if (currentSessionId && activeGuidedPlan) {
      try {
        const completedCount = activeGuidedPlan.steps.filter((s) => statuses[s.id] === 'completed').length;
        await learningHistoryStorage.updateSessionM3Snapshot(currentSessionId, {
          plan: activeGuidedPlan,
          activeStepIndex: 0,
          stepStatuses: statuses,
          revealedHints: activeRevealedHints,
          expandedPatches: {},
          completedStepsCount: completedCount,
          totalStepsCount: activeGuidedPlan.steps.length,
          savedAt: new Date().toISOString(),
        });
        checkQuota();
      } catch (e) {
        console.warn('Failed to update step statuses:', e);
      }
    }
  };

  const handleRevealedHintsChange = async (hints: Record<string, boolean>) => {
    setActiveRevealedHints(hints);
    if (currentSessionId && activeGuidedPlan) {
      try {
        const completedCount = activeGuidedPlan.steps.filter((s) => activeStepStatuses[s.id] === 'completed').length;
        await learningHistoryStorage.updateSessionM3Snapshot(currentSessionId, {
          plan: activeGuidedPlan,
          activeStepIndex: 0,
          stepStatuses: activeStepStatuses,
          revealedHints: hints,
          expandedPatches: {},
          completedStepsCount: completedCount,
          totalStepsCount: activeGuidedPlan.steps.length,
          savedAt: new Date().toISOString(),
        });
        checkQuota();
      } catch (e) {
        console.warn('Failed to update revealed hints:', e);
      }
    }
  };

  const handleSelectVerify = async (issueNumber: number, customDiff?: string) => {
    if (!currentRepoUrl) return;

    setVerifyingIssueId(issueNumber);
    setVerificationError(null);

    try {
      const issueTitle =
        activeGuidedPlan?.issue_number === issueNumber
          ? activeGuidedPlan.issue_title
          : activeLearningBrief?.issue_number === issueNumber
          ? activeLearningBrief.issue_title
          : `Issue #${issueNumber}`;

      const session = await getOrCreateSession(issueNumber, issueTitle, 'm4_verify');

      // Genuinely restore existing verification snapshot if available and no custom diff passed
      if (!customDiff && session?.m4Snapshot?.report) {
        setActiveVerificationReport(session.m4Snapshot.report);
        setTestExecutionResult(session.m4Snapshot.testExecutionResult || null);
        setActiveDraftPR(session.m4Snapshot.draftPR || null);
        setActiveDiffText(session.m4Snapshot.rawDiffText || session.m4Snapshot.report.parsed_diff?.raw_diff_sample || '');
        setOptInStoreDiff(session.m4Snapshot.hasRawDiffStored || false);
        return;
      }

      setIsAnalyzingVerification(true);

      const resp = await fetch('/api/verification/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: currentRepoUrl,
          issue_number: issueNumber,
          diff_text: customDiff || '',
          profile: currentProfile,
          demo: currentDemo,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }

      setActiveVerificationReport(data);
      // Reset execution & draft PR on fresh verification report
      setTestExecutionResult(null);
      setActiveDraftPR(null);
      setActiveDiffText(customDiff || data.parsed_diff?.raw_diff_sample || '');

      if (session) {
        await learningHistoryStorage.updateSessionM4Snapshot(
          session.sessionId,
          {
            report: data,
            hasRawDiffStored: optInStoreDiff,
            rawDiffText: optInStoreDiff ? (customDiff || data.parsed_diff?.raw_diff_sample || '') : undefined,
            testExecutionResult: null,
            draftPR: null,
            savedAt: new Date().toISOString(),
          },
          optInStoreDiff,
        );
        checkQuota();
      }
    } catch (err: any) {
      setVerificationError(`Failed to verify changes for #${issueNumber}: ${err.message}`);
    } finally {
      setVerifyingIssueId(null);
      setIsAnalyzingVerification(false);
    }
  };

  const handleReAnalyzeDiff = async (diffText: string, optIn?: boolean) => {
    if (!activeVerificationReport || !currentRepoUrl) return;
    setIsAnalyzingVerification(true);
    const saveDiff = optIn !== undefined ? optIn : optInStoreDiff;
    try {
      const resp = await fetch('/api/verification/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: currentRepoUrl,
          issue_number: activeVerificationReport.issue_number,
          diff_text: diffText,
          profile: currentProfile,
          demo: currentDemo,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }

      setActiveVerificationReport(data);
      setActiveDiffText(diffText);
      setOptInStoreDiff(saveDiff);

      if (currentSessionId) {
        await learningHistoryStorage.updateSessionM4Snapshot(
          currentSessionId,
          {
            report: data,
            hasRawDiffStored: saveDiff,
            rawDiffText: saveDiff ? diffText : undefined,
            testExecutionResult,
            draftPR: activeDraftPR,
            savedAt: new Date().toISOString(),
          },
          saveDiff,
        );
        checkQuota();
      }
    } catch (err: any) {
      setVerificationError(`Failed to re-analyze diff: ${err.message}`);
    } finally {
      setIsAnalyzingVerification(false);
    }
  };

  const handleOptInStoreDiffChange = async (optIn: boolean, currentDiff: string) => {
    setOptInStoreDiff(optIn);
    setActiveDiffText(currentDiff);
    if (currentSessionId && activeVerificationReport) {
      try {
        await learningHistoryStorage.updateSessionM4Snapshot(
          currentSessionId,
          {
            report: activeVerificationReport,
            hasRawDiffStored: optIn,
            rawDiffText: optIn ? currentDiff : undefined,
            testExecutionResult,
            draftPR: activeDraftPR,
            savedAt: new Date().toISOString(),
          },
          optIn,
        );
        checkQuota();
      } catch (e) {
        console.warn('Failed to update diff opt-in preference:', e);
      }
    }
  };

  const handleExecuteTestPlan = async (
    plan: TestExecutionPlan,
    diffText: string,
    authorized: boolean,
  ) => {
    if (!activeVerificationReport || !currentRepoUrl) return;
    setIsExecutingTests(true);
    try {
      const resp = await fetch('/api/verification/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: currentRepoUrl,
          issue_number: activeVerificationReport.issue_number,
          execution_plan: plan,
          diff_text: diffText,
          authorized,
          demo: currentDemo,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }

      setTestExecutionResult(data);
      if (currentSessionId && activeVerificationReport) {
        await learningHistoryStorage.updateSessionM4Snapshot(
          currentSessionId,
          {
            report: activeVerificationReport,
            hasRawDiffStored: optInStoreDiff,
            rawDiffText: optInStoreDiff ? diffText : undefined,
            testExecutionResult: data,
            draftPR: activeDraftPR,
            savedAt: new Date().toISOString(),
          },
          optInStoreDiff,
        );
        checkQuota();
      }
    } catch (err: any) {
      setVerificationError(`Test execution error: ${err.message}`);
    } finally {
      setIsExecutingTests(false);
    }
  };

  const handlePrepareDraftPR = async (diffText: string) => {
    if (!activeVerificationReport || !currentRepoUrl) return;
    setIsPreparingPR(true);
    try {
      const resp = await fetch('/api/verification/prepare-pr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: currentRepoUrl,
          issue_number: activeVerificationReport.issue_number,
          diff_text: diffText,
          profile: currentProfile,
          execution_result: testExecutionResult,
          review_findings: activeVerificationReport.review_findings,
          regression_risks: activeVerificationReport.regression_risks,
          readiness: activeVerificationReport.readiness,
          demo: currentDemo,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }

      setActiveDraftPR(data);
      if (currentSessionId && activeVerificationReport) {
        await learningHistoryStorage.updateSessionM4Snapshot(
          currentSessionId,
          {
            report: activeVerificationReport,
            hasRawDiffStored: optInStoreDiff,
            rawDiffText: optInStoreDiff ? diffText : undefined,
            testExecutionResult: testExecutionResult,
            draftPR: data,
            savedAt: new Date().toISOString(),
          },
          optInStoreDiff,
        );
        checkQuota();
      }
    } catch (err: any) {
      setVerificationError(`Failed to prepare draft PR: ${err.message}`);
    } finally {
      setIsPreparingPR(false);
    }
  };

  return (
    <div className="container">
      <header>
        <div className="brand">
          <h1>PatchLoom</h1>
          <span className="badge badge-verified">Hacktoberfest MVP</span>
        </div>
        <p className="tagline">From &apos;I want to contribute&apos; to a repo-grounded plan for a first PR.</p>

        <div className="status-bar">
          <span className={`status-dot ${health?.status === 'ok' ? 'active' : 'inactive'}`} />
          <span>
            <strong>System:</strong>{' '}
            {healthLoading ? 'Connecting...' : healthError ? `Unavailable (${healthError})` : 'Online'}
          </span>
          {health && (
            <>
              <span>•</span>
              <span><strong>Mode:</strong> {health.demo_mode ? 'Fixture/Demo' : 'Live API'}</span>
              <span>•</span>
              <span><strong>GitHub Token:</strong> {health.has_github_token ? 'Configured' : 'Missing (60 req/hr limit)'}</span>
              <span>•</span>
              <span><strong>Gemini Key:</strong> {health.has_gemini_key ? 'Configured (Gemma 4)' : 'Missing (Deterministic only)'}</span>
              <span>•</span>
              <span><strong>Storage:</strong> {storageMode === 'indexeddb' ? 'IndexedDB (Persistent)' : 'In-Memory (Temporary)'}</span>
            </>
          )}
        </div>
        {storageWarning && (
          <div className="alert alert-warning" style={{ marginTop: '0.75rem', padding: '0.5rem 1rem', borderRadius: '4px', background: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca', fontSize: '0.85rem' }}>
            <span>⚠️ <strong>Storage Warning:</strong> {storageWarning}</span>
          </div>
        )}
        {quotaWarning && (
          <div className="alert alert-warning" style={{ marginTop: '0.75rem', padding: '0.5rem 1rem', borderRadius: '4px', background: '#fef3c7', color: '#92400e', border: '1px solid #fde68a', fontSize: '0.85rem' }}>
            <span>⚠️ <strong>Storage notice:</strong> {quotaWarning}</span>
          </div>
        )}
      </header>

      <main>
        <InputForm onSubmit={handleAnalyze} isLoading={analyzing} />

        {analysisError && (
          <div className="error-banner">
            <strong>Error:</strong> {analysisError}
          </div>
        )}

        {planError && (
          <div className="error-banner">
            <strong>Planning Error:</strong> {planError}
          </div>
        )}

        {learnError && (
          <div className="error-banner">
            <strong>Learning Error:</strong> {learnError}
          </div>
        )}

        {guidedError && (
          <div className="error-banner">
            <strong>Guided Implementation Error:</strong> {guidedError}
          </div>
        )}

        {verificationError && (
          <div className="error-banner">
            <strong>Verification Error:</strong> {verificationError}
          </div>
        )}

        {analyzing && (
          <div className="loading-container">
            <div className="spinner" />
            <p>Analyzing repository metadata, computing viability signals, and scoring fit with Gemma 4...</p>
          </div>
        )}

        {analysisResult && (
          <div className="results-container">
            {(currentDemo || analysisResult.warnings.some((w) => w.includes('Demo/Fixture mode'))) && (
              <div className="demo-banner">
                <strong>Demo / Fixture Mode Active:</strong> Displaying offline repository snapshot data. Zero external GitHub or Gemini API network calls made.
              </div>
            )}
            <div className="card repo-overview-card">
              <div className="repo-header-row">
                <div>
                  <h2>
                    {analysisResult.repo.owner}/{analysisResult.repo.name}
                  </h2>
                  <p className="repo-desc">{analysisResult.repo.description || 'No description provided'}</p>
                </div>
                <div className="repo-stats-row">
                  <span className="stat-pill">Default Branch: {analysisResult.repo.default_branch}</span>
                  <span className="stat-pill">Open Issues: {analysisResult.repo.open_issues_count}</span>
                  <span className="stat-pill">Model: {analysisResult.actual_model}</span>
                  <span className={`stat-pill status-${analysisResult.ai_status}`}>
                    AI Status: {analysisResult.ai_status}
                  </span>
                </div>
              </div>

              {analysisResult.warnings && analysisResult.warnings.length > 0 && (
                <div className="warning-banner" style={{ marginTop: '1rem' }}>
                  {analysisResult.warnings.map((w, idx) => (
                    <p key={idx}>⚠️ {w}</p>
                  ))}
                </div>
              )}
            </div>

            {analysisResult.intelligence && (
              <RepoIntelligenceView intelligence={analysisResult.intelligence} />
            )}

            <EvidenceLegend />

            <div className="candidates-section">
              <div className="section-title-row">
                <h3>Recommended Candidate Issues ({analysisResult.issues.length})</h3>
                <span className="field-hint">Filtered and ranked by contributor fit & deterministic viability</span>
              </div>

              {analysisResult.issues.length === 0 ? (
                <div className="card empty-card">
                  <p>No open issues met the viability thresholds for this repository.</p>
                </div>
              ) : (
                <div className="issues-list">
                  {analysisResult.issues.map((issue, idx) => (
                    <IssueCard
                      key={issue.number}
                      issue={issue}
                      rank={idx + 1}
                      onSelectPlan={handleSelectPlan}
                      isPlanningThis={planningIssueId === issue.number}
                      onSelectLearn={handleSelectLearn}
                      isLearningThis={learningIssueId === issue.number}
                      onSelectGuided={(issue) => handleSelectGuided(issue.number)}
                      isGuidingThis={guidedIssueId === issue.number}
                      onSelectVerify={(issue) => handleSelectVerify(issue.number)}
                      isVerifyingThis={verifyingIssueId === issue.number}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {activePlan && (
        <PlanModal plan={activePlan} onClose={() => setActivePlan(null)} />
      )}

      {activeLearningBrief && (
        <LearnModal
          key={activeLearningBrief.issue_number}
          brief={activeLearningBrief}
          onClose={() => setActiveLearningBrief(null)}
          onStartGuidedImplementation={handleSelectGuided}
          initialCheckedItems={activeChecklistState}
          onChecklistChange={handleChecklistChange}
        />
      )}

      {activeGuidedPlan && (
        <GuidedImplementationModal
          key={activeGuidedPlan.issue_number}
          plan={activeGuidedPlan}
          onClose={() => setActiveGuidedPlan(null)}
          onOpenVerification={handleSelectVerify}
          initialStepStatuses={activeStepStatuses}
          initialRevealedHints={activeRevealedHints}
          onStepStatusesChange={handleStepStatusesChange}
          onRevealedHintsChange={handleRevealedHintsChange}
        />
      )}

      {activeVerificationReport && (
        <VerificationModal
          key={activeVerificationReport.issue_number}
          report={activeVerificationReport}
          onClose={() => setActiveVerificationReport(null)}
          onReAnalyzeDiff={handleReAnalyzeDiff}
          isAnalyzingDiff={isAnalyzingVerification}
          onExecuteTestPlan={handleExecuteTestPlan}
          isExecutingTests={isExecutingTests}
          executionResult={testExecutionResult}
          onPrepareDraftPR={handlePrepareDraftPR}
          isPreparingPR={isPreparingPR}
          draftPR={activeDraftPR}
          initialDiff={activeDiffText}
          initialOptInStoreDiff={optInStoreDiff}
          onOptInStoreDiffChange={handleOptInStoreDiffChange}
        />
      )}
    </div>
  );
}
