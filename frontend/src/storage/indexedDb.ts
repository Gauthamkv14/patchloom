import {
  CURRENT_SCHEMA_VERSION,
  MAX_IMPORT_SIZE_BYTES,
  SOFT_SESSION_LIMIT,
} from '../types/learningHistory.ts';
import type {
  ContributorGrowthProfile,
  CreateSessionParams,
  ImportResult,
  LearningSessionRecord,
  M2LearningSnapshot,
  M3GuidedSnapshot,
  M4VerificationSnapshot,
  SessionFilter,
  SessionLearningMetrics,
  StorageExportPayload,
  StorageQuotaInfo,
} from '../types/learningHistory.ts';

const DB_NAME = 'patchloom_learning_db';
const DB_VERSION = 2;
const SESSIONS_STORE = 'learning_sessions';
const PROFILES_STORE = 'growth_profiles';

let lastTimestampMs = 0;

export function getMonotonicIsoTimestamp(): string {
  let now = Date.now();
  if (now <= lastTimestampMs) {
    now = lastTimestampMs + 1;
  }
  lastTimestampMs = now;
  return new Date(now).toISOString();
}

export function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function parseRepoOwnerAndName(repoUrl: string): { owner: string; name: string } {
  try {
    const parsed = new URL(repoUrl.trim());
    const segments = parsed.pathname.replace(/^\/+|\/+$/g, '').split('/');
    if (segments.length >= 2) {
      return { owner: segments[0], name: segments[1] };
    }
  } catch {
    // If not a full URL, attempt split
    const segments = repoUrl.trim().replace(/^\/+|\/+$/g, '').split('/');
    if (segments.length >= 2) {
      return { owner: segments[segments.length - 2], name: segments[segments.length - 1] };
    }
  }
  return { owner: 'unknown', name: 'unknown' };
}

// In-Memory fallback store for environments without IndexedDB (e.g. Node, private browsing)
class InMemoryStore {
  private sessions: Map<string, LearningSessionRecord> = new Map();
  private profiles: Map<string, ContributorGrowthProfile> = new Map();

  async getSession(id: string): Promise<LearningSessionRecord | null> {
    const record = this.sessions.get(id);
    return record ? JSON.parse(JSON.stringify(record)) : null;
  }

  async putSession(session: LearningSessionRecord): Promise<void> {
    this.sessions.set(session.sessionId, JSON.parse(JSON.stringify(session)));
  }

  async deleteSession(id: string): Promise<boolean> {
    return this.sessions.delete(id);
  }

  async getAllSessions(): Promise<LearningSessionRecord[]> {
    return Array.from(this.sessions.values()).map((s) => JSON.parse(JSON.stringify(s)));
  }

  async clearSessions(): Promise<void> {
    this.sessions.clear();
  }

  async getProfile(isDemo: boolean): Promise<ContributorGrowthProfile | null> {
    const p = this.profiles.get(String(isDemo));
    return p ? JSON.parse(JSON.stringify(p)) : null;
  }

  async putProfile(profile: ContributorGrowthProfile): Promise<void> {
    this.profiles.set(String(profile.isDemo), JSON.parse(JSON.stringify(profile)));
  }

  async clearAll(): Promise<void> {
    this.sessions.clear();
    this.profiles.clear();
  }
}

export class LearningHistoryStorageAdapter {
  private dbPromise: Promise<IDBDatabase> | null = null;
  private memoryStore: InMemoryStore | null = null;
  private isMemoryOnly = false;
  private customFactory?: IDBFactory;

  constructor(optionsOrFactory?: IDBFactory | { forceMemoryOnly?: boolean; customFactory?: IDBFactory | null } | null) {
    if (optionsOrFactory === null) {
      this.isMemoryOnly = true;
      this.memoryStore = new InMemoryStore();
      return;
    }
    if (optionsOrFactory && typeof optionsOrFactory === 'object' && 'forceMemoryOnly' in optionsOrFactory) {
      if (optionsOrFactory.forceMemoryOnly) {
        this.isMemoryOnly = true;
        this.memoryStore = new InMemoryStore();
        return;
      }
      this.customFactory = optionsOrFactory.customFactory || undefined;
    } else if (optionsOrFactory) {
      this.customFactory = optionsOrFactory as IDBFactory;
    }

    const factory = this.getFactory();
    if (!factory) {
      this.isMemoryOnly = true;
      this.memoryStore = new InMemoryStore();
    }
  }

  getFactory(): IDBFactory | undefined {
    if (this.customFactory) return this.customFactory;
    if (typeof indexedDB !== 'undefined') return indexedDB;
    if (typeof window !== 'undefined' && window.indexedDB) return window.indexedDB;
    return undefined;
  }

  getStorageMode(): 'indexeddb' | 'memory' {
    return this.isMemoryOnly ? 'memory' : 'indexeddb';
  }

  isPersistent(): boolean {
    return !this.isMemoryOnly;
  }

  async checkStorageStatus(): Promise<{ mode: 'indexeddb' | 'memory'; persistent: boolean; warning?: string }> {
    if (this.isMemoryOnly) {
      return {
        mode: 'memory',
        persistent: false,
        warning: 'Local IndexedDB storage is unavailable or running in-memory fallback. Session progress is temporary and will not persist after page reload.',
      };
    }

    try {
      await this.getDb();
      return {
        mode: 'indexeddb',
        persistent: true,
      };
    } catch {
      return {
        mode: 'memory',
        persistent: false,
        warning: 'Local IndexedDB storage failed to open. Session progress is temporary and will not persist after page reload.',
      };
    }
  }

  async closeDatabase(): Promise<void> {
    if (this.dbPromise) {
      try {
        const db = await this.dbPromise;
        db.close();
      } catch {
        // ignore
      }
      this.dbPromise = null;
    }
  }

  private getDb(): Promise<IDBDatabase> {
    if (this.isMemoryOnly) {
      return Promise.reject(new Error('Operating in memory-only mode'));
    }
    if (this.dbPromise) {
      return this.dbPromise;
    }

    const factory = this.getFactory();
    if (!factory) {
      this.isMemoryOnly = true;
      this.memoryStore = new InMemoryStore();
      return Promise.reject(new Error('IndexedDB not supported; switched to in-memory store'));
    }

    this.dbPromise = new Promise((resolve, reject) => {
      try {
        const request = factory.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = (event) => {
          const db = (event.target as IDBOpenDBRequest).result;

          if (!db.objectStoreNames.contains(SESSIONS_STORE)) {
            const sessionsStore = db.createObjectStore(SESSIONS_STORE, { keyPath: 'sessionId' });
            sessionsStore.createIndex('repoUrl', 'repoUrl', { unique: false });
            sessionsStore.createIndex('issueNumber', 'issueNumber', { unique: false });
            sessionsStore.createIndex('isDemo', 'isDemo', { unique: false });
            sessionsStore.createIndex('lastUpdatedAt', 'lastUpdatedAt', { unique: false });
            sessionsStore.createIndex('status', 'status', { unique: false });
          }

          if (db.objectStoreNames.contains(PROFILES_STORE)) {
            db.deleteObjectStore(PROFILES_STORE);
          }
          db.createObjectStore(PROFILES_STORE, { keyPath: 'profileKey' });
        };

        request.onsuccess = (event) => {
          const db = (event.target as IDBOpenDBRequest).result;
          resolve(db);
        };

        request.onerror = (event) => {
          console.warn('Failed to open IndexedDB, using in-memory store fallback:', request.error);
          this.isMemoryOnly = true;
          this.memoryStore = new InMemoryStore();
          reject((event.target as IDBOpenDBRequest).error);
        };
      } catch (err) {
        console.warn('Exception opening IndexedDB, falling back to memory store:', err);
        this.isMemoryOnly = true;
        this.memoryStore = new InMemoryStore();
        reject(err);
      }
    });

    return this.dbPromise;
  }

  // --- CRUD Operations ---

  async createSession(params: CreateSessionParams): Promise<LearningSessionRecord> {
    const { owner, name } = parseRepoOwnerAndName(params.repoUrl);
    const now = getMonotonicIsoTimestamp();

    const newSession: LearningSessionRecord = {
      sessionId: generateUUID(),
      schemaVersion: CURRENT_SCHEMA_VERSION,
      repoUrl: params.repoUrl,
      repoOwner: owner,
      repoName: name,
      issueNumber: params.issueNumber,
      issueTitle: params.issueTitle,
      isDemo: params.isDemo,
      status: 'active',
      startedAt: now,
      lastUpdatedAt: now,
      lastActivePillar: params.initialPillar || 'm2_learn',
      contributorProfile: params.profile || null,
      m2Snapshot: null,
      m3Snapshot: null,
      m4Snapshot: null,
      metrics: {
        encounteredConcepts: [],
        practicedConcepts: [],
        userMarkedUnderstanding: [],
        completedSteps: [],
        filesTouched: [],
      },
    };

    await this.putSession(newSession);
    return newSession;
  }

  async getSession(sessionId: string): Promise<LearningSessionRecord | null> {
    if (this.isMemoryOnly && this.memoryStore) {
      return this.memoryStore.getSession(sessionId);
    }

    try {
      const db = await this.getDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(SESSIONS_STORE, 'readonly');
        const store = tx.objectStore(SESSIONS_STORE);
        const req = store.get(sessionId);

        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
    } catch {
      if (this.memoryStore) {
        return this.memoryStore.getSession(sessionId);
      }
      return null;
    }
  }

  async putSession(session: LearningSessionRecord): Promise<void> {
    if (this.isMemoryOnly && this.memoryStore) {
      await this.memoryStore.putSession(session);
      return;
    }

    try {
      const db = await this.getDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(SESSIONS_STORE, 'readwrite');
        const store = tx.objectStore(SESSIONS_STORE);
        const req = store.put(session);

        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch {
      if (!this.memoryStore) this.memoryStore = new InMemoryStore();
      await this.memoryStore.putSession(session);
    }
  }

  async deleteSession(sessionId: string): Promise<boolean> {
    if (this.isMemoryOnly && this.memoryStore) {
      return this.memoryStore.deleteSession(sessionId);
    }

    try {
      const db = await this.getDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(SESSIONS_STORE, 'readwrite');
        const store = tx.objectStore(SESSIONS_STORE);
        const req = store.delete(sessionId);

        req.onsuccess = () => resolve(true);
        req.onerror = () => reject(req.error);
      });
    } catch {
      if (this.memoryStore) {
        return this.memoryStore.deleteSession(sessionId);
      }
      return false;
    }
  }

  async listSessions(filter?: SessionFilter): Promise<LearningSessionRecord[]> {
    let all: LearningSessionRecord[] = [];

    if (this.isMemoryOnly && this.memoryStore) {
      all = await this.memoryStore.getAllSessions();
    } else {
      try {
        const db = await this.getDb();
        all = await new Promise((resolve, reject) => {
          const tx = db.transaction(SESSIONS_STORE, 'readonly');
          const store = tx.objectStore(SESSIONS_STORE);
          const req = store.getAll();

          req.onsuccess = () => resolve(req.result || []);
          req.onerror = () => reject(req.error);
        });
      } catch {
        if (this.memoryStore) {
          all = await this.memoryStore.getAllSessions();
        }
      }
    }

    if (!filter) {
      return all.sort((a, b) => b.lastUpdatedAt.localeCompare(a.lastUpdatedAt));
    }

    return all
      .filter((s) => {
        if (filter.isDemo !== undefined && s.isDemo !== filter.isDemo) return false;
        if (filter.repoUrl && s.repoUrl.toLowerCase() !== filter.repoUrl.toLowerCase()) return false;
        if (filter.issueNumber !== undefined && s.issueNumber !== filter.issueNumber) return false;
        if (filter.status && s.status !== filter.status) return false;
        return true;
      })
      .sort((a, b) => b.lastUpdatedAt.localeCompare(a.lastUpdatedAt));
  }

  async findActiveSession(
    repoUrl: string,
    issueNumber: number,
    isDemo: boolean,
  ): Promise<LearningSessionRecord | null> {
    const sessions = await this.listSessions({
      repoUrl,
      issueNumber,
      isDemo,
      status: 'active',
    });
    return sessions.length > 0 ? sessions[0] : null;
  }

  // --- Snapshot Updaters with Metric Extraction ---

  async updateSessionM2Snapshot(
    sessionId: string,
    snapshot: M2LearningSnapshot,
  ): Promise<LearningSessionRecord> {
    const session = await this.getSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    session.m2Snapshot = snapshot;
    session.lastActivePillar = 'm2_learn';
    session.lastUpdatedAt = getMonotonicIsoTimestamp();

    // Recompute honest learning metrics
    const metrics = this.recomputeSessionMetrics(session);
    session.metrics = metrics;

    await this.putSession(session);
    return session;
  }

  async updateSessionM3Snapshot(
    sessionId: string,
    snapshot: M3GuidedSnapshot,
  ): Promise<LearningSessionRecord> {
    const session = await this.getSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    session.m3Snapshot = snapshot;
    session.lastActivePillar = 'm3_guided';
    session.lastUpdatedAt = getMonotonicIsoTimestamp();

    // Check completion status: if all steps completed, mark session completed
    if (snapshot.totalStepsCount > 0 && snapshot.completedStepsCount >= snapshot.totalStepsCount) {
      session.status = 'completed';
    }

    const metrics = this.recomputeSessionMetrics(session);
    session.metrics = metrics;

    await this.putSession(session);
    return session;
  }

  async updateSessionM4Snapshot(
    sessionId: string,
    snapshot: M4VerificationSnapshot,
    optInStoreDiff = false,
  ): Promise<LearningSessionRecord> {
    const session = await this.getSession(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    // Storage Bound & Privacy Invariant:
    // Only store rawDiffText if opt-in is explicitly true
    const boundedSnapshot: M4VerificationSnapshot = {
      report: snapshot.report,
      hasRawDiffStored: optInStoreDiff && !!snapshot.rawDiffText,
      rawDiffText: optInStoreDiff ? snapshot.rawDiffText : undefined,
      testExecutionResult: snapshot.testExecutionResult,
      draftPR: snapshot.draftPR,
      savedAt: snapshot.savedAt || new Date().toISOString(),
    };

    session.m4Snapshot = boundedSnapshot;
    session.lastActivePillar = 'm4_verify';
    session.lastUpdatedAt = getMonotonicIsoTimestamp();

    const metrics = this.recomputeSessionMetrics(session);
    session.metrics = metrics;

    await this.putSession(session);
    return session;
  }

  private recomputeSessionMetrics(session: LearningSessionRecord): SessionLearningMetrics {
    const encounteredSet = new Set<string>();
    const practicedSet = new Set<string>();
    const userMarkedSet = new Set<string>();
    const completedStepsSet = new Set<string>();
    const filesTouchedSet = new Set<string>();

    // 1. From M2 Learning Brief
    if (session.m2Snapshot) {
      const brief = session.m2Snapshot.brief;
      if (brief.concepts) {
        brief.concepts.forEach((c) => encounteredSet.add(c.name));
      }
      if (brief.investigation_targets) {
        brief.investigation_targets.forEach((f) => filesTouchedSet.add(f.path));
      }
      if (session.m2Snapshot.checkedChecklistKeys && brief.readiness_checklist) {
        Object.entries(session.m2Snapshot.checkedChecklistKeys).forEach(([key, checked]) => {
          if (checked) {
            const idx = parseInt(key.replace('chk-', ''), 10);
            if (!isNaN(idx) && brief.readiness_checklist[idx]) {
              userMarkedSet.add(brief.readiness_checklist[idx].item);
            }
          }
        });
      }
    }

    // 2. From M3 Guided Plan
    if (session.m3Snapshot) {
      const plan = session.m3Snapshot.plan;
      if (plan.steps) {
        plan.steps.forEach((step) => {
          const status = session.m3Snapshot?.stepStatuses[step.id];
          if (step.files) {
            step.files.forEach((f) => filesTouchedSet.add(f));
          }

          if (status === 'completed') {
            completedStepsSet.add(step.id);
            practicedSet.add(step.title);
          } else if (status === 'understood') {
            userMarkedSet.add(`Understood step: ${step.title}`);
            practicedSet.add(step.title);
          } else if (status === 'in_progress') {
            practicedSet.add(step.title);
          }

          // Check revealed hints
          if (step.hints && session.m3Snapshot?.revealedHints) {
            step.hints.forEach((hint, hintIdx) => {
              const hintKey = `${step.id}-${hintIdx}`;
              if (session.m3Snapshot?.revealedHints[hintKey]) {
                practicedSet.add(`${step.title} (${hint.title || `Hint ${hintIdx + 1}`})`);
              }
            });
          }
        });
      }
    }

    // 3. From M4 Verification
    if (session.m4Snapshot && session.m4Snapshot.report) {
      const report = session.m4Snapshot.report;
      if (report.parsed_diff?.files) {
        report.parsed_diff.files.forEach((f) => filesTouchedSet.add(f.path));
      }
      if (report.review_findings) {
        report.review_findings.forEach((rf) => {
          practicedSet.add(`Review: ${rf.title}`);
        });
      }
      if (report.readiness?.checklist_status) {
        Object.entries(report.readiness.checklist_status).forEach(([item, checked]) => {
          if (checked) {
            userMarkedSet.add(`Verified readiness: ${item}`);
          }
        });
      }
    }

    return {
      encounteredConcepts: Array.from(encounteredSet).sort(),
      practicedConcepts: Array.from(practicedSet).sort(),
      userMarkedUnderstanding: Array.from(userMarkedSet).sort(),
      completedSteps: Array.from(completedStepsSet).sort(),
      filesTouched: Array.from(filesTouchedSet).sort(),
    };
  }

  // --- Contributor Growth Profile Computation ---

  async recalculateGrowthProfile(isDemo = false): Promise<ContributorGrowthProfile> {
    const sessions = await this.listSessions({ isDemo });

    const distinctRepos = new Set<string>();
    const encounteredFreq: Record<string, number> = {};
    const practicedFreq: Record<string, number> = {};
    const markedSet = new Set<string>();
    const completedStepsSet = new Set<string>();

    let completedSessions = 0;
    let activeSessions = 0;

    for (const session of sessions) {
      distinctRepos.add(session.repoUrl);
      if (session.status === 'completed') completedSessions++;
      if (session.status === 'active') activeSessions++;

      session.metrics.encounteredConcepts.forEach((c) => {
        encounteredFreq[c] = (encounteredFreq[c] || 0) + 1;
      });

      session.metrics.practicedConcepts.forEach((c) => {
        practicedFreq[c] = (practicedFreq[c] || 0) + 1;
      });

      session.metrics.userMarkedUnderstanding.forEach((u) => {
        markedSet.add(u);
      });

      session.metrics.completedSteps.forEach((s) => {
        completedStepsSet.add(`${session.sessionId}:${s}`);
      });
    }

    const profile: ContributorGrowthProfile = {
      profileVersion: 1,
      isDemo,
      totalSessions: sessions.length,
      completedSessions,
      activeSessions,
      distinctRepositories: Array.from(distinctRepos).sort(),
      encounteredConceptsCount: Object.keys(encounteredFreq).length,
      practicedConceptsCount: Object.keys(practicedFreq).length,
      userMarkedUnderstandingCount: markedSet.size,
      completedStepsCount: completedStepsSet.size,
      conceptsEncountered: encounteredFreq,
      conceptsPracticed: practicedFreq,
      lastCalculatedAt: new Date().toISOString(),
    };

    await this.putGrowthProfile(profile);
    return profile;
  }

  async getGrowthProfile(isDemo = false): Promise<ContributorGrowthProfile | null> {
    if (this.isMemoryOnly && this.memoryStore) {
      return this.memoryStore.getProfile(isDemo);
    }

    try {
      const db = await this.getDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(PROFILES_STORE, 'readonly');
        const store = tx.objectStore(PROFILES_STORE);
        const profileKey = isDemo ? 'demo' : 'real';
        const req = store.get(profileKey);

        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
    } catch {
      if (this.memoryStore) {
        return this.memoryStore.getProfile(isDemo);
      }
      return null;
    }
  }

  private async putGrowthProfile(profile: ContributorGrowthProfile): Promise<void> {
    if (this.isMemoryOnly && this.memoryStore) {
      await this.memoryStore.putProfile(profile);
      return;
    }

    try {
      const db = await this.getDb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction(PROFILES_STORE, 'readwrite');
        const store = tx.objectStore(PROFILES_STORE);
        const record = {
          ...profile,
          profileKey: profile.isDemo ? 'demo' : 'real',
        };
        const req = store.put(record);

        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } catch {
      if (!this.memoryStore) this.memoryStore = new InMemoryStore();
      await this.memoryStore.putProfile(profile);
    }
  }

  // --- Quota & Health Check ---

  async checkStorageQuota(): Promise<StorageQuotaInfo> {
    const all = await this.listSessions();
    const count = all.length;
    const warning = count >= SOFT_SESSION_LIMIT;

    return {
      count,
      softLimit: SOFT_SESSION_LIMIT,
      warning,
      message: warning
        ? `You have reached ${count} learning sessions (soft limit: ${SOFT_SESSION_LIMIT}). Consider exporting or clearing older sessions to manage storage.`
        : undefined,
    };
  }

  // --- Export & Import ---

  async exportHistoryJson(filter?: { isDemo?: boolean }): Promise<string> {
    const sessions = await this.listSessions(filter);
    const profile = await this.getGrowthProfile(filter?.isDemo ?? false);

    const payload: StorageExportPayload = {
      format: 'patchloom_learning_history',
      version: CURRENT_SCHEMA_VERSION,
      exportedAt: new Date().toISOString(),
      sessionCount: sessions.length,
      sessions,
      growthProfile: profile,
    };

    return JSON.stringify(payload, null, 2);
  }

  async importHistoryJson(jsonStr: string): Promise<ImportResult> {
    const errors: string[] = [];

    // 1. Size guard: reject if > MAX_IMPORT_SIZE_BYTES (5MB)
    const byteLength = new TextEncoder().encode(jsonStr).length;
    if (byteLength > MAX_IMPORT_SIZE_BYTES) {
      return {
        success: false,
        importedSessionsCount: 0,
        skippedSessionsCount: 0,
        errors: [`Payload size (${(byteLength / 1024 / 1024).toFixed(2)} MB) exceeds maximum allowed 5 MB`],
      };
    }

    // 2. Parse JSON safely
    let data: any;
    try {
      data = JSON.parse(jsonStr);
    } catch (e: any) {
      return {
        success: false,
        importedSessionsCount: 0,
        skippedSessionsCount: 0,
        errors: [`Malformed JSON: ${e.message}`],
      };
    }

    // 3. Validate format header
    if (!data || typeof data !== 'object') {
      return {
        success: false,
        importedSessionsCount: 0,
        skippedSessionsCount: 0,
        errors: ['Import payload must be a JSON object'],
      };
    }

    if (data.format !== 'patchloom_learning_history') {
      return {
        success: false,
        importedSessionsCount: 0,
        skippedSessionsCount: 0,
        errors: [`Unrecognized format: "${data.format}". Expected "patchloom_learning_history"`],
      };
    }

    if (!Array.isArray(data.sessions)) {
      return {
        success: false,
        importedSessionsCount: 0,
        skippedSessionsCount: 0,
        errors: ['Invalid payload: "sessions" must be an array'],
      };
    }

    let importedCount = 0;
    let skippedCount = 0;

    for (const rawSession of data.sessions) {
      try {
        if (!rawSession || typeof rawSession !== 'object') {
          skippedCount++;
          errors.push('Skipped invalid non-object session entry');
          continue;
        }

        if (!rawSession.repoUrl || typeof rawSession.repoUrl !== 'string') {
          skippedCount++;
          errors.push('Skipped session missing valid repoUrl');
          continue;
        }

        if (typeof rawSession.issueNumber !== 'number') {
          skippedCount++;
          errors.push(`Skipped session for ${rawSession.repoUrl} with missing issueNumber`);
          continue;
        }

        // Sanitize & enforce security invariants:
        // Ensure execution authorization is NEVER imported/restored
        const sanitizedSession: LearningSessionRecord = {
          sessionId: typeof rawSession.sessionId === 'string' && rawSession.sessionId ? rawSession.sessionId : generateUUID(),
          schemaVersion: CURRENT_SCHEMA_VERSION,
          repoUrl: rawSession.repoUrl,
          repoOwner: rawSession.repoOwner || parseRepoOwnerAndName(rawSession.repoUrl).owner,
          repoName: rawSession.repoName || parseRepoOwnerAndName(rawSession.repoUrl).name,
          issueNumber: rawSession.issueNumber,
          issueTitle: rawSession.issueTitle || `Issue #${rawSession.issueNumber}`,
          isDemo: !!rawSession.isDemo,
          status: ['active', 'completed', 'abandoned'].includes(rawSession.status) ? rawSession.status : 'active',
          startedAt: rawSession.startedAt || new Date().toISOString(),
          lastUpdatedAt: rawSession.lastUpdatedAt || new Date().toISOString(),
          lastActivePillar: ['m2_learn', 'm3_guided', 'm4_verify'].includes(rawSession.lastActivePillar)
            ? rawSession.lastActivePillar
            : 'm2_learn',
          contributorProfile: rawSession.contributorProfile || null,
          m2Snapshot: rawSession.m2Snapshot || null,
          m3Snapshot: rawSession.m3Snapshot || null,
          m4Snapshot: rawSession.m4Snapshot
            ? {
                report: rawSession.m4Snapshot.report,
                hasRawDiffStored: !!rawSession.m4Snapshot.rawDiffText,
                rawDiffText: rawSession.m4Snapshot.rawDiffText,
                testExecutionResult: rawSession.m4Snapshot.testExecutionResult,
                draftPR: rawSession.m4Snapshot.draftPR,
                savedAt: rawSession.m4Snapshot.savedAt || new Date().toISOString(),
              }
            : null,
          metrics: rawSession.metrics || {
            encounteredConcepts: [],
            practicedConcepts: [],
            userMarkedUnderstanding: [],
            completedSteps: [],
            filesTouched: [],
          },
        };

        // Recompute metrics safely
        sanitizedSession.metrics = this.recomputeSessionMetrics(sanitizedSession);

        await this.putSession(sanitizedSession);
        importedCount++;
      } catch (err: any) {
        skippedCount++;
        errors.push(`Failed to import session: ${err.message}`);
      }
    }

    return {
      success: importedCount > 0 || skippedCount === 0,
      importedSessionsCount: importedCount,
      skippedSessionsCount: skippedCount,
      errors,
    };
  }

  // --- Clear History ---

  async clearAllSessions(filter?: { isDemo?: boolean }): Promise<void> {
    if (filter?.isDemo === undefined) {
      if (this.isMemoryOnly && this.memoryStore) {
        await this.memoryStore.clearAll();
        return;
      }

      try {
        const db = await this.getDb();
        await new Promise<void>((resolve, reject) => {
          const tx = db.transaction([SESSIONS_STORE, PROFILES_STORE], 'readwrite');
          tx.objectStore(SESSIONS_STORE).clear();
          tx.objectStore(PROFILES_STORE).clear();
          tx.oncomplete = () => resolve();
          tx.onerror = () => reject(tx.error);
        });
      } catch {
        if (this.memoryStore) {
          await this.memoryStore.clearAll();
        }
      }
    } else {
      // Clear specific category (demo or real)
      const toDelete = await this.listSessions(filter);
      for (const s of toDelete) {
        await this.deleteSession(s.sessionId);
      }
      // Recalculate or clear that category's profile
      await this.recalculateGrowthProfile(filter.isDemo);
    }
  }
}

// Global singleton instance for app-wide use
export const learningHistoryStorage = new LearningHistoryStorageAdapter();
