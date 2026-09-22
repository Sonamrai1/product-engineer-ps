import type { Incident } from './types';
import { updateIncidentState } from './db';
import { simulatedFetch } from './network';

let syncing = false;

/**
 * Pushes every PENDING/FAILED incident to the server, one at a time.
 * Sequential on purpose - it keeps the "app closed mid-sync" story simple:
 * at most one incident is ever in SYNCING when the process dies, and on
 * relaunch it just gets retried (server dedupes on id, so that's safe).
 */
export async function syncQueue(
  incidents: Incident[],
  onUpdate: (id: string, state: Incident['syncState'], error?: string) => void,
): Promise<void> {
  if (syncing) return;
  syncing = true;

  try {
    const toSync = incidents.filter((i) => i.syncState === 'PENDING' || i.syncState === 'FAILED');

    for (const incident of toSync) {
      onUpdate(incident.id, 'SYNCING');
      await updateIncidentState(incident.id, 'SYNCING');

      try {
        const res = await simulatedFetch('/incidents', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: incident.id,
            title: incident.title,
            severity: incident.severity,
            createdAt: incident.createdAt,
          }),
        });

        if (!res.ok) throw new Error(`server responded ${res.status}`);

        onUpdate(incident.id, 'SYNCED');
        await updateIncidentState(incident.id, 'SYNCED');
      } catch (err) {
        const message = err instanceof Error ? err.message : 'unknown error';
        onUpdate(incident.id, 'FAILED', message);
        await updateIncidentState(incident.id, 'FAILED', message);
      }
    }
  } finally {
    syncing = false;
  }
}
