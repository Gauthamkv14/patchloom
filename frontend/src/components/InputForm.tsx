import React, { useState } from 'react';
import { ContributorProfile } from '../types';

interface InputFormProps {
  onSubmit: (repoUrl: string, profile: ContributorProfile, isDemo: boolean) => void;
  isLoading: boolean;
}

export const InputForm: React.FC<InputFormProps> = ({ onSubmit, isLoading }) => {
  const [repoUrl, setRepoUrl] = useState('https://github.com/psf/requests');
  const [skillsStr, setSkillsStr] = useState('python, testing, requests');
  const [languagesStr, setLanguagesStr] = useState('python');
  const [experienceLevel, setExperienceLevel] = useState<'beginner' | 'intermediate' | 'advanced'>('beginner');
  const [availableHours, setAvailableHours] = useState<number>(3);
  const [learningGoal, setLearningGoal] = useState('Understand how HTTP connection pooling is handled');
  const [demo, setDemo] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;

    const skills = skillsStr
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const preferred_languages = languagesStr
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const profile: ContributorProfile = {
      skills: skills.length > 0 ? skills : ['python'],
      preferred_languages,
      experience_level: experienceLevel,
      available_hours: Number(availableHours) || 3,
      learning_goal: learningGoal.trim() || undefined,
    };

    onSubmit(repoUrl.trim(), profile, demo);
  };

  return (
    <form className="card form-card" onSubmit={handleSubmit}>
      <h2>Analyze Public Repository</h2>
      <p className="form-description">
        Provide a canonical GitHub repository URL and your contributor profile to evaluate actionable issues.
      </p>

      <div className="demo-presets-bar">
        <span className="presets-label">Demo Presets:</span>
        <button
          type="button"
          className="preset-btn"
          onClick={() => {
            setRepoUrl('https://github.com/psf/requests');
            setSkillsStr('python, documentation, testing');
            setLanguagesStr('python');
            setExperienceLevel('beginner');
            setAvailableHours(3);
            setLearningGoal('Understand HTTP timeouts and docs');
            setDemo(true);
          }}
          disabled={isLoading}
        >
          Scenario A: psf/requests (Good Fit)
        </button>
        <button
          type="button"
          className="preset-btn"
          onClick={() => {
            setRepoUrl('https://github.com/expressjs/express');
            setSkillsStr('javascript, express');
            setLanguagesStr('javascript');
            setExperienceLevel('intermediate');
            setAvailableHours(6);
            setLearningGoal('Debug router regex handling');
            setDemo(true);
          }}
          disabled={isLoading}
        >
          Scenario B: expressjs/express (Partial Evidence)
        </button>
        <button
          type="button"
          className="preset-btn"
          onClick={() => {
            setRepoUrl('https://github.com/encode/uvicorn');
            setSkillsStr('python, asgi');
            setLanguagesStr('python');
            setExperienceLevel('beginner');
            setAvailableHours(2);
            setLearningGoal('Documentation configuration');
            setDemo(true);
          }}
          disabled={isLoading}
        >
          Scenario C: encode/uvicorn (Deterministic Fallback)
        </button>
      </div>

      <div className="form-group">
        <label htmlFor="repoUrl">GitHub Repository URL (Canonical HTTPS)</label>
        <input
          id="repoUrl"
          type="text"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/OWNER/REPO"
          required
          disabled={isLoading}
        />
        <span className="field-hint">Accepts canonical public repositories (e.g. https://github.com/psf/requests)</span>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label htmlFor="skills">Your Skills (Comma-separated)</label>
          <input
            id="skills"
            type="text"
            value={skillsStr}
            onChange={(e) => setSkillsStr(e.target.value)}
            placeholder="e.g. python, react, sql, documentation"
            required
            disabled={isLoading}
          />
        </div>

        <div className="form-group">
          <label htmlFor="languages">Preferred Languages</label>
          <input
            id="languages"
            type="text"
            value={languagesStr}
            onChange={(e) => setLanguagesStr(e.target.value)}
            placeholder="e.g. python, javascript"
            disabled={isLoading}
          />
        </div>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label htmlFor="experience">Experience Level</label>
          <select
            id="experience"
            value={experienceLevel}
            onChange={(e) => setExperienceLevel(e.target.value as any)}
            disabled={isLoading}
          >
            <option value="beginner">Beginner (First-time open source contributor)</option>
            <option value="intermediate">Intermediate (A few prior contributions)</option>
            <option value="advanced">Advanced (Experienced open source developer)</option>
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="hours">Available Hours for PR</label>
          <input
            id="hours"
            type="number"
            min="0.5"
            max="100"
            step="0.5"
            value={availableHours}
            onChange={(e) => setAvailableHours(parseFloat(e.target.value))}
            required
            disabled={isLoading}
          />
        </div>
      </div>

      <div className="form-group">
        <label htmlFor="goal">Optional Learning Goal</label>
        <input
          id="goal"
          type="text"
          value={learningGoal}
          onChange={(e) => setLearningGoal(e.target.value)}
          placeholder="e.g. Learn how documentation tests are structured"
          disabled={isLoading}
        />
      </div>

      <div className="form-footer">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={demo}
            onChange={(e) => setDemo(e.target.checked)}
            disabled={isLoading}
          />
          <span>Use Offline Demo / Fixture Mode</span>
        </label>

        <button type="submit" disabled={isLoading} className="submit-btn">
          {isLoading ? 'Analyzing Repository...' : 'Analyze Repository'}
        </button>
      </div>
    </form>
  );
};
