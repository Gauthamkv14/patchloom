import React, { useState } from 'react';
import { PlanResponse } from '../types';

interface PlanModalProps {
  plan: PlanResponse;
  onClose: () => void;
}

export const PlanModal: React.FC<PlanModalProps> = ({ plan, onClose }) => {
  const [copiedTitle, setCopiedTitle] = useState(false);
  const [copiedDesc, setCopiedDesc] = useState(false);
  const [copiedChecklist, setCopiedChecklist] = useState(false);

  const copyToClipboard = (text: string, setCopied: (val: boolean) => void) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formattedChecklist = plan.checklist.map((c) => `- [ ] ${c}`).join('\n');

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="badge-row">
              <span className="badge badge-verified">Plan Ready</span>
              {plan.ai_status === 'complete' ? (
                <span className="badge badge-inference">Gemma 4 Grounded</span>
              ) : (
                <span className="badge badge-unknown">Deterministic Fallback</span>
              )}
            </div>
            <h2>First-PR Plan: #{plan.issue_number}</h2>
            <p className="modal-issue-title">{plan.issue_title}</p>
          </div>
          <button type="button" className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {plan.warnings && plan.warnings.length > 0 && (
            <div className="warning-banner">
              {plan.warnings.map((w, i) => (
                <p key={i}>⚠️ {w}</p>
              ))}
            </div>
          )}

          <div className="plan-section">
            <h3>Overview & Approach</h3>
            <p className="summary-text">{plan.summary}</p>
          </div>

          <div className="guidance-cards-row">
            <div className="guidance-card">
              <div className="guidance-header">
                <h4>Setup Guidance</h4>
                <span
                  className={`badge ${
                    plan.setup_guidance.status === 'verified'
                      ? 'badge-verified'
                      : plan.setup_guidance.status === 'unknown'
                      ? 'badge-unknown'
                      : 'badge-inference'
                  }`}
                >
                  {plan.setup_guidance.status}
                </span>
              </div>
              <p>{plan.setup_guidance.notes}</p>
            </div>

            <div className="guidance-card">
              <div className="guidance-header">
                <h4>Testing Guidance</h4>
                <span
                  className={`badge ${
                    plan.test_guidance.status === 'verified'
                      ? 'badge-verified'
                      : plan.test_guidance.status === 'unknown'
                      ? 'badge-unknown'
                      : 'badge-inference'
                  }`}
                >
                  {plan.test_guidance.status}
                </span>
              </div>
              <p>{plan.test_guidance.notes}</p>
            </div>
          </div>

          <div className="plan-section">
            <h3>Implementation Steps ({plan.steps.length} Grounded Steps)</h3>
            <ol className="steps-list">
              {plan.steps.map((step, idx) => (
                <li key={idx} className="step-item">
                  <div className="step-title-row">
                    <strong>{step.title}</strong>
                    <span
                      className={`badge ${
                        step.kind === 'verified' ? 'badge-verified' : 'badge-inference'
                      }`}
                    >
                      {step.kind}
                    </span>
                  </div>
                  <p className="step-detail">{step.detail}</p>
                  {step.files && step.files.length > 0 && (
                    <div className="step-files">
                      <span className="files-label">Target Files:</span>
                      {step.files.map((f, i) => (
                        <code key={i} className="file-tag">
                          {f}
                        </code>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </div>

          <div className="plan-section">
            <div className="section-header-row">
              <h3>Contributor Verification Checklist</h3>
              <button
                type="button"
                className="btn-copy"
                onClick={() => copyToClipboard(formattedChecklist, setCopiedChecklist)}
              >
                {copiedChecklist ? '✓ Copied' : 'Copy Checklist'}
              </button>
            </div>
            <ul className="checklist">
              {plan.checklist.map((item, idx) => (
                <li key={idx} className="checklist-item">
                  <input type="checkbox" id={`check-${idx}`} />
                  <label htmlFor={`check-${idx}`}>{item}</label>
                </li>
              ))}
            </ul>
          </div>

          <div className="plan-section">
            <div className="section-header-row">
              <h3>Draft Pull Request</h3>
              <div className="copy-btn-group">
                <button
                  type="button"
                  className="btn-copy"
                  onClick={() => copyToClipboard(plan.pr_title, setCopiedTitle)}
                >
                  {copiedTitle ? '✓ Copied Title' : 'Copy PR Title'}
                </button>
                <button
                  type="button"
                  className="btn-copy"
                  onClick={() => copyToClipboard(plan.pr_description_draft, setCopiedDesc)}
                >
                  {copiedDesc ? '✓ Copied Body' : 'Copy PR Description'}
                </button>
              </div>
            </div>

            <div className="draft-pr-box">
              <div className="draft-row">
                <span className="draft-label">Title:</span>
                <code className="draft-code">{plan.pr_title}</code>
              </div>
              <div className="draft-row">
                <span className="draft-label">Description:</span>
                <pre className="draft-body">{plan.pr_description_draft}</pre>
              </div>
            </div>
          </div>

          {plan.open_questions_for_maintainer && plan.open_questions_for_maintainer.length > 0 && (
            <div className="plan-section">
              <h3>Open Questions for Maintainers</h3>
              <ul className="questions-list">
                {plan.open_questions_for_maintainer.map((q, idx) => (
                  <li key={idx}>{q}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="disclaimer-banner">
            ℹ️ <strong>Notice:</strong> PatchLoom is an advisory planning tool. It never creates branches, executes code, or submits pull requests to GitHub.
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
