import { describe, it, expect } from 'vitest';
import {
  pageList,
  maxVisiblePages,
  MEDIA_PAGER_METRICS,
  MANAGE_PAGER_METRICS,
  DEFAULT_PAGER_LIMITS
} from './pagination';

describe('pageList', () => {
  it('renders every page when they all fit', () => {
    expect(pageList(3, 5, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(pageList(1, 1, 5)).toEqual([1]);
  });

  it('returns nothing when there are no pages', () => {
    expect(pageList(1, 0, 5)).toEqual([]);
  });

  it('windows around the current page with ellipses on both sides', () => {
    expect(pageList(10, 20, 5)).toEqual([1, '…', 9, 10, 11, '…', 20]);
    expect(pageList(15, 30, 7)).toEqual([1, '…', 13, 14, 15, 16, 17, '…', 30]);
  });

  it('expands toward the far side when the window hits the first page', () => {
    expect(pageList(1, 20, 5)).toEqual([1, 2, 3, 4, '…', 20]);
    expect(pageList(3, 20, 5)).toEqual([1, 2, 3, 4, '…', 20]);
  });

  it('expands toward the near side when the window hits the last page', () => {
    expect(pageList(20, 20, 5)).toEqual([1, '…', 17, 18, 19, 20]);
  });

  it('always keeps first page, last page and the current page', () => {
    for (let total = 6; total <= 60; total++) {
      for (let current = 1; current <= total; current++) {
        const list = pageList(current, total, 5);
        expect(list[0]).toBe(1);
        expect(list[list.length - 1]).toBe(total);
        expect(list).toContain(current);
        expect(list.length).toBeLessThanOrEqual(DEFAULT_PAGER_LIMITS.max);
      }
    }
  });
});

describe('maxVisiblePages', () => {
  it('falls back to the wide-screen default before measurement', () => {
    expect(maxVisiblePages(0, MEDIA_PAGER_METRICS)).toBe(15);
    expect(maxVisiblePages(0, MANAGE_PAGER_METRICS)).toBe(15);
  });

  it('clamps to the configured min/max', () => {
    expect(maxVisiblePages(120, MEDIA_PAGER_METRICS)).toBe(5);
    expect(maxVisiblePages(100000, MEDIA_PAGER_METRICS)).toBe(15);
  });

  it('shrinks as the container narrows', () => {
    const wide = maxVisiblePages(1400, MANAGE_PAGER_METRICS);
    const narrow = maxVisiblePages(700, MANAGE_PAGER_METRICS);
    expect(wide).toBeGreaterThan(narrow);
    expect(wide).toBeLessThanOrEqual(15);
    expect(narrow).toBeGreaterThanOrEqual(5);
  });

  it('keeps the two pagers on their own pixel budgets', () => {
    // The manage pager reserves more width for the item counter, so it shows
    // fewer buttons than the media pager at the same container width.
    expect(maxVisiblePages(900, MANAGE_PAGER_METRICS)).toBeLessThanOrEqual(
      maxVisiblePages(900, MEDIA_PAGER_METRICS)
    );
  });
});
