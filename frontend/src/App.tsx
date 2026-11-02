import { useState, useEffect } from 'react';
import {
  AnalyzeResponse,
  CandidateIssue,
  ContributorProfile,
  GuidedImplementationPlan,
  HealthData,
  IssueLearningBrief,
  PlanResponse,
} from './types';
import { InputForm } from './components/InputForm';
import { EvidenceLegend } from './components/EvidenceLegend';
import { IssueCard } from './components/IssueCard';
import { PlanModal } from './components/PlanModal';
import { LearnModal } from './components/LearnModal';
import { GuidedImplementationModal } from './components/GuidedImplementationModal';
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

  const [currentRepoUrl, setCurrentRepoUrl] = useState<string>('');
  const [currentProfile, setCurrentProfile] = useState<ContributorProfile | null>(null);
  const [currentDemo, setCurrentDemo] = useState<boolean>(false);

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
    } catch (err: any) {
      setLearnError(`Failed to generate learning brief for #${issue.number}: ${err.message}`);
    } finally {
      setLearningIssueId(null);
    }
  };

  const handleSelectGuided = async (issueNumber: number) => {
    if (!currentProfile || !currentRepoUrl) return;

    setGuidedIssueId(issueNumber);
    setGuidedError(null);

    try {
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
    } catch (err: any) {
      setGuidedError(`Failed to generate guided implementation for #${issueNumber}: ${err.message}`);
    } finally {
      setGuidedIssueId(null);
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
            </>
          )}
        </div>
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
        />
      )}

      {activeGuidedPlan && (
        <GuidedImplementationModal
          key={activeGuidedPlan.issue_number}
          plan={activeGuidedPlan}
          onClose={() => setActiveGuidedPlan(null)}
        />
      )}
    </div>
  );
}
