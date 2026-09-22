import { useEffect, useState } from 'react';
import type { Incident, NetworkMode, Severity } from './types';
import { getAllIncidents, saveIncident, updateIncidentState } from './db';
import { getNetworkMode, setNetworkMode } from './network';
import { syncQueue } from './sync';
import './App.css';

const SEVERITIES: Severity[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

export default function App() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [title, setTitle] = useState('');
  const [severity, setSeverity] = useState<Severity>('MEDIUM');
  const [mode, setMode] = useState<NetworkMode>(getNetworkMode());

  // Load whatever's already in IndexedDB on mount - this is what makes
  // incidents survive an app restart (AC2).
  useEffect(() => {
    getAllIncidents().then(setIncidents);
  }, []);

  // Whenever we flip to ONLINE, kick off a sync pass automatically.
  useEffect(() => {
    if (mode === 'ONLINE') runSync();
  }, [mode]);

  function applyUpdate(id: string, syncState: Incident['syncState'], error?: string) {
    setIncidents((prev) =>
      prev.map((i) => (i.id === id ? { ...i, syncState, lastError: error } : i)),
    );
  }

  async function runSync() {
    const current = await getAllIncidents();
    await syncQueue(current, applyUpdate);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;

    const incident: Incident = {
      id: crypto.randomUUID(),
      title: title.trim(),
      severity,
      createdAt: new Date().toISOString(),
      syncState: 'PENDING',
    };

    await saveIncident(incident);
    setIncidents((prev) => [incident, ...prev]);
    setTitle('');

    if (getNetworkMode() === 'ONLINE') runSync();
  }

  async function handleRetry(id: string) {
    await updateIncidentState(id, 'PENDING');
    setIncidents((prev) => prev.map((i) => (i.id === id ? { ...i, syncState: 'PENDING' } : i)));
    runSync();
  }

  function handleModeChange(next: NetworkMode) {
    setNetworkMode(next);
    setMode(next);
  }

  return (
    <div className="app">
      <header>
        <h1>Incident Queue</h1>
        <p className="subtitle">Reports here save locally first and sync when the network allows.</p>
      </header>

      <section className="network-panel">
        <span className={`status-dot ${mode.toLowerCase()}`} />
        <span className="network-label">{mode}</span>
        <div className="network-buttons">
          <button onClick={() => handleModeChange('ONLINE')} disabled={mode === 'ONLINE'}>
            Go online
          </button>
          <button onClick={() => handleModeChange('OFFLINE')} disabled={mode === 'OFFLINE'}>
            Go offline
          </button>
          <button onClick={() => handleModeChange('FAILING')} disabled={mode === 'FAILING'}>
            Simulate failing
          </button>
        </div>
      </section>

      <form className="create-form" onSubmit={handleCreate}>
        <input
          type="text"
          placeholder="What's happening?"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <select value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button type="submit">Report incident</button>
      </form>

      <ul className="incident-list">
        {incidents.length === 0 && <li className="empty">No incidents reported yet.</li>}
        {incidents.map((incident) => (
          <li key={incident.id} className="incident-row">
            <div className="incident-main">
              <span className={`severity-tag ${incident.severity.toLowerCase()}`}>
                {incident.severity}
              </span>
              <span className="incident-title">{incident.title}</span>
              <span className="incident-time">
                {new Date(incident.createdAt).toLocaleTimeString()}
              </span>
            </div>
            <div className="incident-state">
              <span className={`state-badge ${incident.syncState.toLowerCase()}`}>
                {incident.syncState}
              </span>
              {incident.syncState === 'FAILED' && (
                <button className="retry-btn" onClick={() => handleRetry(incident.id)}>
                  Retry
                </button>
              )}
            </div>
            {incident.lastError && incident.syncState === 'FAILED' && (
              <div className="error-note">{incident.lastError}</div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
