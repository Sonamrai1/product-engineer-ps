# Offline Incident Queue

React + IndexedDB on the client, a small Express server standing in for the
backend. No React Native/Flutter here - a PWA-style setup covers the same
offline/sync mechanics without the extra build tooling, and it's faster for
a reviewer to just `npm run dev` and click around.

## Prerequisites

- Node.js 18+ (uses Vite 5 and native `crypto.randomUUID()`)
- npm (ships with Node)

## Demo video

[Add the demo video link here before submitting - see the root
`DEMO_SCRIPT.md` for the walkthrough this was recorded from.]

## Running it

Two terminals:

```
cd server
npm install
npm start          # http://localhost:4000
```

```
cd client
npm install
npm run dev         # http://localhost:5173
```

Open the client, report a few incidents, then play with the three network
buttons at the top (Go online / Go offline / Simulate failing) to see the
queue behave. Reload the page mid-way through - the list rebuilds itself
from IndexedDB.

## Demo - how to trigger each acceptance criterion

1. **Offline create, stable id, PENDING immediately.** Click **Go
   offline**, then report an incident. It appears instantly with a
   `PENDING` badge - no network round trip happened.
2. **Survives an app restart.** With one or more `PENDING` incidents on
   screen, reload the page. They're still there, still `PENDING` - this is
   read straight back from IndexedDB, not kept in memory.
3. **Online sync with server-side dedupe.** Click **Go online** - the
   `PENDING` incidents flip to `SYNCED`. (The dedupe itself - POSTing the
   same id twice never creates a second record - is exercised directly in
   `server/tests/incidents.test.js`, since triggering the exact retry race
   from the UI isn't practical to click through by hand.)
4. **Fail, then retry.** Click **Simulate failing**, report a new
   incident - it goes to `FAILED`. Click its **Retry** button, then
   **Go online** - it succeeds and flips to `SYNCED`.

## Running the tests

```
cd server && npm install && npm test
cd client && npm install && npm test
```

Server tests cover the idempotent POST / dedupe behavior. Client tests cover
IndexedDB persistence across a simulated restart, and the fail -> retry ->
synced path for the sync engine.

## How it's wired

- `client/src/db.ts` - all IndexedDB reads/writes, one object store keyed by
  the incident's client-generated UUID.
- `client/src/network.ts` - a fake network layer the UI buttons control.
  OFFLINE throws before anything leaves the browser, FAILING lets the delay
  happen but then throws (mimics a request that got sent and failed
  server-side, not just a dead connection), ONLINE hits the real server.
- `client/src/sync.ts` - walks every PENDING/FAILED incident and pushes it,
  one at a time, updating IndexedDB and React state as it goes.
- `server/index.js` - one endpoint, `POST /incidents`, keyed by the same id
  the client generated. Second POST with the same id just returns the
  existing record instead of creating a second one.

## Submission questions

See `SUBMISSION.md` for the four submission questions (mid-sync crash,
where dedupe lives, scaling to thousands of incidents, monitoring).


