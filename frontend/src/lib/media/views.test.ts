import { describe, it, expect } from 'vitest';
import {
  PROBLEM_VIEW_IDS,
  SAVED_VIEWS,
  VIEW_IDS,
  isSavedViewId,
  savedView,
  type StatsCountKey
} from './views';
import { viewToParams } from './query';
import type { SavedViewId } from './status';

/**
 * Fields the backend actually returns in `GET /api/stats/summary`
 * (see `StatsSummary` in `app/api/stats.py`). Hard-coded on purpose: if a badge
 * ever points at a field that does not exist, this list is what catches it.
 */
const BACKEND_COUNT_FIELDS = [
  'media_count',
  'problem_count',
  'missing_count',
  'no_poster_count',
  'no_metadata_count',
  'ignored_count',
  'untagged_count'
] as const;

/** The view id union, spelled out so a new view cannot be forgotten here. */
const ALL_VIEW_IDS: readonly SavedViewId[] = [
  'all',
  'problem',
  'missing',
  'no_poster',
  'metadata',
  'ignored',
  'untagged'
];

describe('SAVED_VIEWS', () => {
  it('covers exactly the SavedViewId union', () => {
    expect([...VIEW_IDS].sort()).toEqual([...ALL_VIEW_IDS].sort());
  });

  it('has unique ids', () => {
    expect(new Set(VIEW_IDS).size).toBe(VIEW_IDS.length);
  });

  it('every countKey exists on the backend StatsSummary', () => {
    const known = new Set<string>(BACKEND_COUNT_FIELDS);
    for (const view of SAVED_VIEWS) {
      if (view.countKey === null) continue;
      expect(known.has(view.countKey), `${view.id} → ${view.countKey}`).toBe(true);
    }
  });

  it('every view is labelled', () => {
    for (const view of SAVED_VIEWS) {
      expect(view.label.length).toBeGreaterThan(0);
      expect(view.hint.length).toBeGreaterThan(0);
    }
  });

  it('maps each count key to exactly one view', () => {
    const keys = SAVED_VIEWS.map((v) => v.countKey).filter((k): k is StatsCountKey => k !== null);
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe('view ids ↔ query parameters', () => {
  it('only "all" produces no parameters', () => {
    for (const id of ALL_VIEW_IDS) {
      const params = viewToParams(id);
      if (id === 'all') expect(params).toEqual({});
      else expect(Object.keys(params).length).toBeGreaterThan(0);
    }
  });

  it('a view never sends two conflicting status predicates', () => {
    for (const id of ALL_VIEW_IDS) {
      const params = viewToParams(id) as Record<string, unknown>;
      const statusKeys = ['problem', 'file_missing', 'has_poster', 'metadata_status', 'untagged'].filter(
        (k) => k in params
      );
      expect(statusKeys.length, `${id} sends ${statusKeys.join(' + ')}`).toBeLessThanOrEqual(1);
    }
  });

  it('problem / missing / no_poster / untagged share the same issue scope', () => {
    const scopes = PROBLEM_VIEW_IDS.filter((id) => id !== 'metadata').map((id) =>
      viewToParams(id)
    );
    for (const params of scopes) {
      expect(params).toMatchObject({ exclude_series: true, exclude_network: true });
    }
  });
});

describe('savedView lookup', () => {
  it('returns the view for a known id', () => {
    expect(savedView('missing').countKey).toBe('missing_count');
  });

  it('falls back to "all" for unknown or empty input', () => {
    expect(savedView('nope').id).toBe('all');
    expect(savedView(null).id).toBe('all');
    expect(savedView(undefined).id).toBe('all');
  });

  it('validates ids before use (URL values are untrusted)', () => {
    expect(isSavedViewId('problem')).toBe(true);
    expect(isSavedViewId('problem ')).toBe(false);
    expect(isSavedViewId(null)).toBe(false);
    expect(isSavedViewId(42)).toBe(false);
  });
});
