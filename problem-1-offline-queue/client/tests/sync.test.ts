import { describe, it, expect, beforeEach, vi } from 'vitest';
import * as db from '../src/db';
import { syncQueue } from '../src/sync';
import type { Incident } from '../src/types';

vi.mock('../src/network', () => ({
  simulatedFetch: vi.fn(),
}));

import { simulatedFetch } from '../src/network';

const sample: Incident = {
  id: 'incident-retry-1',
  title: 'Sensor offline, aisle 7',
  severity: 'MEDIUM',
  createdAt: '2026-01-01T10:00:00.000Z',
  syncState: 'PENDING',
};

describe('sync engine - fail then retry', () => {
  beforeEach(async () => {
    await db._resetDbForTests();
    vi.mocked(simulatedFetch).mockReset();
  });

  it('marks the incident FAILED when the request rejects, then SYNCED on retry', async () => {
    await db.saveIncident(sample);

    vi.mocked(simulatedFetch).mockRejectedValueOnce(new Error('simulated network failure'));

    const updates: Record<string, string> = {};
    const onUpdate = (id: string, state: string) => {
      updates[id] = state;
    };

    await syncQueue([sample], onUpdate);
    expect(updates[sample.id]).toBe('FAILED');

    const afterFail = await db.getAllIncidents();
    expect(afterFail[0].syncState).toBe('FAILED');

    // retry - this time the "server" responds fine
    vi.mocked(simulatedFetch).mockResolvedValueOnce({ ok: true } as Response);
    await db.updateIncidentState(sample.id, 'PENDING');

    const retryable = await db.getAllIncidents();
    await syncQueue(retryable, onUpdate);

    expect(updates[sample.id]).toBe('SYNCED');
    const afterRetry = await db.getAllIncidents();
    expect(afterRetry[0].syncState).toBe('SYNCED');
  });
});
