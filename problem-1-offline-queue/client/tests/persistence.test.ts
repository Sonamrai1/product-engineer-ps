import { describe, it, expect, beforeEach } from 'vitest';
import { openDB } from 'idb';
import * as db from '../src/db';
import type { Incident } from '../src/types';

const sample: Incident = {
  id: 'incident-1',
  title: 'Coolant leak, bay 3',
  severity: 'HIGH',
  createdAt: '2026-01-01T10:00:00.000Z',
  syncState: 'PENDING',
};

describe('IndexedDB persistence', () => {
  beforeEach(async () => {
    await db._resetDbForTests();
  });

  it('reads back what was saved through a brand new connection (simulated restart)', async () => {
    await db.saveIncident(sample);

    // A restart just means the app opens a new connection to the same
    // on-disk database - nothing lives in JS memory between launches.
    // Opening one directly here (bypassing db.ts's cached connection)
    // is the closest thing to that in a test.
    const freshConn = await openDB('incident-queue', 1);
    const raw = await freshConn.getAll('incidents');
    freshConn.close();

    expect(raw).toHaveLength(1);
    expect(raw[0].id).toBe(sample.id);
    expect(raw[0].syncState).toBe('PENDING');
  });

  it('keeps a state update after it is written', async () => {
    await db.saveIncident(sample);
    await db.updateIncidentState(sample.id, 'SYNCED');

    const all = await db.getAllIncidents();
    expect(all[0].syncState).toBe('SYNCED');
  });
});
