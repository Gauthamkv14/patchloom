import React, { useState } from 'react';
import { RepositoryIntelligenceReport } from '../types';

interface RepoIntelligenceViewProps {
  intelligence: RepositoryIntelligenceReport;
}

type TabType = 'overview' | 'entry_points' | 'tests' | 'docs' | 'modules';

export const RepoIntelligenceView: React.FC<RepoIntelligenceViewProps> = ({ intelligence }) => {
  const [activeTab, setActiveTab] = useState<TabType>('overview');

  const getEvidenceBadge = (status: string) => {
    switch (status) {
      case 'verified':
        return <span className="badge badge-verified">Verified</span>;
      case 'unknown':
        return <span className="badge badge-unknown">Unknown</span>;
      case 'inference':
      default:
        return <span className="badge badge-inference">Inference</span>;
    }
  };

  const getConfidenceBadge = (confidence: string) => {
    return confidence === 'detected' || confidence === 'high' ? (
      <span className="badge badge-verified">{confidence}</span>
    ) : (
      <span className="badge badge-inference">{confidence}</span>
    );
  };

  return (
    <div className="card intelligence-card">
      <div className="intelligence-header">
        <div className="intelligence-title-row">
          <div>
            <h3>Repository Intelligence & Architecture</h3>
            <p className="section-subtitle">
              Deterministic, evidence-grounded structural analysis for {intelligence.repo_owner}/{intelligence.repo_name}
            </p>
          </div>
          <div className="intelligence-meta-badges">
            <span className="stat-pill">
              Project: {intelligence.project_type.replace(/_/g, ' ')}
            </span>
            <span className="stat-pill">
              Structure: {intelligence.structure_type.replace(/_/g, ' ')}
            </span>
            <span className="stat-pill">
              Inspected: {intelligence.inspected_paths_count} files
            </span>
            {getEvidenceBadge(intelligence.evidence.status)}
          </div>
        </div>

        {intelligence.tree_truncated && (
          <div className="warning-banner" style={{ marginTop: '0.75rem', marginBottom: '0.75rem' }}>
            ⚠️ Repository file tree was truncated due to scale limits (400 paths retained). Some structural findings may be incomplete.
          </div>
        )}

        <div className="intelligence-tabs">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            📊 Overview & Tech
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'entry_points' ? 'active' : ''}`}
            onClick={() => setActiveTab('entry_points')}
          >
            🚪 Entry Points ({intelligence.entry_points.length})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'tests' ? 'active' : ''}`}
            onClick={() => setActiveTab('tests')}
          >
            🧪 Tests & CI
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'docs' ? 'active' : ''}`}
            onClick={() => setActiveTab('docs')}
          >
            📖 Documentation
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'modules' ? 'active' : ''}`}
            onClick={() => setActiveTab('modules')}
          >
            🧩 Modules ({intelligence.modules.length})
          </button>
        </div>
      </div>

      <div className="intelligence-tab-content">
        {/* TAB 1: OVERVIEW */}
        {activeTab === 'overview' && (
          <div className="tab-pane">
            <div className="intel-section">
              <h4>Languages & Classification</h4>
              <div className="intel-grid">
                <div className="intel-cell">
                  <strong>Primary Language:</strong> {intelligence.languages.primary || 'Not detected'}
                  {intelligence.languages.secondary.length > 0 && (
                    <span style={{ display: 'block', marginTop: '0.25rem', color: '#6b7280' }}>
                      Secondary: {intelligence.languages.secondary.join(', ')}
                    </span>
                  )}
                </div>
                <div className="intel-cell">
                  <strong>Project Type:</strong> {intelligence.project_type.replace(/_/g, ' ')}
                  <p style={{ marginTop: '0.25rem', fontSize: '0.875rem', color: '#4b5563' }}>
                    {intelligence.project_type_rationale}
                  </p>
                </div>
              </div>
            </div>

            <div className="intel-section">
              <h4>Identified Technologies & Frameworks ({intelligence.technologies.length})</h4>
              {intelligence.technologies.length === 0 ? (
                <p className="empty-text">No standard frameworks or specialized libraries recognized from manifests or file patterns.</p>
              ) : (
                <div className="tech-tags-grid">
                  {intelligence.technologies.map((t, i) => (
                    <div key={i} className="tech-card">
                      <div className="tech-card-header">
                        <span className="tech-name">{t.name}</span>
                        {getConfidenceBadge(t.confidence)}
                      </div>
                      <span className="tech-cat">{t.category}</span>
                      <span className="tech-source">Source: {t.source}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="intel-section">
              <h4>Manifests & Configuration Files</h4>
              <div className="intel-grid">
                <div className="intel-cell">
                  <strong>Package Managers:</strong>{' '}
                  {intelligence.package_managers.length > 0
                    ? intelligence.package_managers.join(', ')
                    : 'None identified'}
                </div>
                <div className="intel-cell">
                  <strong>Dependency Manifests:</strong>{' '}
                  {intelligence.manifest_files.length > 0
                    ? intelligence.manifest_files.join(', ')
                    : 'None identified'}
                </div>
                {intelligence.configuration_files.length > 0 && (
                  <div className="intel-cell" style={{ gridColumn: '1 / -1' }}>
                    <strong>Key Toolchain Configs:</strong>{' '}
                    {intelligence.configuration_files.join(', ')}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: ENTRY POINTS */}
        {activeTab === 'entry_points' && (
          <div className="tab-pane">
            <div className="intel-section">
              <h4>Identified Entry Points & Root Exporters ({intelligence.entry_points.length})</h4>
              <p className="intel-desc">
                Files identified deterministically through structural patterns, export conventions, and manifest declarations.
              </p>
              {intelligence.entry_points.length === 0 ? (
                <p className="empty-text">No standard application or module entry points detected.</p>
              ) : (
                <div className="entry-points-list">
                  {intelligence.entry_points.map((ep, i) => (
                    <div key={i} className="entry-point-item">
                      <div className="ep-header">
                        <code>{ep.path}</code>
                        <div className="ep-badges">
                          <span className="badge ep-kind-badge">{ep.kind}</span>
                          {getConfidenceBadge(ep.confidence)}
                        </div>
                      </div>
                      <p className="ep-reason">{ep.reason}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: TESTS & CI */}
        {activeTab === 'tests' && (
          <div className="tab-pane">
            <div className="intel-section">
              <div className="section-status-header">
                <h4>Test Infrastructure</h4>
                {intelligence.test_profile.status === 'detected' && (
                  <span className="badge badge-verified">Detected</span>
                )}
                {intelligence.test_profile.status === 'not_detected' && (
                  <span className="badge badge-unknown">Not Detected</span>
                )}
                {intelligence.test_profile.status === 'unknown' && (
                  <span className="badge badge-unknown">Unknown (Truncated)</span>
                )}
              </div>

              <div className="intel-grid">
                <div className="intel-cell">
                  <strong>Test Frameworks:</strong>{' '}
                  {intelligence.test_profile.frameworks.length > 0
                    ? intelligence.test_profile.frameworks.join(', ')
                    : 'None identified'}
                </div>
                <div className="intel-cell">
                  <strong>Test Directories:</strong>{' '}
                  {intelligence.test_profile.test_directories.length > 0
                    ? intelligence.test_profile.test_directories.join(', ')
                    : 'None'}
                </div>
                <div className="intel-cell">
                  <strong>Identified Test Files:</strong> {intelligence.test_profile.test_file_count} file(s)
                </div>
                <div className="intel-cell">
                  <strong>CI Automation:</strong>{' '}
                  {intelligence.test_profile.ci_configuration?.value?.status === 'detected'
                    ? 'Detected (GitHub Actions / Workflows)'
                    : 'Not Detected'}
                </div>
              </div>

              {intelligence.test_profile.likely_commands.length > 0 && (
                <div className="test-cmds-box">
                  <strong>Likely Test Commands (Documented / Configured):</strong>
                  <ul>
                    {intelligence.test_profile.likely_commands.map((cmd, i) => (
                      <li key={i}>
                        <code>{cmd}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="limitations-box">
                <strong>Test Analysis Limitations:</strong>
                <ul>
                  {intelligence.test_profile.limitations.map((lim, i) => (
                    <li key={i}>{lim}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: DOCUMENTATION */}
        {activeTab === 'docs' && (
          <div className="tab-pane">
            <div className="intel-section">
              <h4>Documentation Profile</h4>
              {intelligence.documentation_profile.project_purpose && (
                <div className="doc-purpose-box">
                  <strong>Project Purpose:</strong>
                  <p>{intelligence.documentation_profile.project_purpose}</p>
                </div>
              )}

              <div className="intel-grid" style={{ marginTop: '1rem' }}>
                <div className="intel-cell">
                  <strong>README:</strong>{' '}
                  {intelligence.documentation_profile.has_readme ? '✓ Present' : '✗ Missing'}
                </div>
                <div className="intel-cell">
                  <strong>CONTRIBUTING:</strong>{' '}
                  {intelligence.documentation_profile.has_contributing ? '✓ Present' : '✗ Missing'}
                </div>
              </div>

              {intelligence.documentation_profile.setup_instructions && (
                <div className="doc-section-card" style={{ marginTop: '1rem' }}>
                  <strong>Setup & Installation:</strong>
                  <p>{intelligence.documentation_profile.setup_instructions}</p>
                </div>
              )}

              {intelligence.documentation_profile.test_instructions && (
                <div className="doc-section-card" style={{ marginTop: '0.75rem' }}>
                  <strong>Testing Guidelines:</strong>
                  <p>{intelligence.documentation_profile.test_instructions}</p>
                </div>
              )}

              {intelligence.documentation_profile.docs.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <h5>Inspected Documentation Files ({intelligence.documentation_profile.docs.length})</h5>
                  <div className="doc-files-grid">
                    {intelligence.documentation_profile.docs.map((doc, i) => (
                      <div key={i} className="doc-file-card">
                        <code>{doc.path}</code>
                        <span className="badge ep-kind-badge">{doc.doc_type}</span>
                        {doc.extracted_purpose && (
                          <p style={{ marginTop: '0.25rem', fontSize: '0.85rem', color: '#4b5563' }}>
                            {doc.extracted_purpose}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 5: MODULES */}
        {activeTab === 'modules' && (
          <div className="tab-pane">
            <div className="intel-section">
              <h4>Partitioned Repository Modules ({intelligence.modules.length})</h4>
              <p className="intel-desc">
                High-level functional components inferred from repository directory structure, responsibility heuristics, and entry files.
              </p>
              {intelligence.modules.length === 0 ? (
                <p className="empty-text">No distinct modular components partitioned.</p>
              ) : (
                <div className="modules-grid">
                  {intelligence.modules.map((mod, i) => (
                    <div key={i} className="module-card">
                      <div className="module-card-header">
                        <div>
                          <strong className="module-name">{mod.name}</strong>
                          <span className="module-path">({mod.root_path})</span>
                        </div>
                        <div className="module-badges">
                          <span className="badge ep-kind-badge">{mod.component_type.replace(/_/g, ' ')}</span>
                          {getConfidenceBadge(mod.confidence)}
                        </div>
                      </div>
                      <p className="module-resp">{mod.likely_responsibility}</p>
                      <div className="module-file-stats">
                        <span>{mod.file_count} file(s) in component</span>
                        {mod.key_entry_files.length > 0 && (
                          <div className="module-entries">
                            <strong>Key Files:</strong>{' '}
                            {mod.key_entry_files.map((kf, ki) => (
                              <code key={ki}>{kf}</code>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
