import React, { useState, useEffect } from 'react';
import {
  GuidedImplementationPlan,
  ImplementationStep,
} from '../types';

interface GuidedImplementationModalProps {
  plan: GuidedImplementationPlan;
  onClose: () => void;
  onOpenVerification?: (issueNumber: number) => void;
}

type StepStatus = 'not_started' | 'in_progress' | 'understood' | 'completed';

export const GuidedImplementationModal: React.FC<GuidedImplementationModalProps> = ({
  plan,
  onClose,
  onOpenVerification,
}) => {
  const [activeTab, setActiveTab] = useState<'steps' | 'approaches' | 'exploration'>('steps');
  const [activeStepIndex, setActiveStepIndex] = useState<number>(0);
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>({});
  const [revealedHints, setRevealedHints] = useState<Record<string, boolean>>({});
  const [expandedPatches, setExpandedPatches] = useState<Record<string, boolean>>({});
  const [copiedText, setCopiedText] = useState(false);
  const [copiedSnippetId, setCopiedSnippetId] = useState<string | null>(null);

  // Reset state when switching issue numbers
  useEffect(() => {
    setActiveTab('steps');
    setActiveStepIndex(0);
    setStepStatuses({});
    setRevealedHints({});
    setExpandedPatches({});
  }, [plan.issue_number]);

  const setStatus = (stepId: string, status: StepStatus) => {
    setStepStatuses((prev) => ({ ...prev, [stepId]: status }));
  };

  const toggleHint = (hintKey: string) => {
    setRevealedHints((prev) => ({ ...prev, [hintKey]: !prev[hintKey] }));
  };

  const togglePatch = (stepId: string) => {
    setExpandedPatches((prev) => ({ ...prev, [stepId]: !prev[stepId] }));
  };

  const activeStep: ImplementationStep | undefined = plan.steps[activeStepIndex];

  const totalSteps = plan.steps.length;
  const completedSteps = plan.steps.filter((s) => stepStatuses[s.id] === 'completed').length;

  const copyRoadmapSummary = () => {
    const lines = [
      `PatchLoom Guided Implementation Roadmap: #${plan.issue_number} - ${plan.issue_title}`,
      `Experience Level: ${plan.experience_level}`,
      `Overview: ${plan.overview}`,
      `Progress: ${completedSteps}/${totalSteps} steps completed`,
      '',
      'Steps:',
      ...plan.steps.map((s, idx) => {
        const st = stepStatuses[s.id] || 'not_started';
        return `${idx + 1}. [${st.toUpperCase()}] ${s.title}\n   Objective: ${s.objective}\n   Expected Outcome: ${s.expected_outcome}`;
      }),
    ];
    navigator.clipboard.writeText(lines.join('\n'));
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  const copySnippet = (snippet: string, stepId: string) => {
    navigator.clipboard.writeText(snippet);
    setCopiedSnippetId(stepId);
    setTimeout(() => setCopiedSnippetId(null), 2000);
  };

  const getStatusLabel = (status: StepStatus) => {
    switch (status) {
      case 'completed':
        return '✓ Completed';
      case 'understood':
        return '👁 Understood';
      case 'in_progress':
        return '⏳ In Progress';
      case 'not_started':
      default:
        return '○ Not Started';
    }
  };

  const getStatusClass = (status: StepStatus) => {
    switch (status) {
      case 'completed':
        return 'status-pill-completed';
      case 'understood':
        return 'status-pill-understood';
      case 'in_progress':
        return 'status-pill-inprogress';
      case 'not_started':
      default:
        return 'status-pill-notstarted';
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content guided-modal-content" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div>
            <div className="badge-row">
              <span className="badge badge-verified">LEARN & BUILD PILLAR</span>
              <span className="badge badge-verified" style={{ textTransform: 'capitalize' }}>
                {plan.experience_level} Contributor
              </span>
              {plan.ai_status === 'complete' ? (
                <span className="badge badge-inference">Gemma 4 Guided</span>
              ) : (
                <span className="badge badge-unknown">Deterministic Fallback</span>
              )}
            </div>
            <h2>Guided Implementation: #{plan.issue_number}</h2>
            <p className="modal-issue-title">
              <a href={plan.issue_url} target="_blank" rel="noopener noreferrer">
                {plan.issue_title} ↗
              </a>
            </p>
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        {/* Warnings Banner */}
        {plan.warnings && plan.warnings.length > 0 && (
          <div className="warning-banner" style={{ margin: '1rem 1.5rem 0' }}>
            {plan.warnings.map((w, i) => (
              <p key={i}>⚠️ {w}</p>
            ))}
          </div>
        )}

        {/* Strategy Overview */}
        <div className="guided-overview-card">
          <div className="guided-overview-header">
            <strong>Implementation Strategy</strong>
            <span className="badge badge-inference">Recommended: {plan.recommended_approach_id}</span>
          </div>
          <p className="guided-overview-text">{plan.overview}</p>
        </div>

        {/* Navigation Tabs */}
        <div className="learn-tabs-header">
          <button
            type="button"
            className={`learn-tab-btn ${activeTab === 'steps' ? 'active' : ''}`}
            onClick={() => setActiveTab('steps')}
          >
            🗺 Implementation Roadmap ({completedSteps}/{totalSteps})
          </button>
          <button
            type="button"
            className={`learn-tab-btn ${activeTab === 'approaches' ? 'active' : ''}`}
            onClick={() => setActiveTab('approaches')}
          >
            ⚖️ Approaches ({plan.approaches.length})
          </button>
          <button
            type="button"
            className={`learn-tab-btn ${activeTab === 'exploration' ? 'active' : ''}`}
            onClick={() => setActiveTab('exploration')}
          >
            🧭 Code Exploration ({plan.exploration_targets.length})
          </button>
        </div>

        {/* Tab Body */}
        <div className="learn-tab-body">
          {/* TAB 1: ROADMAP & STEPS */}
          {activeTab === 'steps' && (
            <div className="guided-roadmap-layout">
              {/* Step Navigator Sidebar */}
              <div className="guided-steps-sidebar">
                <div className="steps-sidebar-header">
                  <strong>Roadmap Steps</strong>
                  <span className="steps-progress-text">
                    {completedSteps} / {totalSteps} Done
                  </span>
                </div>
                <div className="steps-nav-list">
                  {plan.steps.map((step, idx) => {
                    const status = stepStatuses[step.id] || 'not_started';
                    const isCurrent = idx === activeStepIndex;
                    return (
                      <button
                        key={step.id}
                        type="button"
                        className={`step-nav-item ${isCurrent ? 'active' : ''}`}
                        onClick={() => setActiveStepIndex(idx)}
                      >
                        <div className="step-nav-number">{step.order}</div>
                        <div className="step-nav-info">
                          <div className="step-nav-title">{step.title}</div>
                          <span className={`status-pill ${getStatusClass(status)}`}>
                            {getStatusLabel(status)}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Active Step Workspace */}
              {activeStep && (
                <div className="guided-active-step-panel">
                  {/* Step Header */}
                  <div className="step-panel-header">
                    <div>
                      <span className="badge badge-verified">Step {activeStep.order} of {totalSteps}</span>
                      <h3>{activeStep.title}</h3>
                    </div>
                    {/* Contributor Status Selector */}
                    <div className="status-selector-group">
                      <span className="status-selector-label">My Progress:</span>
                      {(['not_started', 'in_progress', 'understood', 'completed'] as StepStatus[]).map((st) => (
                        <button
                          key={st}
                          type="button"
                          className={`status-select-btn ${stepStatuses[activeStep.id] === st || (!stepStatuses[activeStep.id] && st === 'not_started') ? 'selected ' + getStatusClass(st) : ''}`}
                          onClick={() => setStatus(activeStep.id, st)}
                        >
                          {getStatusLabel(st)}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Objective & Why It Matters */}
                  <div className="step-section">
                    <div className="step-objective-box">
                      <strong>🎯 Objective:</strong> {activeStep.objective}
                    </div>
                    <p className="step-why-text">
                      <strong>Why this matters:</strong> {activeStep.why_it_matters}
                    </p>
                  </div>

                  {/* Grounded Files & Elements to Inspect */}
                  <div className="step-section">
                    <h4>📁 Grounded Repository Targets</h4>
                    <div className="grounded-files-row">
                      {activeStep.files && activeStep.files.length > 0 ? (
                        activeStep.files.map((f, i) => (
                          <span key={i} className="grounded-file-tag">
                            📄 {f}
                          </span>
                        ))
                      ) : (
                        <span className="muted-text">Refer to general repository structure</span>
                      )}
                    </div>
                    <div className="step-inspect-box">
                      <strong>🔍 What to inspect:</strong> {activeStep.what_to_inspect}
                    </div>
                    <div className="step-outcome-box">
                      <strong>🏁 Expected outcome:</strong> {activeStep.expected_outcome}
                    </div>
                    <div className="step-criteria-box">
                      <strong>✅ Completion criteria:</strong> {activeStep.completion_criteria}
                    </div>
                  </div>

                  {/* Progressive Hint System */}
                  <div className="step-section">
                    <h4>💡 Progressive Hints</h4>
                    <p className="hints-intro-text">
                      Hints reduce ambiguity step-by-step. Reveal only what you need to keep solving independently.
                    </p>
                    <div className="hints-container">
                      {activeStep.hints && activeStep.hints.length > 0 ? (
                        activeStep.hints.map((hint, hIdx) => {
                          const hintKey = `${activeStep.id}-hint-${hint.level}-${hIdx}`;
                          const isRevealed = !!revealedHints[hintKey];
                          const hintIcons = ['💡', '🔍', '⚙️'];
                          const hintLevels = ['Gentle Direction', 'Specific Investigation', 'Technical Guidance'];

                          return (
                            <div key={hintKey} className={`progressive-hint-card ${isRevealed ? 'revealed' : ''}`}>
                              <div className="hint-card-header">
                                <div className="hint-title-group">
                                  <span className="hint-icon">{hintIcons[hint.level - 1] || '💡'}</span>
                                  <strong>Hint {hint.level}: {hint.title}</strong>
                                  <span className="badge badge-unknown" style={{ fontSize: '0.75rem' }}>
                                    {hintLevels[hint.level - 1] || `Level ${hint.level}`}
                                  </span>
                                  <span className={hint.kind === 'evidence_based' ? 'badge badge-verified' : 'badge badge-inference'} style={{ fontSize: '0.7rem' }}>
                                    {hint.kind === 'evidence_based' ? 'Repo Evidence' : 'Conceptual'}
                                  </span>
                                </div>
                                <button
                                  type="button"
                                  className="btn-secondary hint-toggle-btn"
                                  onClick={() => toggleHint(hintKey)}
                                >
                                  {isRevealed ? 'Hide Hint' : 'Reveal Hint'}
                                </button>
                              </div>
                              {isRevealed && (
                                <div className="hint-content-body">
                                  <p>{hint.content}</p>
                                </div>
                              )}
                            </div>
                          );
                        })
                      ) : (
                        <p className="muted-text">No additional hints needed for this step.</p>
                      )}
                    </div>
                  </div>

                  {/* Step Checkpoint */}
                  <div className="step-section checkpoint-section">
                    <h4>🎯 Self-Reflection Checkpoint</h4>
                    <div className="checkpoint-card">
                      <p className="checkpoint-question">❓ {activeStep.checkpoint.question}</p>
                      <p className="checkpoint-guidance">💡 {activeStep.checkpoint.verification_guidance}</p>
                    </div>
                  </div>

                  {/* Optional Educational Code Suggestion */}
                  {activeStep.patch_suggestion && (
                    <div className="step-section patch-suggestion-section">
                      <div className="patch-toggle-row">
                        <button
                          type="button"
                          className="btn-secondary patch-toggle-btn"
                          onClick={() => togglePatch(activeStep.id)}
                        >
                          {expandedPatches[activeStep.id]
                            ? '▲ Collapse Educational Code Suggestion'
                            : '💻 Inspect Optional Code Suggestion (Educational Draft)'}
                        </button>
                      </div>

                      {expandedPatches[activeStep.id] && (
                        <div className="patch-suggestion-card">
                          <div className="patch-warning-notice">
                            <strong>⚠️ UNVERIFIED EDUCATIONAL DRAFT</strong>
                            <p>
                              This code snippet illustrates one possible approach and has NOT been automatically
                              executed, tested, or verified against the repository. Review assumptions, test locally,
                              and do not blindly apply.
                            </p>
                          </div>

                          <div className="patch-meta-row">
                            <span><strong>Target File:</strong> <code>{activeStep.patch_suggestion.target_path}</code></span>
                            {activeStep.patch_suggestion.target_symbol && (
                              <span><strong>Target Symbol:</strong> <code>{activeStep.patch_suggestion.target_symbol}</code></span>
                            )}
                          </div>

                          <p className="patch-summary-text">{activeStep.patch_suggestion.summary}</p>

                          <div className="code-snippet-block">
                            <div className="snippet-header">
                              <span>Illustration Snippet</span>
                              <button
                                type="button"
                                className="copy-snippet-btn"
                                onClick={() => copySnippet(activeStep.patch_suggestion!.code_snippet, activeStep.id)}
                              >
                                {copiedSnippetId === activeStep.id ? '✓ Copied' : 'Copy Code'}
                              </button>
                            </div>
                            <pre>
                              <code>{activeStep.patch_suggestion.code_snippet}</code>
                            </pre>
                          </div>

                          {activeStep.patch_suggestion.assumptions && activeStep.patch_suggestion.assumptions.length > 0 && (
                            <div className="patch-assumptions-box">
                              <strong>Assumptions:</strong>
                              <ul>
                                {activeStep.patch_suggestion.assumptions.map((a, i) => (
                                  <li key={i}>{a}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          <div className="patch-effect-box">
                            <strong>Expected Effect:</strong> {activeStep.patch_suggestion.expected_effect}
                          </div>

                          {activeStep.patch_suggestion.potential_risks && activeStep.patch_suggestion.potential_risks.length > 0 && (
                            <div className="patch-risks-box">
                              <strong>Potential Risks & Caveats:</strong>
                              <ul>
                                {activeStep.patch_suggestion.potential_risks.map((r, i) => (
                                  <li key={i}>{r}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Step Navigation Controls */}
                  <div className="step-nav-footer">
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={activeStepIndex === 0}
                      onClick={() => setActiveStepIndex((prev) => Math.max(0, prev - 1))}
                    >
                      ← Previous Step
                    </button>
                    <span className="step-footer-counter">
                      Step {activeStepIndex + 1} of {totalSteps}
                    </span>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={activeStepIndex === totalSteps - 1}
                      onClick={() => setActiveStepIndex((prev) => Math.min(totalSteps - 1, prev + 1))}
                    >
                      Next Step →
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: IMPLEMENTATION APPROACHES */}
          {activeTab === 'approaches' && (
            <div className="guided-approaches-view">
              <div className="approaches-intro">
                <h3>Alternative Implementation Approaches</h3>
                <p>
                  Real engineering problems often have multiple viable solutions. Compare these trade-offs before
                  starting your implementation.
                </p>
              </div>
              <div className="approaches-grid">
                {plan.approaches.map((appr) => {
                  const isRecommended = appr.approach_id === plan.recommended_approach_id;
                  return (
                    <div
                      key={appr.approach_id}
                      className={`approach-card ${isRecommended ? 'recommended-approach' : ''}`}
                    >
                      <div className="approach-card-header">
                        <div>
                          {isRecommended && (
                            <span className="badge badge-verified" style={{ marginBottom: '0.4rem', display: 'inline-block' }}>
                              ★ Recommended Approach
                            </span>
                          )}
                          <h4>{appr.title}</h4>
                        </div>
                        <span className="approach-id-tag"><code>{appr.approach_id}</code></span>
                      </div>

                      <p className="approach-summary">{appr.summary}</p>

                      {appr.relevant_design_patterns && appr.relevant_design_patterns.length > 0 && (
                        <div className="approach-patterns">
                          <strong>Design Patterns:</strong>
                          <div className="patterns-tags">
                            {appr.relevant_design_patterns.map((p, i) => (
                              <span key={i} className="pattern-tag">{p}</span>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="approach-pros-cons-grid">
                        <div className="approach-pros-col">
                          <strong>✓ Advantages:</strong>
                          <ul>
                            {appr.pros.map((pro, i) => (
                              <li key={i}>{pro}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="approach-cons-col">
                          <strong>⚠️ Trade-offs & Limitations:</strong>
                          <ul>
                            {appr.cons_and_tradeoffs.map((con, i) => (
                              <li key={i}>{con}</li>
                            ))}
                          </ul>
                        </div>
                      </div>

                      {appr.edge_cases && appr.edge_cases.length > 0 && (
                        <div className="approach-edge-cases">
                          <strong>Edge Cases to Guard Against:</strong>
                          <ul>
                            {appr.edge_cases.map((ec, i) => (
                              <li key={i}>{ec}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {appr.regression_risks && appr.regression_risks.length > 0 && (
                        <div className="approach-risks">
                          <strong>Potential Regression Risks:</strong>
                          <ul>
                            {appr.regression_risks.map((rr, i) => (
                              <li key={i}>{rr}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {appr.unanswered_questions && appr.unanswered_questions.length > 0 && (
                        <div className="approach-questions">
                          <strong>Unanswered Questions for Maintainers:</strong>
                          <ul>
                            {appr.unanswered_questions.map((uq, i) => (
                              <li key={i}>{uq}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 3: CODE EXPLORATION TARGETS */}
          {activeTab === 'exploration' && (
            <div className="guided-exploration-view">
              <div className="exploration-intro">
                <h3>Grounded Code Exploration Targets</h3>
                <p>
                  These files and components are verified from the repository tree to guide your investigation.
                </p>
              </div>
              <div className="exploration-cards-list">
                {plan.exploration_targets.map((target, idx) => (
                  <div key={idx} className="exploration-target-card">
                    <div className="exploration-card-header">
                      <div>
                        <span className="badge badge-verified">Verified Path</span>
                        <h4 className="target-file-path"><code>{target.path}</code></h4>
                      </div>
                      {target.module_name && (
                        <span className="badge badge-unknown">Module: {target.module_name}</span>
                      )}
                    </div>

                    <p className="target-why-text">
                      <strong>Why Relevant:</strong> {target.why_relevant}
                    </p>

                    {target.target_symbols && target.target_symbols.length > 0 && (
                      <div className="target-symbols-row">
                        <strong>Target Symbols to Locate:</strong>
                        <div className="symbols-tags">
                          {target.target_symbols.map((sym, sIdx) => (
                            <code key={sIdx} className="symbol-tag">{sym}</code>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="target-behavior-box">
                      <strong>Behavior to Observe:</strong> {target.behavior_to_observe}
                    </div>

                    {target.suggested_search_terms && target.suggested_search_terms.length > 0 && (
                      <div className="target-search-terms-row">
                        <strong>Suggested Search Terms:</strong>
                        <div className="search-terms-tags">
                          {target.suggested_search_terms.map((term, tIdx) => (
                            <span key={tIdx} className="search-term-tag">🔍 {term}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={copyRoadmapSummary}>
            {copiedText ? '✓ Copied Roadmap Summary' : '📋 Copy Roadmap Summary'}
          </button>
          {onOpenVerification && (
            <button
              type="button"
              className="btn-accent"
              onClick={() => onOpenVerification(plan.issue_number)}
              style={{ fontWeight: 600, backgroundColor: '#059669', color: '#ffffff' }}
            >
              🔍 Proceed to Verification &amp; Review
            </button>
          )}
          <button type="button" className="btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
