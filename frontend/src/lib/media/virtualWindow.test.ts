import { describe, it, expect } from 'vitest';
import { computeWindow } from './virtualWindow';

const base = { headHeight: 34, viewportHeight: 700, rowHeight: 72, total: 1000, overscan: 6, scrollTop: 0 };

describe('computeWindow', () => {
  it('renders a bounded slice in the middle of a long list', () => {
    const w = computeWindow({ ...base, scrollTop: 3600 });
    expect(w.start).toBeGreaterThan(0);
    // 700px 视口 / 72px 行高 ≈ 10 行 + 2 额外 + 两侧 overscan
    expect(w.end - w.start).toBeLessThan(30);
    // 窗口必须覆盖当前视口内的第一行
    expect(w.start).toBeLessThanOrEqual(Math.floor((3600 - 34) / 72));
  });

  it('pads correctly so total scroll height stays constant', () => {
    const w = computeWindow({ ...base, scrollTop: 3600 });
    expect(w.padTop).toBe(w.start * 72);
    expect(w.padBottom).toBe((1000 - w.end) * 72);
    // 窗口内行数 + 上下垫片行数 == 总行数
    expect(w.end - w.start + w.start + (1000 - w.end)).toBe(1000);
  });

  it('starts at 0 at the top with no top padding', () => {
    const w = computeWindow({ ...base, scrollTop: 0 });
    expect(w.start).toBe(0);
    expect(w.padTop).toBe(0);
  });

  it('clamps to the end without overshooting', () => {
    // 滚到最底部：end 必须正好等于 total
    const maxScroll = 1000 * 72 + 34 - 700;
    const w = computeWindow({ ...base, scrollTop: maxScroll });
    expect(w.end).toBe(1000);
    expect(w.padBottom).toBe(0);
  });

  it('handles an empty list', () => {
    expect(computeWindow({ ...base, total: 0 })).toEqual({
      start: 0,
      end: 0,
      padTop: 0,
      padBottom: 0
    });
  });

  it('handles a list shorter than the viewport', () => {
    const w = computeWindow({ ...base, total: 5 });
    expect(w.start).toBe(0);
    expect(w.end).toBe(5);
    expect(w.padBottom).toBe(0);
  });

  it('never returns start > end or negative pads for tiny lists', () => {
    for (const total of [1, 2, 3]) {
      const w = computeWindow({ ...base, total, scrollTop: 10_000 });
      expect(w.start).toBeLessThanOrEqual(w.end);
      expect(w.padTop).toBeGreaterThanOrEqual(0);
      expect(w.padBottom).toBeGreaterThanOrEqual(0);
      expect(w.end).toBeLessThanOrEqual(total);
    }
  });

  it('guards against a zero row height (avoid divide-by-zero infinite loops)', () => {
    expect(computeWindow({ ...base, rowHeight: 0 })).toEqual({
      start: 0,
      end: 0,
      padTop: 0,
      padBottom: 0
    });
  });

  it('grows the window with overscan', () => {
    const small = computeWindow({ ...base, scrollTop: 3600, overscan: 0 });
    const large = computeWindow({ ...base, scrollTop: 3600, overscan: 10 });
    expect(large.end - large.start).toBeGreaterThan(small.end - small.start);
  });
});
