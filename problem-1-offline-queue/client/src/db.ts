import { openDB, type IDBPDatabase } from 'idb';
import type { Incident } from './types';

const DB_NAME = 'incident-queue';
const STORE = 'incidents';

let dbPromise: Promise<IDBPDatabase> | null = null;

function getDb() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, 1, {
      upgrade(db) {
        db.createObjectStore(STORE, { keyPath: 'id' });
      },
    });
  }
  return dbPromise;
}

export async function saveIncident(incident: Incident): Promise<void> {
  const db = await getDb();
  await db.put(STORE, incident);
}

export async function getAllIncidents(): Promise<Incident[]> {
  const db = await getDb();
  const all = await db.getAll(STORE);
  // newest first, easier to eyeball while testing
  return all.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
}

export async function updateIncidentState(
  id: string,
  syncState: Incident['syncState'],
  lastError?: string,
): Promise<void> {
  const db = await getDb();
  const existing = await db.get(STORE, id);
  if (!existing) return;
  await db.put(STORE, { ...existing, syncState, lastError });
}

// Only used in tests to reset between cases - production code never calls this.
export async function _resetDbForTests(): Promise<void> {
  const db = await getDb();
  await db.clear(STORE);
}
