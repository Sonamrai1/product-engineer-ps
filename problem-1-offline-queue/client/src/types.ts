export type SyncState = 'PENDING' | 'SYNCING' | 'SYNCED' | 'FAILED';

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface Incident {
  id: string; // client-generated uuid, doubles as the idempotency key
  title: string;
  severity: Severity;
  createdAt: string; // ISO string
  syncState: SyncState;
  lastError?: string;
}

export type NetworkMode = 'ONLINE' | 'OFFLINE' | 'FAILING';
