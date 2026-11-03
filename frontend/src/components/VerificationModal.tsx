import React, { useState } from 'react';
import {
  DraftPR,
  TestExecutionPlan,
  TestExecutionResult,
  VerificationAnalysisReport,
} from '../types';

interface VerificationModalProps {
  report: VerificationAnalysisReport;
  onClose: () => void;
  onReAnalyzeDiff: (diffText: string) => Promise<void>;
  isAnalyzingDiff: boolean;
  onExecuteTestPlan: (plan: TestExecutionPlan, diffText: string, authorized: boolean) => Promise<void>;
  isExecutingTests: boolean;
  executionResult: TestExecutionResult | null;
  onPrepareDraftPR: (diffText: string) => Promise<void>;
  isPreparingPR: boolean;
  draftPR: DraftPR | null;
}

type TabType = 'diff' | 'tests' | 'review' | 'readiness' | 'draft_pr';

export const VerificationModal: React.FC<VerificationModalProps> = ({
  report,
  onClose,
  onReAnalyzeDiff,
  isAnalyzingDiff,
  onExecuteTestPlan,
  isExecutingTests,
  executionResult,
  onPrepareDraftPR,
  isPreparingPR,
  draftPR,
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('diff');
  const [diffInput, setDiffInput] = useState<string>(report.parsed_diff.raw_diff_sample || '');
  const [authorizedExecution, setAuthorizedExecution] = useState<boolean>(false);
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [copiedSummary, setCopiedSummary] = useState<boolean>(false);
  const [copiedPR, setCopiedPR] = useState<boolean>(false);

  const getSeverityBadgeClass = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 'badge-critical';
      case 'high':
        return 'badge-high';
      case 'medium':
        return 'badge-medium';
      case 'low':
        return 'badge-low';
      default:
        return 'badge-info';
    }
  };

  const getReadinessBadgeClass = (status: string) => {
    switch (status) {
      case 'ready_for_review':
        return 'badge-status-ready';
      case 'needs_attention':
        return 'badge-status-attention';
      case 'insufficient_evidence':
      default:
        return 'badge-status-unknown';
    }
  };

  const getExecutionStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'passed':
        return 'badge-status-ready';
      case 'failed':
      case 'timed_out':
        return 'badge-critical';
      case 'execution_unavailable':
      case 'invalid_or_unsupported':
      default:
        return 'badge-status-attention';
    }
  };

  const filteredFindings = report.review_findings.filter((f) => {
    if (selectedSeverity === 'all') return true;
    return f.severity.toLowerCase() === selectedSeverity.toLowerCase();
  });

  const handleRunTests = () => {
    if (!report.suggested_execution_plan) return;
    onExecuteTestPlan(report.suggested_execution_plan, diffInput, authorizedExecution);
  };

  const handleCopySummary = () => {
    const summaryLines = [
      `PatchLoom Verification & Review Report: #${report.issue_number} - ${report.issue_title}`,
      `Readiness: ${report.readiness.status.replace(/_/g, ' ').toUpperCase()}`,
      `Changes: ${report.parsed_diff.total_files} file(s) (+${report.parsed_diff.lines_added}/-${report.parsed_diff.lines_removed})`,
      `Roadmap Alignment: ${report.roadmap_alignment_summary}`,
      `Review Findings: ${report.review_findings.length} item(s)`,
      `Regression Risks: ${report.regression_risks.length} item(s)`,
    ];
    navigator.clipboard.writeText(summaryLines.join('\n'));
    setCopiedSummary(true);
    setTimeout(() => setCopiedSummary(false), 2500);
  };

  const handleCopyPR = () => {
    if (!draftPR) return;
    const prLines = [
      `## ${draftPR.title}`,
      '',
      '### Summary of Changes',
      draftPR.summary_of_changes,
      '',
      '### Problem Addressed',
      draftPR.problem_addressed,
      '',
      '### Implementation Overview',
      draftPR.implementation_overview,
      '',
      '### Tests Performed',
      `* Executed & Passed: ${draftPR.tests_performed.executed_and_passed?.join(', ') || 'None'}`,
      `* Executed & Failed: ${draftPR.tests_performed.executed_and_failed?.join(', ') || 'None'}`,
      `* Not Executed / Unverified: ${draftPR.tests_performed.not_executed?.join(', ') || 'None'}`,
      `* Manually Verified: ${draftPR.tests_performed.manually_verified?.join(', ') || 'None'}`,
      '',
      '### Manual Checklist',
      ...draftPR.manual_verification_checklist.map((c) => `- [ ] ${c}`),
    ];
    navigator.clipboard.writeText(prLines.join('\n'));
    setCopiedPR(true);
    setTimeout(() => setCopiedPR(false), 2500);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content verification-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title-area">
            <span className="badge badge-verified">VERIFY &amp; CONTRIBUTE</span>
            <h2>
              Verification &amp; Review — #{report.issue_number}: {report.issue_title}
            </h2>
            <div className="modal-meta-row">
              <a
                href={report.repo_url}
                target="_blank"
                rel="noopener noreferrer"
                className="external-link"
              >
                View Repository ↗
              </a>
              <span className="meta-separator">•</span>
              <span className={`badge ${getReadinessBadgeClass(report.readiness.status)}`}>
                Readiness: {report.readiness.status.replace(/_/g, ' ')}
              </span>
              <span className="meta-separator">•</span>
              <span className="badge badge-inference">
                {report.ai_status === 'complete' ? 'AI Review Complete' : 'Deterministic Analysis'}
              </span>
            </div>
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="modal-tabs">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'diff' ? 'active' : ''}`}
            onClick={() => setActiveTab('diff')}
          >
            📝 Diff &amp; Changes ({report.parsed_diff.total_files})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'tests' ? 'active' : ''}`}
            onClick={() => setActiveTab('tests')}
          >
            🧪 Tests &amp; Runner ({report.discovered_tests.length})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'review' ? 'active' : ''}`}
            onClick={() => setActiveTab('review')}
          >
            🔍 Review Findings ({report.review_findings.length})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'readiness' ? 'active' : ''}`}
            onClick={() => setActiveTab('readiness')}
          >
            📊 Regression &amp; Readiness
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'draft_pr' ? 'active' : ''}`}
            onClick={() => setActiveTab('draft_pr')}
          >
            📋 Draft PR
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {/* TAB 1: DIFF & CHANGES */}
          {activeTab === 'diff' && (
            <div className="tab-pane">
              <div className="diff-stats-bar">
                <div className="diff-stat-item">
                  <strong>{report.parsed_diff.total_files}</strong> modified files
                </div>
                <div className="diff-stat-item stat-added">
                  <strong>+{report.parsed_diff.lines_added}</strong> lines added
                </div>
                <div className="diff-stat-item stat-removed">
                  <strong>-{report.parsed_diff.lines_removed}</strong> lines removed
                </div>
              </div>

              {/* Roadmap Alignment Box */}
              <div className="alignment-notice-box">
                <h4>Roadmap Step Alignment</h4>
                <p>{report.roadmap_alignment_summary}</p>
                {report.potentially_unrelated_files.length > 0 && (
                  <div className="unrelated-files-alert">
                    <strong>⚠️ Potentially Unrelated Files:</strong>
                    <ul>
                      {report.potentially_unrelated_files.map((uf, i) => (
                        <li key={i}><code>{uf}</code> (not mentioned in planned steps)</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Touched Files List */}
              <div className="diff-files-section">
                <h4>Modified Files</h4>
                <div className="diff-files-list">
                  {report.parsed_diff.files.map((file, idx) => (
                    <div key={idx} className="diff-file-card">
                      <div className="file-header">
                        <span className={`change-badge change-${file.change_type}`}>
                          {file.change_type}
                        </span>
                        <code className="file-path">{file.path}</code>
                        <span className="file-lines">
                          +{file.lines_added} / -{file.lines_removed}
                        </span>
                      </div>
                      {file.detected_symbols.length > 0 && (
                        <div className="detected-symbols">
                          <span>Symbols Defined:</span>
                          {file.detected_symbols.map((sym, sIdx) => (
                            <code key={sIdx} className="symbol-pill">{sym}</code>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Diff Input / Editor for verification */}
              <div className="diff-editor-section">
                <h4>Git Diff Input</h4>
                <p className="diff-editor-hint">
                  Paste or update your unified git diff (e.g. <code>git diff origin/main</code>) up to 100KB to re-evaluate roadmap alignment, tests, and findings.
                </p>
                <textarea
                  className="diff-textarea"
                  rows={8}
                  value={diffInput}
                  onChange={(e) => setDiffInput(e.target.value)}
                  placeholder="Paste git diff here..."
                />
                <div className="diff-editor-actions">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => onReAnalyzeDiff(diffInput)}
                    disabled={isAnalyzingDiff}
                  >
                    {isAnalyzingDiff ? 'Analyzing Diff...' : '🔄 Re-Analyze Diff'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: TESTS & ISOLATED RUNNER */}
          {activeTab === 'tests' && (
            <div className="tab-pane">
              {/* Isolated Docker Environment Disclaimer */}
              <div className="isolation-notice-banner">
                <h4>🔒 Disposable Test Isolation Boundary</h4>
                <p>
                  Tests execute exclusively within temporary, network-disabled (<code>--network none</code>) Docker containers with dropped capabilities (<code>--cap-drop ALL</code>), CPU limits (1.0 core), memory limits (512MB), and a non-root user. Execution is never performed on the host.
                </p>
              </div>

              {/* Suggested Execution Plan */}
              {report.suggested_execution_plan ? (
                <div className="execution-plan-box">
                  <h4>Recommended Test Execution Plan</h4>
                  <div className="plan-details-grid">
                    <div><strong>Test Runner:</strong> <code>{report.suggested_execution_plan.test_runner}</code></div>
                    <div><strong>Command:</strong> <code>{report.suggested_execution_plan.command} {report.suggested_execution_plan.arguments.join(' ')}</code></div>
                    <div><strong>Timeout:</strong> {report.suggested_execution_plan.timeout_seconds}s</div>
                    <div><strong>Allowlisted:</strong> {report.suggested_execution_plan.is_allowlisted ? '✓ Yes' : '✗ No'}</div>
                  </div>

                  {/* Explicit Contributor Authorization Checkbox */}
                  <div className="authorization-row">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={authorizedExecution}
                        onChange={(e) => setAuthorizedExecution(e.target.checked)}
                      />
                      <span>
                        I explicitly authorize running this test command in a disposable, isolated container.
                      </span>
                    </label>
                  </div>

                  <button
                    type="button"
                    className="btn-primary run-tests-btn"
                    onClick={handleRunTests}
                    disabled={!authorizedExecution || isExecutingTests}
                  >
                    {isExecutingTests ? 'Executing in Container...' : '▶ Run Isolated Tests'}
                  </button>
                </div>
              ) : (
                <div className="empty-state-box">
                  No automated test command could be safely discovered for this repository.
                </div>
              )}

              {/* Execution Result Card */}
              {executionResult && (
                <div className="execution-result-card">
                  <div className="result-header">
                    <h4>Execution Result</h4>
                    <span className={`badge ${getExecutionStatusBadgeClass(executionResult.status)}`}>
                      {executionResult.status.toUpperCase()}
                    </span>
                    <span className="result-meta">
                      Exit Code: {executionResult.exit_code} • {executionResult.duration_seconds.toFixed(2)}s
                      {executionResult.simulated && ' (Simulated)'}
                    </span>
                  </div>

                  {(executionResult.tests_total !== null && executionResult.tests_total !== undefined) && (
                    <div className="result-counts-bar">
                      <span>Total: <strong>{executionResult.tests_total}</strong></span>
                      <span className="stat-added">Passed: <strong>{executionResult.tests_passed || 0}</strong></span>
                      <span className="stat-removed">Failed: <strong>{executionResult.tests_failed || 0}</strong></span>
                      {executionResult.tests_skipped ? (
                        <span>Skipped: <strong>{executionResult.tests_skipped}</strong></span>
                      ) : null}
                    </div>
                  )}

                  {executionResult.failure_details.length > 0 && (
                    <div className="failure-details-box">
                      <strong>Failure Details:</strong>
                      <ul>
                        {executionResult.failure_details.map((f, i) => (
                          <li key={i}>{f}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {executionResult.stdout_bounded && (
                    <div className="output-box">
                      <div className="output-label">Standard Output:</div>
                      <pre><code>{executionResult.stdout_bounded}</code></pre>
                    </div>
                  )}

                  {executionResult.stderr_bounded && (
                    <div className="output-box output-stderr">
                      <div className="output-label">Standard Error / Diagnostics:</div>
                      <pre><code>{executionResult.stderr_bounded}</code></pre>
                    </div>
                  )}
                </div>
              )}

              {/* Discovered Tests Table */}
              <div className="discovered-tests-section">
                <h4>Discovered Relevant Tests ({report.discovered_tests.length})</h4>
                <div className="tests-list">
                  {report.discovered_tests.map((test, idx) => (
                    <div key={idx} className="test-item-card">
                      <div className="test-item-header">
                        <code className="test-file-path">{test.test_file}</code>
                        <span className="badge badge-verified">{test.framework}</span>
                        <span className="confidence-pill">Confidence: {test.confidence}</span>
                      </div>
                      <p className="test-rationale"><strong>Rationale:</strong> {test.selection_rationale}</p>
                      <div className="test-cmd-row">
                        <span>Command:</span> <code>{test.test_command}</code>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: REVIEW FINDINGS */}
          {activeTab === 'review' && (
            <div className="tab-pane">
              {/* Severity Filter */}
              <div className="filter-row">
                <span className="filter-label">Filter by Severity:</span>
                {['all', 'critical', 'high', 'medium', 'low', 'informational'].map((sev) => (
                  <button
                    key={sev}
                    type="button"
                    className={`filter-btn ${selectedSeverity === sev ? 'active' : ''}`}
                    onClick={() => setSelectedSeverity(sev)}
                  >
                    {sev.charAt(0).toUpperCase() + sev.slice(1)}
                  </button>
                ))}
              </div>

              {filteredFindings.length === 0 ? (
                <div className="empty-state-box">
                  No review findings match the selected filter.
                </div>
              ) : (
                <div className="findings-list">
                  {filteredFindings.map((finding) => (
                    <div key={finding.finding_id} className="finding-card">
                      <div className="finding-header">
                        <span className={`badge ${getSeverityBadgeClass(finding.severity)}`}>
                          {finding.severity.toUpperCase()}
                        </span>
                        <span className="category-tag">{finding.category.replace(/_/g, ' ')}</span>
                        <h4 className="finding-title">{finding.title}</h4>
                      </div>

                      <div className="finding-location">
                        <code>{finding.file_path}</code>
                        {finding.line_range && <span> (Lines {finding.line_range})</span>}
                      </div>

                      <p className="finding-explanation">{finding.explanation}</p>

                      <div className="finding-evidence-box">
                        <strong>Evidence:</strong> {finding.evidence}
                      </div>

                      <div className="finding-why-box">
                        <strong>Why it matters:</strong> {finding.why_it_matters}
                      </div>

                      <div className="finding-action-box">
                        <strong>Suggested Action:</strong> {finding.suggested_action}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 4: REGRESSION & READINESS */}
          {activeTab === 'readiness' && (
            <div className="tab-pane">
              {/* Readiness Assessment Card */}
              <div className="readiness-summary-card">
                <div className="readiness-header">
                  <h3>Contribution Readiness Assessment</h3>
                  <span className={`badge ${getReadinessBadgeClass(report.readiness.status)}`}>
                    {report.readiness.status.replace(/_/g, ' ').toUpperCase()}
                  </span>
                </div>
                <p className="readiness-summary-text">{report.readiness.summary}</p>

                {/* Readiness Checklist Status */}
                <div className="checklist-grid">
                  <div className={`check-item ${report.readiness.checklist_status.diff_parsed ? 'checked' : ''}`}>
                    {report.readiness.checklist_status.diff_parsed ? '✓' : '✗'} Diff parsed &amp; bounded
                  </div>
                  <div className={`check-item ${report.readiness.checklist_status.tests_discovered ? 'checked' : ''}`}>
                    {report.readiness.checklist_status.tests_discovered ? '✓' : '✗'} Candidate tests discovered
                  </div>
                  <div className={`check-item ${report.readiness.checklist_status.tests_executed ? 'checked' : ''}`}>
                    {report.readiness.checklist_status.tests_executed ? '✓' : '○'} Tests executed &amp; passed
                  </div>
                  <div className={`check-item ${report.readiness.checklist_status.review_findings_resolved ? 'checked' : ''}`}>
                    {report.readiness.checklist_status.review_findings_resolved ? '✓' : '○'} Critical findings resolved
                  </div>
                </div>

                {report.readiness.outstanding_items.length > 0 && (
                  <div className="outstanding-items-box">
                    <h4>Outstanding Items:</h4>
                    <ul>
                      {report.readiness.outstanding_items.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Regression Risks Section */}
              <div className="regression-section">
                <h4>Potential Regression Risks ({report.regression_risks.length})</h4>
                <div className="regression-list">
                  {report.regression_risks.map((risk) => (
                    <div key={risk.risk_id} className="risk-item-card">
                      <div className="risk-header">
                        <code>{risk.affected_module_or_file}</code>
                        <span className="badge badge-inference">{risk.risk_type.replace(/_/g, ' ')}</span>
                        <span className="confidence-pill">Confidence: {risk.confidence}</span>
                      </div>
                      <p><strong>Impact:</strong> {risk.potential_impact}</p>
                      <p><strong>Evidence:</strong> {risk.evidence}</p>
                      <div className="suggested-check">
                        <strong>Verification:</strong> {risk.suggested_verification}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: DRAFT PR */}
          {activeTab === 'draft_pr' && (
            <div className="tab-pane">
              <div className="pr-intro-bar">
                <p>
                  Generate a maintainer-ready pull request draft. All claims are grounded strictly in parsed diff evidence and test results.
                </p>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => onPrepareDraftPR(diffInput)}
                  disabled={isPreparingPR}
                >
                  {isPreparingPR ? 'Generating PR Draft...' : draftPR ? '🔄 Refresh Draft PR' : '✨ Generate Draft PR'}
                </button>
              </div>

              {draftPR ? (
                <div className="draft-pr-container">
                  <div className="pr-title-row">
                    <strong>PR Title:</strong>
                    <code className="pr-title-code">{draftPR.title}</code>
                  </div>

                  <div className="pr-field">
                    <h4>Summary of Changes</h4>
                    <p>{draftPR.summary_of_changes}</p>
                  </div>

                  <div className="pr-field">
                    <h4>Problem Addressed</h4>
                    <p>{draftPR.problem_addressed}</p>
                  </div>

                  <div className="pr-field">
                    <h4>Implementation Overview</h4>
                    <p>{draftPR.implementation_overview}</p>
                  </div>

                  <div className="pr-field">
                    <h4>Tests Performed</h4>
                    <div className="tests-categorized-grid">
                      <div>
                        <strong>Executed &amp; Passed:</strong>
                        <ul>
                          {draftPR.tests_performed.executed_and_passed?.length ? (
                            draftPR.tests_performed.executed_and_passed.map((t, i) => <li key={i}>{t}</li>)
                          ) : (
                            <li>None recorded</li>
                          )}
                        </ul>
                      </div>
                      <div>
                        <strong>Not Executed / Pending:</strong>
                        <ul>
                          {draftPR.tests_performed.not_executed?.length ? (
                            draftPR.tests_performed.not_executed.map((t, i) => <li key={i}>{t}</li>)
                          ) : (
                            <li>None recorded</li>
                          )}
                        </ul>
                      </div>
                    </div>
                  </div>

                  {draftPR.manual_verification_checklist.length > 0 && (
                    <div className="pr-field">
                      <h4>Maintainer Checklist</h4>
                      <ul className="pr-checklist">
                        {draftPR.manual_verification_checklist.map((c, i) => (
                          <li key={i}>[ ] {c}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="pr-actions-row">
                    <button type="button" className="btn-secondary" onClick={handleCopyPR}>
                      {copiedPR ? '✓ Copied PR Draft' : '📋 Copy Full PR Description'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="empty-state-box">
                  Click &quot;Generate Draft PR&quot; above to synthesize a maintainer-ready PR proposal.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={handleCopySummary}>
            {copiedSummary ? '✓ Copied Summary' : '📋 Copy Verification Summary'}
          </button>
          <button type="button" className="btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
