import { describe, it, expect, beforeEach } from 'vitest';
import request from 'supertest';
import app from '../index.js';

const sample = {
  id: 'fixed-uuid-1',
  title: 'Fridge temp alarm',
  severity: 'HIGH',
  createdAt: '2026-01-01T00:00:00.000Z',
};

describe('POST /incidents', () => {
  beforeEach(async () => {
    await request(app).delete('/incidents');
  });

  it('creates a new incident and returns 201', async () => {
    const res = await request(app).post('/incidents').send(sample);
    expect(res.status).toBe(201);
    expect(res.body.id).toBe(sample.id);
  });

  it('is idempotent - same id twice never creates two records', async () => {
    await request(app).post('/incidents').send(sample);
    const second = await request(app).post('/incidents').send(sample);

    expect(second.status).toBe(200);
    expect(second.body.deduped).toBe(true);

    const list = await request(app).get('/incidents');
    expect(list.body).toHaveLength(1);
  });

  it('rejects a payload missing required fields', async () => {
    const res = await request(app).post('/incidents').send({ id: 'x' });
    expect(res.status).toBe(400);
  });

  it('treats a retried sync (client crashed mid-flight) the same as first send', async () => {
    const first = await request(app).post('/incidents').send(sample);
    const retry = await request(app).post('/incidents').send(sample);

    expect(first.body.id).toBe(retry.body.id);
    const list = await request(app).get('/incidents');
    expect(list.body).toHaveLength(1);
  });
});
