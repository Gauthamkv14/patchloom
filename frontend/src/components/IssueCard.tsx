import React, { useState } from 'react';
import { CandidateIssue } from '../types';

interface IssueCardProps {
  issue: CandidateIssue;
  rank: number;
  onSelectPlan: (issue: CandidateIssue) => void;
  isPlanningThis: boolean;
}

export const IssueCard: React.FC<IssueCardProps> = ({
  issue,
  rank,
  onSelectPlan,
  isPlanningThis,
}) => {
  const [expanded, setExpanded] = useState(false);

  const getBandClass = (band: string) => {
    switch (band) {
      case 'high':
        return 'band-high';
      case 'medium':
        return 'band-medium';
      case 'low':
      default:
        return 'band-low';
    }
  };

  return (
    <div className={`card issue-card ${getBandClass(issue.viability_band)}`}>
      <div className="issue-header">
        <div className="issue-rank-title">
          <span className="rank-badge">#{rank}</span>
          <div className="title-and-link">
            <h3 className="issue-title">
              <a href={issue.url} target="_blank" rel="noopener noreferrer">
                #{issue.number}: {issue.title}
              </a>
            </h3>
            <div className="labels-row">
              {issue.labels.map((label, idx) => (
                <span key={idx} className="label-tag">
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="scores-container">
          {issue.final_score !== null && issue.final_score !== undefined && (
            <div className="score-box final-score">
              <span className="score-num">{issue.final_score}</span>
              <span className="score-label">Final Score</span>
            </div>
          )}

          {issue.fit_score !== null && issue.fit_score !== undefined && (
            <div className="score-box fit-score">
              <span className="score-num">{issue.fit_score}</span>
              <span className="score-label">AI Fit</span>
            </div>
          )}

          <div className={`score-box viability-score ${issue.viability_band}`}>
            <span className="score-num">{issue.viability_score}</span>
            <span className="score-label">Viability ({issue.viability_band})</span>
          </div>
        </div>
      </div>

      {issue.reason && (
        <div className="fit-summary">
          <span className="badge badge-inference">AI Assessment</span>
          <p className="reason-text">{issue.reason}</p>
        </div>
      )}

      <div className="card-actions">
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? '▲ Hide Signals & Evidence' : '▼ Inspect Signals & Evidence'}
        </button>

        <button
          type="button"
          className="btn-primary plan-btn"
          onClick={() => onSelectPlan(issue)}
          disabled={isPlanningThis}
        >
          {isPlanningThis ? 'Generating Plan...' : '📋 Plan First PR'}
        </button>
      </div>

      {expanded && (
        <div className="expanded-details">
          <div className="details-section">
            <h4>Verified GitHub Evidence</h4>
            <div className="signals-grid">
              <div className="signal-cell">
                <span className="badge badge-verified">Verified</span>
                <strong>Last Updated:</strong>{' '}
                {issue.signals.days_since_updated?.value !== undefined
                  ? `${issue.signals.days_since_updated.value} days ago`
                  : 'Unknown'}
              </div>

              <div className="signal-cell">
                <span className="badge badge-verified">Verified</span>
                <strong>Assignment:</strong>{' '}
                {issue.signals.is_assigned?.value ? 'Assigned' : 'Unassigned (Open for all)'}
              </div>

              <div className="signal-cell">
                <span
                  className={`badge ${
                    issue.signals.linked_pr?.status === 'verified'
                      ? 'badge-verified'
                      : issue.signals.linked_pr?.status === 'unknown'
                      ? 'badge-unknown'
                      : 'badge-inference'
                  }`}
                >
                  {issue.signals.linked_pr?.status || 'inference'}
                </span>
                <strong>Linked Open PR:</strong>{' '}
                {issue.signals.linked_pr?.value?.status === 'detected'
                  ? 'Detected (May already have PR)'
                  : 'None Detected'}
              </div>

              <div className="signal-cell">
                <span className="badge badge-verified">Verified</span>
                <strong>Maintainer Reply:</strong>{' '}
                {issue.signals.has_maintainer_reply?.value ? 'Yes (Active maintainer)' : 'None found'}
              </div>

              <div className="signal-cell">
                <span className="badge badge-inference">Inference</span>
                <strong>Setup Docs:</strong>{' '}
                {issue.signals.has_setup_guidance?.value ? 'Detected in README' : 'No setup guidance found'}
              </div>

              <div className="signal-cell">
                <span className="badge badge-verified">Verified</span>
                <strong>Comments:</strong> {issue.comments_count}
              </div>
            </div>
          </div>

          {(issue.matching_skills?.length > 0 || issue.skill_gaps?.length > 0) && (
            <div className="details-section">
              <h4>Skills Fit Breakdown</h4>
              <div className="skills-row">
                {issue.matching_skills.length > 0 && (
                  <div>
                    <span className="badge badge-inference">Matching Skills</span>
                    <div className="tags-list">
                      {issue.matching_skills.map((s, i) => (
                        <span key={i} className="skill-match-tag">
                          ✓ {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {issue.skill_gaps.length > 0 && (
                  <div>
                    <span className="badge badge-unknown">Skill Gaps</span>
                    <div className="tags-list">
                      {issue.skill_gaps.map((s, i) => (
                        <span key={i} className="skill-gap-tag">
                          ! {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {issue.likely_files && issue.likely_files.length > 0 && (
            <div className="details-section">
              <h4>Grounded File Targets (from Repository Tree)</h4>
              <ul className="file-targets-list">
                {issue.likely_files.map((file, i) => (
                  <li key={i}>
                    <code>{file}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {issue.risks && issue.risks.length > 0 && (
            <div className="details-section">
              <h4>Identified Risks & Inferences</h4>
              <ul className="risks-list">
                {issue.risks.map((risk, i) => (
                  <li key={i}>{risk}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
