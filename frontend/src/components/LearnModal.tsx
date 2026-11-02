import React, { useState, useEffect } from 'react';
import { IssueLearningBrief, ReadinessChecklistItem } from '../types';

interface LearnModalProps {
  brief: IssueLearningBrief;
  onClose: () => void;
  onStartGuidedImplementation?: (issueNumber: number) => void;
}

export const LearnModal: React.FC<LearnModalProps> = ({ brief, onClose, onStartGuidedImplementation }) => {
  const [activeTab, setActiveTab] = useState<'explanation' | 'codebase' | 'concepts' | 'checklist'>('explanation');
  const [checkedItems, setCheckedItems] = useState<Record<string, boolean>>({});
  const [copiedText, setCopiedText] = useState(false);

  // Reset checklist and active tab when switching issues
  useEffect(() => {
    setCheckedItems({});
    setActiveTab('explanation');
  }, [brief.issue_number]);

  const toggleCheck = (id: string) => {
    setCheckedItems((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const totalChecklist = brief.readiness_checklist.length;
  const completedCount = brief.readiness_checklist.filter((_, idx) => {
    const key = `chk-${idx}`;
    return !!checkedItems[key];
  }).length;

  const copyBriefSummary = () => {
    const text = `PatchLoom Issue Learning Brief: #${brief.issue_number} - ${brief.issue_title}
Experience Level: ${brief.experience_level}
Summary: ${brief.explanation.summary}
Problem: ${brief.explanation.problem_description}
Expected Outcome: ${brief.explanation.expected_outcome}

Readiness Checklist (${completedCount}/${totalChecklist} confirmed):
${brief.readiness_checklist.map((item, idx) => `[${checkedItems[`chk-${idx}`] ? 'x' : ' '}] ${item.item}`).join('\n')}`;

    navigator.clipboard.writeText(text);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  const getCategoryLabel = (category: ReadinessChecklistItem['category']) => {
    switch (category) {
      case 'problem_understanding':
        return 'Problem Understanding';
      case 'expected_behavior':
        return 'Expected Behavior';
      case 'architecture_components':
        return 'Architecture & Files';
      case 'technical_concepts':
        return 'Technical Concepts';
      case 'testing_approach':
        return 'Testing Approach';
      case 'remaining_uncertainties':
        return 'Uncertainties';
      default:
        return category;
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content learn-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="badge-row">
              <span className="badge badge-verified">LEARN PILLAR</span>
              <span className="badge badge-verified" style={{ textTransform: 'capitalize' }}>
                {brief.experience_level} Contributor
              </span>
              {brief.ai_status === 'complete' ? (
                <span className="badge badge-inference">Gemma 4 Grounded</span>
              ) : (
                <span className="badge badge-unknown">Deterministic Fallback</span>
              )}
            </div>
            <h2>Issue Learning Brief: #{brief.issue_number}</h2>
            <p className="modal-issue-title">
              <a href={brief.issue_url} target="_blank" rel="noopener noreferrer">
                {brief.issue_title} ↗
              </a>
            </p>
          </div>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        {brief.warnings && brief.warnings.length > 0 && (
          <div className="warning-banner" style={{ margin: '1rem 1.5rem 0' }}>
            {brief.warnings.map((w, i) => (
              <p key={i}>⚠️ {w}</p>
            ))}
          </div>
        )}

        <div className="learn-tabs-header">
          <button
            type="button"
            className={`learn-tab-btn ${activeTab === 'explanation' ? 'active' : ''}`}
            onClick={() => setActiveTab('explanation')}
          >
            📖 Explanation & Requirements
          </button>
          <button
            type="button"
            className={`learn-tab-btn ${activeTab === 'codebase' ? 'active' : ''}`}
            onClick={() => setActiveTab('codebase')}
          >
            🧭 Codebase & Targets ({brief.investigation_targets.length})
          </button>
          <button
            type="button"
            className={`learn-tab-btn ${activeTab === 'concepts' ? 'active' : ''}`}
            onClick={() => setActiveTab('concepts')}
          >
            💡 Concepts & Objectives ({brief.concepts.length})
          </button>
          <button
            type="button"
            className={`learn-tab-btn ${activeTab === 'checklist' ? 'active' : ''}`}
            onClick={() => setActiveTab('checklist')}
          >
            ✅ Readiness Checklist ({completedCount}/{totalChecklist})
          </button>
        </div>

        <div className="modal-body learn-modal-body">
          {/* TAB 1: EXPLANATION */}
          {activeTab === 'explanation' && (
            <div className="learn-tab-content">
              <div className="plan-section">
                <div className="learn-adaptation-banner">
                  <strong>Personalized Adaptation:</strong> {brief.explanation.experience_adaptation_note}
                </div>
                <h3>Executive Summary</h3>
                <p className="summary-text">{brief.explanation.summary}</p>
              </div>

              <div className="guidance-cards-row">
                <div className="guidance-card">
                  <div className="guidance-header">
                    <h4>Problem Statement</h4>
                    <span className="badge badge-verified">Issue Report</span>
                  </div>
                  <p>{brief.explanation.problem_description}</p>
                </div>

                <div className="guidance-card">
                  <div className="guidance-header">
                    <h4>Expected Outcome</h4>
                    <span className="badge badge-verified">Success Goal</span>
                  </div>
                  <p>{brief.explanation.expected_outcome}</p>
                </div>
              </div>

              {brief.explanation.why_it_matters && (
                <div className="plan-section">
                  <h4>Why This Matters</h4>
                  <p>{brief.explanation.why_it_matters}</p>
                </div>
              )}

              <div className="plan-section">
                <h3>Requirements Breakdown ({brief.requirements.length})</h3>
                <div className="learn-requirements-list">
                  {brief.requirements.map((req, idx) => (
                    <div key={idx} className="learn-requirement-card">
                      <div className="requirement-header">
                        <span className={`badge ${req.classification === 'explicit' ? 'badge-verified' : 'badge-inference'}`}>
                          {req.classification}
                        </span>
                        <span className="badge badge-unknown" style={{ fontSize: '0.75rem' }}>
                          Confidence: {req.confidence}
                        </span>
                        <span className="requirement-source">Source: {req.source}</span>
                      </div>
                      <p className="requirement-desc">{req.description}</p>
                      {req.supporting_evidence && (
                        <div className="requirement-evidence">
                          <em>Evidence: &quot;{req.supporting_evidence}&quot;</em>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {brief.explanation.constraints_and_conditions.length > 0 && (
                <div className="plan-section">
                  <h4>Technical Constraints & Edge Cases</h4>
                  <ul className="risks-list">
                    {brief.explanation.constraints_and_conditions.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}

              {brief.explanation.ambiguities_and_unanswered_questions.length > 0 && (
                <div className="plan-section" style={{ backgroundColor: '#fffbeb', padding: '1rem', borderRadius: '8px', border: '1px solid #fef3c7' }}>
                  <h4 style={{ color: '#b45309', margin: 0, marginBottom: '0.5rem' }}>❓ Ambiguities & Unresolved Questions</h4>
                  <ul className="risks-list" style={{ color: '#92400e' }}>
                    {brief.explanation.ambiguities_and_unanswered_questions.map((amb, i) => (
                      <li key={i}>{amb}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: CODEBASE CONTEXT & INVESTIGATION TARGETS */}
          {activeTab === 'codebase' && (
            <div className="learn-tab-content">
              {brief.relevant_modules.length > 0 && (
                <div className="plan-section">
                  <h3>Candidate Architecture Modules</h3>
                  <div className="tags-list">
                    {brief.relevant_modules.map((mod, idx) => (
                      <span key={idx} className="badge badge-inference" style={{ fontSize: '0.85rem', padding: '0.35rem 0.65rem' }}>
                        📦 {mod}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="plan-section">
                <h3>Candidate Investigation Targets ({brief.investigation_targets.length})</h3>
                <p className="field-hint" style={{ marginBottom: '1rem' }}>
                  Files verified strictly in the repository tree. Treat as targets to inspect and explore, not confirmed bug locations.
                </p>
                <div className="investigation-targets-list">
                  {brief.investigation_targets.map((target, idx) => (
                    <div key={idx} className="investigation-target-card">
                      <div className="target-card-header">
                        <code>{target.path}</code>
                        <span className="badge badge-verified">Tree Verified</span>
                        {target.module_name && (
                          <span className="badge badge-inference">Module: {target.module_name}</span>
                        )}
                      </div>
                      <p className="target-why"><strong>Why Relevant:</strong> {target.why_relevant}</p>
                      <div className="target-inspect-box">
                        <strong>What to Inspect:</strong> {target.what_to_inspect}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {brief.related_tests_and_docs.length > 0 && (
                <div className="plan-section">
                  <h3>Related Tests & Documentation</h3>
                  <div className="tags-list">
                    {brief.related_tests_and_docs.map((item, idx) => (
                      <span key={idx} className="stat-pill" style={{ background: '#f3f4f6' }}>
                        📄 {item}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: CONCEPTS & LEARNING OBJECTIVES */}
          {activeTab === 'concepts' && (
            <div className="learn-tab-content">
              <div className="plan-section">
                <h3>Technical Concepts to Master</h3>
                <p className="field-hint" style={{ marginBottom: '1rem' }}>
                  Foundational topics and domain concepts relevant to understanding and resolving this issue.
                </p>
                <div className="concepts-grid">
                  {brief.concepts.map((concept, idx) => (
                    <div key={idx} className="concept-card">
                      <div className="concept-header">
                        <span className="concept-order">#{concept.learning_order || idx + 1}</span>
                        <h4>{concept.name}</h4>
                        <span className={`badge difficulty-${concept.difficulty || 'beginner'}`}>
                          {concept.difficulty || 'beginner'}
                        </span>
                      </div>
                      <p className="concept-explanation">{concept.explanation}</p>
                      <p className="concept-why"><strong>Why it matters:</strong> {concept.why_it_matters}</p>
                      {concept.prerequisites && concept.prerequisites.length > 0 && (
                        <div className="concept-prereqs">
                          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#4b5563' }}>Prerequisites: </span>
                          {concept.prerequisites.map((p, i) => (
                            <span key={i} className="skill-gap-tag" style={{ fontSize: '0.75rem', marginRight: '0.25rem' }}>
                              {p}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="plan-section">
                <h3>Measurable Learning Objectives</h3>
                <div className="objectives-list">
                  {brief.learning_objectives.map((obj, idx) => (
                    <div key={idx} className="objective-card">
                      <div className="objective-header">
                        <span className="objective-number">Goal {idx + 1}</span>
                        <h4>{obj.title}</h4>
                      </div>
                      <p className="objective-desc">{obj.description}</p>
                      <div className="objective-relevance">
                        <strong>Relevance:</strong> {obj.relevance}
                      </div>
                      <div className="objective-criterion">
                        <strong>Completion Criterion:</strong> {obj.completion_criterion}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: READINESS CHECKLIST */}
          {activeTab === 'checklist' && (
            <div className="learn-tab-content">
              <div className="plan-section">
                <div className="checklist-progress-box">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3>Understanding Readiness Checklist</h3>
                    <span className="progress-badge">
                      {completedCount} of {totalChecklist} checks confirmed
                    </span>
                  </div>
                  <p className="field-hint">
                    Self-assessment items to verify your understanding before making changes or drafting code.
                  </p>
                  <div className="progress-bar-container">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${totalChecklist > 0 ? (completedCount / totalChecklist) * 100 : 0}%` }}
                    />
                  </div>
                </div>

                <div className="checklist-items-container">
                  {brief.readiness_checklist.map((item, idx) => {
                    const key = `chk-${idx}`;
                    const isDone = !!checkedItems[key];
                    return (
                      <div
                        key={idx}
                        className={`readiness-checklist-row ${isDone ? 'checked' : ''}`}
                        onClick={() => toggleCheck(key)}
                      >
                        <input
                          type="checkbox"
                          checked={isDone}
                          onChange={() => {}}
                          className="readiness-checkbox"
                          aria-label={item.item}
                        />
                        <div className="checklist-text-col">
                          <div className="checklist-category-row">
                            <span className="badge badge-unknown" style={{ fontSize: '0.7rem' }}>
                              {getCategoryLabel(item.category)}
                            </span>
                          </div>
                          <p className="checklist-item-text">{item.item}</p>
                          {item.guidance && (
                            <p className="checklist-guidance">💡 {item.guidance}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={copyBriefSummary}>
            {copiedText ? '✓ Copied Summary' : '📋 Copy Brief Summary'}
          </button>
          {onStartGuidedImplementation && (
            <button
              type="button"
              className="btn-primary"
              style={{ backgroundColor: '#2563eb' }}
              onClick={() => {
                onClose();
                onStartGuidedImplementation(brief.issue_number);
              }}
            >
              🚀 Start Guided Implementation
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
