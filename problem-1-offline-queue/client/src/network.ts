import type { NetworkMode } from './types';

// Single source of truth for "what is the network doing right now". The UI
// buttons just flip this, everything else reads it.
let mode: NetworkMode = 'ONLINE';
const listeners = new Set<(mode: NetworkMode) => void>();

export function getNetworkMode(): NetworkMode {
  return mode;
}

export function setNetworkMode(next: NetworkMode): void {
  mode = next;
  listeners.forEach((fn) => fn(mode));
}

export function onNetworkModeChange(fn: (mode: NetworkMode) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export const API_BASE = 'http://localhost:4000';

/**
 * Wraps fetch so the OFFLINE / FAILING toggles in the UI actually mean
 * something without touching the real server or the machine's network.
 */
export async function simulatedFetch(path: string, init?: RequestInit): Promise<Response> {
  if (mode === 'OFFLINE') {
    throw new Error('offline');
  }

  // small artificial delay so SYNCING is actually visible in the UI
  await new Promise((r) => setTimeout(r, 400));

  if (mode === 'FAILING') {
    throw new Error('simulated network failure');
  }

  return fetch(`${API_BASE}${path}`, init);
}
