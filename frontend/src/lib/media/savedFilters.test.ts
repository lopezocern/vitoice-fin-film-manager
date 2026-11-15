import { describe, it, expect } from 'vitest';
import { DEFAULT_MEDIA_QUERY, type MediaQueryState } from './query';
import {
  applyFilter,
  FILTER_FIELDS,
  isSavedFilter,
  normalizeName,
  toFilterState
} from './savedFilters';

function query(overrides: Partial<MediaQueryState> = {}): MediaQueryState {
  return { ...DEFAULT_MEDIA_QUERY, ...overrides };
}

describe('toFilterState', () => {
  it('keeps filter fields', () => {
    const q = query({
      libraryId: '5',
      dir: 'A',
      q: 'akira',
      attribute: 'favorite',
      sort: 'rating',
      order: 'asc'
    });
    const f = toFilterState(q);
    expect(f.libraryId).toBe('5');
    expect(f.dir).toBe('A');
    expect(f.q).toBe('akira');
    expect(f.attribute).toBe('favorite');
    expect(f.sort).toBe('rating');
  });

  it('drops paging and display so saving cannot hijack them', () => {
    const q = query({ page: 7, pageSize: 200, display: 'grid' });
    const f = toFilterState(q) as Record<string, unknown>;
    expect(f.page).toBeUndefined();
    expect(f.pageSize).toBeUndefined();
    expect(f.display).toBeUndefined();
  });

  it('deep-copies arrays so later mutation does not leak into the snapshot', () => {
    const q = query({ tags: ['1', '2'] });
    const f = toFilterState(q);
    (q.tags as string[]).push('3');
    expect(f.tags).toEqual(['1', '2']);
  });

  it('only emits declared filter fields', () => {
    const f = toFilterState(query()) as Record<string, unknown>;
    expect(Object.keys(f).sort()).toEqual([...FILTER_FIELDS].sort());
  });
});

describe('applyFilter', () => {
  it('restores filter values and resets to page 1', () => {
    const current = query({ page: 9, display: 'grid', pageSize: 200, q: 'old' });
    const next = applyFilter(current, { libraryId: '5', q: 'akira', tags: ['7'] });
    expect(next.page).toBe(1);
    expect(next.libraryId).toBe('5');
    expect(next.q).toBe('akira');
    expect(next.tags).toEqual(['7']);
  });

  it('keeps display and pageSize from the current view', () => {
    const current = query({ display: 'grid', pageSize: 200 });
    const next = applyFilter(current, { q: 'x' });
    expect(next.display).toBe('grid');
    expect(next.pageSize).toBe(200);
  });

  it('falls back to defaults for fields absent from the snapshot', () => {
    // 当前状态里有 dir，但保存的筛选里没有 → 应用后应回到默认（清空目录）
    const current = query({ dir: 'A', q: 'temp' });
    const next = applyFilter(current, { q: 'akira' });
    expect(next.dir).toBe('');
    expect(next.q).toBe('akira');
  });

  it('does not mutate the current state object', () => {
    const current = query({ q: 'old' });
    applyFilter(current, { q: 'new' });
    expect(current.q).toBe('old');
  });
});

describe('isSavedFilter', () => {
  it('accepts well-formed entries', () => {
    expect(isSavedFilter({ id: 'a', name: '我的', filter: {} })).toBe(true);
  });

  it('rejects malformed entries from storage', () => {
    expect(isSavedFilter(null)).toBe(false);
    expect(isSavedFilter({})).toBe(false);
    expect(isSavedFilter({ id: '', name: 'x', filter: {} })).toBe(false);
    expect(isSavedFilter({ id: 'a', name: '   ', filter: {} })).toBe(false);
    expect(isSavedFilter({ id: 'a', name: 'x' })).toBe(false);
    expect(isSavedFilter('nope')).toBe(false);
  });
});

describe('normalizeName', () => {
  it('trims, collapses whitespace and caps length', () => {
    expect(normalizeName('  我的   筛选 ')).toBe('我的 筛选');
    expect(normalizeName('a'.repeat(40))).toHaveLength(24);
    expect(normalizeName('   ')).toBe('');
  });
});
