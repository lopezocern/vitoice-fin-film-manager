import { describe, it, expect } from 'vitest';
import {
  LIST_MAX_ATTEMPTS,
  LIST_TIMEOUT_MS,
  shouldRetry,
  timeoutError,
  withTimeout
} from './listRequest';

describe('shouldRetry', () => {
  it('retries once on network / 5xx / unknown errors', () => {
    expect(shouldRetry(new Error('fetch failed'), 0)).toBe(true);
    expect(shouldRetry({ status: 503 }, 0)).toBe(true);
    expect(shouldRetry(null, 0)).toBe(true);
  });

  it('gives up after the attempt budget', () => {
    expect(shouldRetry(new Error('x'), LIST_MAX_ATTEMPTS)).toBe(false);
    expect(shouldRetry({ status: 503 }, LIST_MAX_ATTEMPTS)).toBe(false);
  });

  it('never retries 4xx — the request itself is wrong', () => {
    for (const status of [400, 401, 403, 404, 413, 422]) {
      expect(shouldRetry({ status }, 0)).toBe(false);
    }
  });

  it('never retries a user-initiated abort', () => {
    expect(shouldRetry({ name: 'AbortError' }, 0)).toBe(false);
  });
});

describe('timeoutError', () => {
  it('is distinguishable by name and mentions the limit', () => {
    const e = timeoutError();
    expect(e.name).toBe('TimeoutError');
    expect(e.message).toContain(String(Math.round(LIST_TIMEOUT_MS / 1000)));
  });
});

describe('withTimeout', () => {
  it('does not abort before the deadline', async () => {
    const { signal, cleanup } = withTimeout(50);
    expect(signal.aborted).toBe(false);
    cleanup();
  });

  it('aborts when the timer fires', async () => {
    const { signal, cleanup, timedOut } = withTimeout(10);
    await new Promise((r) => setTimeout(r, 30));
    expect(signal.aborted).toBe(true);
    expect(timedOut()).toBe(true);
    cleanup();
  });

  it('aborts immediately when the external signal fires', () => {
    const outer = new AbortController();
    const { signal, cleanup, timedOut } = withTimeout(10_000, outer.signal);
    outer.abort();
    expect(signal.aborted).toBe(true);
    // 外部取消不能被误判成超时
    expect(timedOut()).toBe(false);
    cleanup();
  });

  it('stops the timer after cleanup (no stray abort later)', async () => {
    const { signal, cleanup } = withTimeout(10);
    cleanup();
    await new Promise((r) => setTimeout(r, 30));
    expect(signal.aborted).toBe(false);
  });
});
