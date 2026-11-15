import { describe, it, expect } from 'vitest';
import { sparkPoints, trendDelta } from './sparkline';

const pts = (values: number[]) =>
  values.map((value, i) => ({ date: `2026-10-${String(i + 1).padStart(2, '0')}`, value }));

describe('sparkPoints', () => {
  it('is not ready with fewer than 2 points', () => {
    expect(sparkPoints([], 60, 18).ready).toBe(false);
    expect(sparkPoints(pts([5]), 60, 18).ready).toBe(false);
    expect(sparkPoints(pts([5]), 60, 18).points).toBe('');
  });

  it('produces one coordinate pair per point', () => {
    const r = sparkPoints(pts([1, 2, 3]), 60, 18);
    expect(r.ready).toBe(true);
    expect(r.points.split(' ')).toHaveLength(3);
  });

  it('never emits NaN when all values are equal', () => {
    const r = sparkPoints(pts([7, 7, 7]), 60, 18);
    expect(r.points).not.toContain('NaN');
    expect(r.points.split(' ')).toHaveLength(3);
  });

  it('inverts the y axis so larger values sit higher', () => {
    const r = sparkPoints(pts([0, 100]), 60, 18);
    const [first, second] = r.points.split(' ').map((p) => Number(p.split(',')[1]));
    expect(second).toBeLessThan(first);
  });

  it('keeps coordinates inside the viewBox', () => {
    const values = [3, 1, 4, 1, 5, 9, 2, 6];
    for (const pair of sparkPoints(pts(values), 64, 18).points.split(' ')) {
      const [x, y] = pair.split(',').map(Number);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(64);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(18);
    }
  });

  it('returns zero bounds for an empty series', () => {
    expect(sparkPoints([], 60, 18)).toMatchObject({ min: 0, max: 0 });
  });

  it('guards against a non-positive viewport', () => {
    expect(sparkPoints(pts([1, 2]), 0, 18).ready).toBe(false);
    expect(sparkPoints(pts([1, 2]), 60, 0).ready).toBe(false);
  });
});

describe('trendDelta', () => {
  it('is null for fewer than 2 points', () => {
    expect(trendDelta([])).toBeNull();
    expect(trendDelta(pts([5]))).toBeNull();
  });

  it('returns last minus first (can be negative)', () => {
    expect(trendDelta(pts([10, 30, 25]))).toBe(15);
    expect(trendDelta(pts([30, 10]))).toBe(-20);
  });
});
