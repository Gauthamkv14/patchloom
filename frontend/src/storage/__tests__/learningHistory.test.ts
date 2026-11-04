import test from 'node:test';
import assert from 'node:assert';
import {
  LearningHistoryStorageAdapter,
  generateUUID,
  parseRepoOwnerAndName,
} from '../indexedDb.ts';
import {
  SOFT_SESSION_LIMIT,
} from '../../types/learningHistory.ts';
import type {
  LearningSessionRecord,
  M2LearningSnapshot,
  M3GuidedSnapshot,
  M4VerificationSnapshot,
} from '../../types/learningHistory.ts';
import { DEMO_HISTORY_SESSIONS } from '../demoHistoryFixture.ts';

test('Session UUID generation creates valid UUID format', () => {
  const uuid1 = generateUUID();
  const uuid2 = generateUUID();
  assert.ok(uuid1);
  assert.ok(uuid2);
  assert.notStrictEqual(uuid1, uuid2);
  // Match standard 8-4-4-4-12 hex UUID pattern
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  assert.match(uuid1, uuidRegex);
  assert.match(uuid2, uuidRegex);
});

test('parseRepoOwnerAndName parses various URL formats', () => {
  const r1 = parseRepoOwnerAndName('https://github.com/psf/requests');
  assert.strictEqual(r1.owner, 'psf');
  assert.strictEqual(r1.name, 'requests');

  const r2 = parseRepoOwnerAndName('https://github.com/expressjs/express/');
  assert.strictEqual(r2.owner, 'expressjs');
  assert.strictEqual(r2.name, 'express');

  const r3 = parseRepoOwnerAndName('owner/repo');
  assert.strictEqual(r3.owner, 'owner');
  assert.strictEqual(r3.name, 'repo');
});

test('Session creation stores independent sessions without collision', async () => {
  const storage = new LearningHistoryStorageAdapter();

  const s1 = await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 6542,
    issueTitle: 'Custom SSL context',
    isDemo: false,
  });

  const s2 = await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 6542,
    issueTitle: 'Custom SSL context (Second Attempt)',
    isDemo: false,
  });

  assert.notStrictEqual(s1.sessionId, s2.sessionId);

  const fetched1 = await storage.getSession(s1.sessionId);
  const fetched2 = await storage.getSession(s2.sessionId);

  assert.ok(fetched1);
  assert.ok(fetched2);
  assert.strictEqual(fetched1.issueTitle, 'Custom SSL context');
  assert.strictEqual(fetched2.issueTitle, 'Custom SSL context (Second Attempt)');
});

test('findActiveSession retrieves latest active session for repo and issue', async () => {
  const storage = new LearningHistoryStorageAdapter();

  await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 100,
    issueTitle: 'First session',
    isDemo: false,
  });

  const latest = await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 100,
    issueTitle: 'Second active session',
    isDemo: false,
  });

  const found = await storage.findActiveSession('https://github.com/psf/requests', 100, false);
  assert.ok(found);
  assert.strictEqual(found.sessionId, latest.sessionId);
  assert.strictEqual(found.issueTitle, 'Second active session');
});

test('M2 Snapshot: persists learning brief and checklist progress', async () => {
  const storage = new LearningHistoryStorageAdapter();
  const session = await storage.createSession({
    repoUrl: 'https://github.com/encode/uvicorn',
    issueNumber: 1820,
    issueTitle: 'ASGI graceful shutdown',
    isDemo: false,
  });

  const m2Snapshot: M2LearningSnapshot = {
    brief: {
      issue_number: 1820,
      issue_title: 'ASGI graceful shutdown',
      issue_url: 'https://github.com/encode/uvicorn/issues/1820',
      repo_url: 'https://github.com/encode/uvicorn',
      experience_level: 'intermediate',
      explanation: {
        summary: 'Handle worker shutdown timeout cleanly',
        problem_description: 'Tasks may hang indefinitely if connection does not terminate',
        expected_outcome: 'Timeout cancels hanging tasks after grace period',
        explicit_requirements: [],
        constraints_and_conditions: [],
        ambiguities_and_unanswered_questions: [],
        experience_adaptation_note: 'Focus on ASGI lifespan protocol.',
      },
      requirements: [],
      relevant_modules: [],
      investigation_targets: [
        {
          path: 'uvicorn/server.py',
          why_relevant: 'Manages server lifespan',
          what_to_inspect: 'Server loop',
          kind: 'detected',
          evidence: {
            status: 'verified',
            source: 'file_tree',
            observed_at: '2026-11-04T00:00:00Z',
            detail: 'Server loop',
          },
        },
      ],
      related_tests_and_docs: [],
      concepts: [
        {
          name: 'Lifespan Protocol',
          explanation: 'ASGI specification for startup and shutdown events',
          why_it_matters: 'Ensures background workers terminate',
          prerequisites: [],
          learning_order: 1,
          difficulty: 'intermediate',
        },
      ],
      learning_objectives: [],
      readiness_checklist: [
        {
          category: 'problem_understanding',
          item: 'Understand ASGI lifespan state transitions',
          guidance: 'Lifespan shutdown message protocol',
        },
      ],
      unresolved_questions: [],
      ai_status: 'complete',
      warnings: [],
      checked_at: '2026-11-04T00:00:00Z',
      evidence: {
        status: 'verified',
        source: 'local_rule',
        observed_at: '2026-11-04T00:00:00Z',
        detail: 'Brief generation',
      },
    },
    checkedChecklistKeys: { 'chk-0': true },
    completedChecklistCount: 1,
    totalChecklistCount: 1,
    savedAt: '2026-11-04T00:05:00Z',
  };

  const updated = await storage.updateSessionM2Snapshot(session.sessionId, m2Snapshot);
  assert.strictEqual(updated.lastActivePillar, 'm2_learn');
  assert.ok(updated.m2Snapshot);
  assert.strictEqual(updated.m2Snapshot.checkedChecklistKeys['chk-0'], true);

  // Check honest metrics
  assert.ok(updated.metrics.encounteredConcepts.includes('Lifespan Protocol'));
  assert.ok(updated.metrics.userMarkedUnderstanding.includes('Understand ASGI lifespan state transitions'));
  assert.ok(updated.metrics.filesTouched.includes('uvicorn/server.py'));
});

test('M3 Snapshot: persists guided steps, hint reveals, and updates metrics', async () => {
  const storage = new LearningHistoryStorageAdapter();
  const session = await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 6542,
    issueTitle: 'Custom SSL context',
    isDemo: false,
  });

  const m3Snapshot: M3GuidedSnapshot = {
    plan: {
      issue_number: 6542,
      issue_title: 'Custom SSL context',
      repo_url: 'https://github.com/psf/requests',
      experience_level: 'intermediate',
      overview: 'Step by step roadmap',
      steps: [
        {
          id: 'step-1',
          title: 'Update HTTPAdapter init signature',
          objective: 'Add ssl_context parameter',
          files_to_modify: ['requests/adapters.py'],
          expected_outcome: 'Attribute recorded',
          hints: [{ level: 1, guidance: 'Add to kwargs' }],
          alternative_considerations: '',
          verification: 'Inspect self.ssl_context',
        },
      ],
      alternative_approaches: [],
      ai_status: 'complete',
      warnings: [],
      checked_at: '2026-11-04T00:00:00Z',
      evidence: {
        status: 'verified',
        source: 'local_rule',
        observed_at: '2026-11-04T00:00:00Z',
        detail: 'Plan generated',
      },
    },
    activeStepIndex: 0,
    stepStatuses: { 'step-1': 'completed' },
    revealedHints: { 'step-1-0': true },
    expandedPatches: {},
    completedStepsCount: 1,
    totalStepsCount: 1,
    savedAt: '2026-11-04T00:10:00Z',
  };

  const updated = await storage.updateSessionM3Snapshot(session.sessionId, m3Snapshot);
  assert.strictEqual(updated.lastActivePillar, 'm3_guided');
  assert.strictEqual(updated.status, 'completed'); // Auto-completed when all steps done
  assert.ok(updated.metrics.completedSteps.includes('step-1'));
  assert.ok(updated.metrics.practicedConcepts.includes('Update HTTPAdapter init signature'));
  assert.ok(updated.metrics.practicedConcepts.includes('Update HTTPAdapter init signature (Hint 1)'));
});

test('M4 Snapshot: persists findings, regression risks, readiness, execution_unavailable and draft PR, strictly omits execution authorization', async () => {
  const storage = new LearningHistoryStorageAdapter();
  const session = await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 6542,
    issueTitle: 'Custom SSL context',
    isDemo: false,
  });

  const m4Snapshot: M4VerificationSnapshot = {
    report: {
      issue_number: 6542,
      issue_title: 'Custom SSL context',
      repo_url: 'https://github.com/psf/requests',
      parsed_diff: {
        files: [{ path: 'requests/adapters.py', change_type: 'modified', lines_added: 3, lines_removed: 1, detected_symbols: ['HTTPAdapter'] }],
        total_files: 1,
        lines_added: 3,
        lines_removed: 1,
        raw_diff_sample: 'diff --git a/requests/adapters.py ...',
        is_truncated: false,
        warnings: [],
      },
      roadmap_alignment_summary: 'Aligned',
      potentially_unrelated_files: [],
      discovered_tests: [],
      review_findings: [
        {
          finding_id: 'rf-1',
          severity: 'medium',
          category: 'error_handling',
          title: 'Handle null SSL context cleanly',
          explanation: 'Pass default context when none supplied',
          evidence: 'adapters.py:102',
          file_path: 'requests/adapters.py',
          why_it_matters: 'Prevents TypeError',
          suggested_action: 'Guard with if check',
          confidence: 'high',
        },
      ],
      regression_risks: [
        {
          risk_id: 'rr-1',
          affected_module_or_file: 'requests/adapters.py',
          risk_type: 'potentially_affected',
          evidence: 'init_poolmanager kwargs',
          potential_impact: 'Pool parameter collision',
          suggested_verification: 'Run adapter tests',
          confidence: 'medium',
        },
      ],
      readiness: {
        status: 'needs_attention',
        summary: 'Review finding needs attention',
        outstanding_items: ['Check default SSL context'],
        checklist_status: { 'Tests passing': false, 'Diff reviewed': true },
      },
      ai_status: 'complete',
      warnings: [],
      evidence: {
        status: 'verified',
        source: 'local_rule',
        observed_at: '2026-11-04T00:00:00Z',
        detail: 'Report generated',
      },
      checked_at: '2026-11-04T00:00:00Z',
    },
    hasRawDiffStored: false,
    rawDiffText: 'diff --git a/requests/adapters.py b/requests/adapters.py\n...',
    testExecutionResult: {
      status: 'execution_unavailable',
      runner: 'pytest',
      command: 'pytest tests/test_adapters.py',
      duration_seconds: 0.0,
      exit_code: 0,
      stdout_bounded: '',
      stderr_bounded: 'Docker execution is unavailable: prepared workspace not provisioned.',
      failure_details: [],
      failure_locations: [],
      ai_likely_causes: [],
      ai_suggested_next_steps: ['Run tests locally'],
      simulated: false,
      executed_at: '2026-11-04T00:15:00Z',
    },
    draftPR: {
      title: 'Support custom SSL context',
      summary_of_changes: 'Passed ssl_context down',
      problem_addressed: 'Hardcoded SSL configuration',
      implementation_overview: 'Modified HTTPAdapter',
      tests_performed: {},
      known_limitations: [],
      remaining_concerns: [],
      manual_verification_checklist: [],
    },
    savedAt: '2026-11-04T00:15:00Z',
  };

  // Opt-in diff = false (default)
  const updatedDefault = await storage.updateSessionM4Snapshot(session.sessionId, m4Snapshot, false);
  assert.strictEqual(updatedDefault.m4Snapshot?.hasRawDiffStored, false);
  assert.strictEqual(updatedDefault.m4Snapshot?.rawDiffText, undefined);

  // Genuinely verifies review findings, regression risks, readiness, and test execution result
  assert.strictEqual(updatedDefault.m4Snapshot?.report.review_findings.length, 1);
  assert.strictEqual(updatedDefault.m4Snapshot?.report.review_findings[0].finding_id, 'rf-1');
  assert.strictEqual(updatedDefault.m4Snapshot?.report.regression_risks.length, 1);
  assert.strictEqual(updatedDefault.m4Snapshot?.report.readiness.status, 'needs_attention');
  assert.strictEqual(updatedDefault.m4Snapshot?.testExecutionResult?.status, 'execution_unavailable');
  assert.strictEqual(updatedDefault.m4Snapshot?.draftPR?.title, 'Support custom SSL context');

  // Verify that NO authorization flag exists anywhere in the stored snapshot
  const rawJson = JSON.stringify(updatedDefault);
  assert.strictEqual(rawJson.includes('"authorized"'), false);
  assert.strictEqual(rawJson.includes('"authorizedExecution"'), false);

  // Opt-in diff = true
  const updatedOptIn = await storage.updateSessionM4Snapshot(session.sessionId, m4Snapshot, true);
  assert.strictEqual(updatedOptIn.m4Snapshot?.hasRawDiffStored, true);
  assert.strictEqual(updatedOptIn.m4Snapshot?.rawDiffText, m4Snapshot.rawDiffText);
});

test('Storage Mode & Unavailable Detection: Node tests exercise in-memory fallback with clear warning', async () => {
  const storage = new LearningHistoryStorageAdapter();
  // In Node.js environment without window.indexedDB, adapter safely identifies memory mode
  assert.strictEqual(storage.getStorageMode(), 'memory');
  assert.strictEqual(storage.isPersistent(), false);

  const status = await storage.checkStorageStatus();
  assert.strictEqual(status.mode, 'memory');
  assert.strictEqual(status.persistent, false);
  assert.ok(status.warning);
  assert.ok(status.warning.includes('temporary'));
});

test('Demo Isolation: demo sessions never merge into non-demo profile', async () => {
  const storage = new LearningHistoryStorageAdapter();

  // Create 1 real session
  const realSession = await storage.createSession({
    repoUrl: 'https://github.com/my-org/my-repo',
    issueNumber: 1,
    issueTitle: 'Real Bug Fix',
    isDemo: false,
  });
  await storage.updateSessionM2Snapshot(realSession.sessionId, {
    brief: {
      issue_number: 1,
      issue_title: 'Real Bug Fix',
      issue_url: 'https://github.com/my-org/my-repo/issues/1',
      repo_url: 'https://github.com/my-org/my-repo',
      experience_level: 'beginner',
      explanation: { summary: 'Real summary', problem_description: 'Real problem', expected_outcome: 'Real outcome', explicit_requirements: [], constraints_and_conditions: [], ambiguities_and_unanswered_questions: [], experience_adaptation_note: '' },
      requirements: [],
      relevant_modules: [],
      investigation_targets: [{ path: 'main.py', why_relevant: 'entry', what_to_inspect: 'main()', kind: 'detected', evidence: { status: 'verified', source: 'file_tree', observed_at: 'now', detail: '' } }],
      related_tests_and_docs: [],
      concepts: [{ name: 'Real Production Concept', explanation: 'def', why_it_matters: 'why', prerequisites: [], learning_order: 1, difficulty: 'beginner' }],
      learning_objectives: [],
      readiness_checklist: [],
      unresolved_questions: [],
      ai_status: 'complete',
      warnings: [],
      checked_at: 'now',
      evidence: { status: 'verified', source: 'rule', observed_at: 'now', detail: '' },
    },
    checkedChecklistKeys: {},
    completedChecklistCount: 0,
    totalChecklistCount: 0,
    savedAt: 'now',
  });

  // Create 1 demo session
  const demoSession = await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 6542,
    issueTitle: 'Demo Bug Fix',
    isDemo: true,
  });
  await storage.updateSessionM2Snapshot(demoSession.sessionId, {
    brief: {
      issue_number: 6542,
      issue_title: 'Demo Bug Fix',
      issue_url: 'https://github.com/psf/requests/issues/6542',
      repo_url: 'https://github.com/psf/requests',
      experience_level: 'intermediate',
      explanation: { summary: 'Demo summary', problem_description: 'Demo problem', expected_outcome: 'Demo outcome', explicit_requirements: [], constraints_and_conditions: [], ambiguities_and_unanswered_questions: [], experience_adaptation_note: '' },
      requirements: [],
      relevant_modules: [],
      investigation_targets: [],
      related_tests_and_docs: [],
      concepts: [{ name: 'Demo Isolated Concept', explanation: 'def', why_it_matters: 'why', prerequisites: [], learning_order: 1, difficulty: 'intermediate' }],
      learning_objectives: [],
      readiness_checklist: [],
      unresolved_questions: [],
      ai_status: 'complete',
      warnings: [],
      checked_at: 'now',
      evidence: { status: 'verified', source: 'rule', observed_at: 'now', detail: '' },
    },
    checkedChecklistKeys: {},
    completedChecklistCount: 0,
    totalChecklistCount: 0,
    savedAt: 'now',
  });

  // Calculate real profile
  const realProfile = await storage.recalculateGrowthProfile(false);
  assert.strictEqual(realProfile.isDemo, false);
  assert.strictEqual(realProfile.totalSessions, 1);
  assert.deepStrictEqual(realProfile.distinctRepositories, ['https://github.com/my-org/my-repo']);
  assert.ok(realProfile.conceptsEncountered['Real Production Concept']);
  assert.strictEqual(realProfile.conceptsEncountered['Demo Isolated Concept'], undefined);

  // Calculate demo profile
  const demoProfile = await storage.recalculateGrowthProfile(true);
  assert.strictEqual(demoProfile.isDemo, true);
  assert.strictEqual(demoProfile.totalSessions, 1);
  assert.deepStrictEqual(demoProfile.distinctRepositories, ['https://github.com/psf/requests']);
  assert.ok(demoProfile.conceptsEncountered['Demo Isolated Concept']);
  assert.strictEqual(demoProfile.conceptsEncountered['Real Production Concept'], undefined);
});

test('Soft Quota: warns at 50 sessions', async () => {
  const storage = new LearningHistoryStorageAdapter();

  const quotaBefore = await storage.checkStorageQuota();
  assert.strictEqual(quotaBefore.warning, false);
  assert.strictEqual(quotaBefore.count, 0);

  // Add 50 sessions
  for (let i = 0; i < SOFT_SESSION_LIMIT; i++) {
    await storage.createSession({
      repoUrl: `https://github.com/org/repo-${i}`,
      issueNumber: i + 1,
      issueTitle: `Issue ${i + 1}`,
      isDemo: false,
    });
  }

  const quotaAfter = await storage.checkStorageQuota();
  assert.strictEqual(quotaAfter.count, 50);
  assert.strictEqual(quotaAfter.warning, true);
  assert.ok(quotaAfter.message?.includes('reached 50 learning sessions'));
});

test('Export and Import: roundtrips correctly', async () => {
  const storage = new LearningHistoryStorageAdapter();
  await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 6542,
    issueTitle: 'Custom SSL context',
    isDemo: false,
  });

  const exportJson = await storage.exportHistoryJson();
  assert.ok(exportJson);

  // Import into a fresh store
  const targetStorage = new LearningHistoryStorageAdapter();
  const importResult = await targetStorage.importHistoryJson(exportJson);

  assert.strictEqual(importResult.success, true);
  assert.strictEqual(importResult.importedSessionsCount, 1);
  assert.strictEqual(importResult.skippedSessionsCount, 0);

  const imported = await targetStorage.listSessions();
  assert.strictEqual(imported.length, 1);
  assert.strictEqual(imported[0].issueNumber, 6542);
});

test('Import Validation: rejects malformed JSON, wrong format, and oversized payloads', async () => {
  const storage = new LearningHistoryStorageAdapter();

  // 1. Malformed JSON
  const resMalformed = await storage.importHistoryJson('{ this is not json }');
  assert.strictEqual(resMalformed.success, false);
  assert.ok(resMalformed.errors[0].includes('Malformed JSON'));

  // 2. Wrong format header
  const resWrongFormat = await storage.importHistoryJson(JSON.stringify({ format: 'other_format', sessions: [] }));
  assert.strictEqual(resWrongFormat.success, false);
  assert.ok(resWrongFormat.errors[0].includes('Unrecognized format'));

  // 3. Oversized payload (> 5MB)
  const hugeString = 'x'.repeat(5 * 1024 * 1024 + 100);
  const resHuge = await storage.importHistoryJson(hugeString);
  assert.strictEqual(resHuge.success, false);
  assert.ok(resHuge.errors[0].includes('exceeds maximum allowed 5 MB'));
});

test('clearAllSessions purges all records', async () => {
  const storage = new LearningHistoryStorageAdapter();
  await storage.createSession({
    repoUrl: 'https://github.com/psf/requests',
    issueNumber: 6542,
    issueTitle: 'Test session',
    isDemo: false,
  });

  const before = await storage.listSessions();
  assert.strictEqual(before.length, 1);

  await storage.clearAllSessions();

  const after = await storage.listSessions();
  assert.strictEqual(after.length, 0);
});

test('Demo Fixtures: realistic demo sessions are valid', () => {
  assert.strictEqual(DEMO_HISTORY_SESSIONS.length, 2);
  const requests = DEMO_HISTORY_SESSIONS[0];
  assert.strictEqual(requests.issueNumber, 6542);
  assert.strictEqual(requests.isDemo, true);
  assert.strictEqual(requests.m2Snapshot?.completedChecklistCount, 1);
  assert.strictEqual(requests.m3Snapshot?.completedStepsCount, 1);
  assert.ok(requests.m4Snapshot?.report);
  // Ensure no authorized field exists in demo fixture
  assert.strictEqual(JSON.stringify(requests).includes('"authorized"'), false);
});
