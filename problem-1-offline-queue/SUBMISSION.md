# Product Engineering Challenge Submission

## Candidate

- **Name:** [TODO]
- **Email:** [TODO]
- **GitHub:** [TODO]
- **Selected problem:** Problem 1 - Offline Mobile Queue
- **Demo video:** [Add the demo video link here before submitting]

## Run the project

Prerequisites: Node.js 18+.

```
cd server && npm install && npm start   # terminal 1, http://localhost:4000
cd client && npm install && npm run dev # terminal 2, http://localhost:5173
```

To trigger the successful scenario: click **Go offline**, report an incident
(shows `PENDING`), reload the page (still there - AC2), click **Go online**
(flips to `SYNCED`).

To trigger the failure/recovery scenario: click **Simulate failing**, report
an incident (goes to `FAILED`), click its **Retry** button, then **Go
online** (succeeds).

## Run the tests

```
cd server && npm install && npm test
cd client && npm install && npm test
```

Server tests cover idempotent POST / server-side dedupe. Client tests cover
IndexedDB persistence across a simulated restart, and the fail-then-retry
path.

## Architecture and data flow

```
React client (IndexedDB)                         Express server (in-memory)
  create incident -> save locally (PENDING) -------\
  reload page -> rehydrate from IndexedDB           |
  sync loop: PENDING/FAILED -> POST /incidents ------+--> dedupe by id -> store
                              <- 200/201 -----------/
  update local syncState (SYNCING/SYNCED/FAILED)
```

- `client/src/db.ts` - all IndexedDB reads/writes, one object store keyed by
  the incident's client-generated UUID.
- `client/src/network.ts` - a fake network layer the UI's three toggle
  buttons control (OFFLINE / ONLINE / FAILING).
- `client/src/sync.ts` - walks every PENDING/FAILED incident and pushes it,
  one at a time, updating IndexedDB and React state as it goes.
- `server/index.js` - one endpoint, `POST /incidents`, keyed by the same id
  the client generated. A second POST with the same id returns the existing
  record instead of creating a new one.

## Technology choices

React + IndexedDB over React Native/Flutter: the offline/sync mechanics
being demonstrated (local persistence, sync states, restart durability) are
identical regardless of mobile framework, and a browser-based PWA-style
client is faster for a reviewer to run with no mobile toolchain setup.
Express with an in-memory `Map` over a real database: the assignment calls
for a "mocked or minimal backend," and the dedupe guarantee under test is
about the `id` UNIQUE-key logic, not about a particular datastore.

## Important decisions

- **Dedupe lives server-side, keyed on the client-generated id.**
  Client-side dedupe ("don't resend if I already sent this") can't tell
  "in flight" apart from "lost," so it either double-sends or silently
  drops something on a bad connection. The server is the only party that
  can say for certain whether a given id was already persisted.
- **What happens if the app closes mid-sync:** the incident is left in
  `SYNCING` in IndexedDB. The current sync loop only looks for
  `PENDING`/`FAILED` rows on restart, so a stuck `SYNCING` row is a real
  gap - documented under Assumptions and limitations below, with the fix.
- **Three explicit network-mode toggles (Offline/Online/Failing)** instead
  of trying to simulate real network conditions, so a reviewer can
  deterministically trigger every acceptance scenario by clicking a button
  rather than unplugging a cable.

## Assumptions and limitations

- A `SYNCING` incident whose app is killed mid-request is not automatically
  retried on relaunch in the current version - the sync loop only picks up
  `PENDING`/`FAILED`. The fix is cheap (treat stale `SYNCING` as `PENDING`
  on startup) but isn't implemented, since the server's dedupe-by-id makes
  the retry safe either way - worst case the server just re-confirms the
  same record.
- The backend is intentionally minimal (in-memory `Map`, no real
  persistence) - out of scope per the assignment, and irrelevant to the
  client-side behavior being demonstrated.
- No authentication - out of scope per the assignment.

## Production and scale

- **At thousands of pending incidents:** sequential one-by-one sync would
  take too long - batch the POST endpoint (accept an array, dedupe each id
  server-side) instead of one request per incident. Loading everything into
  React state at once also gets slow - paginate the IndexedDB read or
  virtualize the list. An index on `syncState` lets the sync engine query
  just the pending/failed subset instead of filtering in JS.
- **What I'd monitor:** count of incidents stuck in `FAILED` past some age,
  and how long the average `PENDING` incident waits before syncing - the
  real signal for "is sync actually working." Server-side dedupe hit rate -
  a sudden jump usually means a client bug or flaky network, not a server
  problem. Client-side error messages from failed syncs, grouped by type,
  so one failure mode spiking is visible instead of buried in a generic
  "sync failed" count.
- Retrying failures would move from "try everything, every time" to
  backoff-scheduled retries (a queue of "next attempt at time X") to avoid
  hammering a server that's already struggling.

## AI usage

Used Claude for scaffolding and tests, manually reviewed logic.

## Credibility note

[TODO]
