const express = require('express');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());

// In-memory store, keyed by the client-generated id. This is the dedupe key -
// if a request comes in twice with the same id (retry after a dropped response,
// duplicate sync tick, whatever), we just hand back what we already have.
const incidents = new Map();

app.post('/incidents', (req, res) => {
  const { id, title, severity, createdAt } = req.body || {};

  if (!id || !title || !severity || !createdAt) {
    return res.status(400).json({ error: 'id, title, severity and createdAt are required' });
  }

  const existing = incidents.get(id);
  if (existing) {
    // Already synced this one. Same shape as a fresh create so the client
    // doesn't need to branch on 200 vs 201.
    return res.status(200).json({ ...existing, deduped: true });
  }

  const record = { id, title, severity, createdAt, serverReceivedAt: new Date().toISOString() };
  incidents.set(id, record);
  res.status(201).json(record);
});

app.get('/incidents', (_req, res) => {
  res.json(Array.from(incidents.values()));
});

// Test-only helper to reset state between test files.
app.delete('/incidents', (_req, res) => {
  incidents.clear();
  res.status(204).end();
});

if (require.main === module) {
  const PORT = process.env.PORT || 4000;
  app.listen(PORT, () => console.log(`incident server listening on ${PORT}`));
}

module.exports = app;
