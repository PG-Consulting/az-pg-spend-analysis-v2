/**
 * @fileoverview IndexedDB persistence layer for Spend.AI v3.
 *
 * Stores:
 *   - sessions: taxonomy classification sessions (keyed by sessionId)
 *   - projects: project definitions (keyed by project_id)
 *   - reviewProgress: per-session review state map (keyed by sessionId)
 *
 * DB_VERSION history:
 *   v1 - sessions store only (migrated from v2 schema)
 *   v2 - added projects store, reviewProgress store, by-project index on sessions,
 *        and backfills reviewState='completed' on existing sessions
 */

import { openDB, DBSchema, IDBPDatabase } from 'idb';
import type { TaxonomySession, Project, ReviewItemState } from './types';

const DB_NAME = 'SpendAnalysisDB';
const DB_VERSION = 2;

interface SpendAnalysisDB extends DBSchema {
  sessions: {
    key: string; // sessionId
    value: TaxonomySession;
    indexes: {
      'by-project': string;
      'by-timestamp': number;
    };
  };
  projects: {
    key: string; // project_id
    value: Project;
    indexes: {
      'by-sector': string;
      'by-name': string;
    };
  };
  reviewProgress: {
    key: string; // sessionId
    value: {
      sessionId: string;
      reviewStates: [number, ReviewItemState][]; // Map serialized as entries array
      lastSaved: number;
    };
  };
}

let dbPromise: Promise<IDBPDatabase<SpendAnalysisDB>> | null = null;

export function getDB(): Promise<IDBPDatabase<SpendAnalysisDB>> {
  if (typeof window === 'undefined') {
    throw new Error('IndexedDB is not available on the server');
  }

  if (!dbPromise) {
    dbPromise = openDB<SpendAnalysisDB>(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion, _newVersion, transaction) {
        // ---- v1: create sessions store ----
        if (!db.objectStoreNames.contains('sessions')) {
          const sessionsStore = db.createObjectStore('sessions', { keyPath: 'sessionId' });
          sessionsStore.createIndex('by-timestamp', 'timestamp');
        }

        // ---- v2: additional stores and indexes ----
        if (oldVersion < 2) {
          // Add by-project index to existing sessions store
          if (db.objectStoreNames.contains('sessions')) {
            const store = transaction.objectStore('sessions');
            if (!store.indexNames.contains('by-project')) {
              store.createIndex('by-project', 'projectId');
            }
          }

          // Create projects store
          if (!db.objectStoreNames.contains('projects')) {
            const projectsStore = db.createObjectStore('projects', { keyPath: 'project_id' });
            projectsStore.createIndex('by-sector', 'sector');
            projectsStore.createIndex('by-name', 'display_name');
          }

          // Create reviewProgress store
          if (!db.objectStoreNames.contains('reviewProgress')) {
            db.createObjectStore('reviewProgress', { keyPath: 'sessionId' });
          }

          // Migrate existing sessions: backfill reviewState = 'completed'
          // (sessions created before the review feature existed are treated as complete)
          if (db.objectStoreNames.contains('sessions')) {
            const sessionsStore = transaction.objectStore('sessions');
            // IDBPDatabase upgrade transaction supports cursor iteration
            void (async () => {
              let cursor = await sessionsStore.openCursor();
              while (cursor) {
                const session = cursor.value as TaxonomySession;
                if (!session.reviewState) {
                  await cursor.update({
                    ...session,
                    reviewState: 'completed',
                    reviewedCount: session.totalItems ?? 0,
                    totalItems: session.totalItems ?? 0,
                  } as TaxonomySession);
                }
                cursor = await cursor.continue();
              }
            })();
          }
        }
      },
    });
  }

  return dbPromise;
}

// ==================== SESSIONS ====================

export async function saveSession(session: TaxonomySession): Promise<void> {
  try {
    const db = await getDB();
    // Ensure required review fields are always present
    const toSave: TaxonomySession = {
      ...session,
      reviewState: session.reviewState ?? 'pending',
      reviewedCount: session.reviewedCount ?? 0,
      totalItems: session.totalItems ?? 0,
    };
    await db.put('sessions', toSave);
  } catch (error) {
    console.error('Error saving session to IndexedDB:', error);
  }
}

export async function getSession(sessionId: string): Promise<TaxonomySession | undefined> {
  try {
    const db = await getDB();
    return await db.get('sessions', sessionId);
  } catch (error) {
    console.error('Error getting session from IndexedDB:', error);
    return undefined;
  }
}

export async function getAllSessions(projectId?: string): Promise<TaxonomySession[]> {
  try {
    const db = await getDB();
    let sessions: TaxonomySession[];
    if (projectId) {
      sessions = await db.getAllFromIndex('sessions', 'by-project', projectId);
    } else {
      sessions = await db.getAll('sessions');
    }
    return sessions.sort((a, b) => b.timestamp - a.timestamp);
  } catch (error) {
    console.error('Error getting all sessions from IndexedDB:', error);
    return [];
  }
}

export async function deleteSession(sessionId: string): Promise<void> {
  try {
    const db = await getDB();
    await db.delete('sessions', sessionId);
    // Clean up associated review progress
    await db.delete('reviewProgress', sessionId);
  } catch (error) {
    console.error('Error deleting session from IndexedDB:', error);
  }
}

export async function clearAllSessions(): Promise<void> {
  try {
    const db = await getDB();
    await db.clear('sessions');
    await db.clear('reviewProgress');
  } catch (error) {
    console.error('Error clearing sessions from IndexedDB:', error);
  }
}

// ==================== PROJECTS ====================

export async function saveProject(project: Project): Promise<void> {
  try {
    const db = await getDB();
    await db.put('projects', project);
  } catch (error) {
    console.error('Error saving project to IndexedDB:', error);
  }
}

export async function getProjectLocal(projectId: string): Promise<Project | undefined> {
  try {
    const db = await getDB();
    return await db.get('projects', projectId);
  } catch (error) {
    console.error('Error getting project from IndexedDB:', error);
    return undefined;
  }
}

export async function getAllProjectsLocal(): Promise<Project[]> {
  try {
    const db = await getDB();
    return await db.getAll('projects');
  } catch (error) {
    console.error('Error getting all projects from IndexedDB:', error);
    return [];
  }
}

export async function deleteProjectLocal(projectId: string): Promise<void> {
  try {
    const db = await getDB();
    await db.delete('projects', projectId);
  } catch (error) {
    console.error('Error deleting project from IndexedDB:', error);
  }
}

// ==================== REVIEW PROGRESS ====================

export async function saveReviewProgress(
  sessionId: string,
  reviewStates: Map<number, ReviewItemState>
): Promise<void> {
  try {
    const db = await getDB();
    await db.put('reviewProgress', {
      sessionId,
      reviewStates: Array.from(reviewStates.entries()),
      lastSaved: Date.now(),
    });
  } catch (error) {
    console.error('Error saving review progress to IndexedDB:', error);
  }
}

export async function loadReviewProgress(
  sessionId: string
): Promise<Map<number, ReviewItemState> | null> {
  try {
    const db = await getDB();
    const data = await db.get('reviewProgress', sessionId);
    if (!data) return null;
    return new Map(data.reviewStates);
  } catch (error) {
    console.error('Error loading review progress from IndexedDB:', error);
    return null;
  }
}
