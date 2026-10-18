import React from 'react';

export const EvidenceLegend: React.FC = () => {
  return (
    <div className="legend-container">
      <h3>Evidence & Scoring Legend</h3>
      <div className="legend-grid">
        <div className="legend-item">
          <span className="badge badge-verified">Verified Fact</span>
          <p>
            Confirmed via GitHub REST API (issue state, timestamps, comments, assignees, maintainer replies). Never guessed.
          </p>
        </div>
        <div className="legend-item">
          <span className="badge badge-inference">AI Assessment / Inference</span>
          <p>
            Gemma 4 model reasoning (contributor fit score, estimated hours, matching skills, likely files grounded in tree).
          </p>
        </div>
        <div className="legend-item">
          <span className="badge badge-unknown">Unknown / Not Checked</span>
          <p>
            Missing or unverified evidence (e.g. unqueried timeline, undocumented setup commands). Never fabricated into a false negative.
          </p>
        </div>
      </div>
      <div className="legend-formula">
        <strong>Scoring Formula:</strong> Final Score = <code>0.60 × Fit Score (AI) + 0.40 × Viability Score (Deterministic)</code>
      </div>
    </div>
  );
};
