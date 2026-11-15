import { describe, it, expect } from 'vitest';
import {
  applyPatch,
  DEFAULT_MEDIA_QUERY,
  buildMediaQuery,
  durationToParams,
  isFiltered,
  parseMediaQuery,
  resolutionToParams,
  sectionToParams,
  serializeMediaQuery,
  viewToParams,
  type MediaQueryState
} from './query';
import type { SavedViewId } from './status';

const base: MediaQueryState = { ...DEFAULT_MEDIA_QUERY };

/** Every issue view and the exact request it must produce. */
const VIEW_PARAMS: Record<SavedViewId, Record<string, unknown>> = {
  all: {},
  problem: { problem: true, exclude_series: true, exclude_network: true },
  missing: { file_missing: true, exclude_series: true, exclude_network: true },
  no_poster: { has_poster: false, exclude_series: true, exclude_network: true },
  metadata: { metadata_status: 'missing', exclude_series: true },
  ignored: { metadata_status: 'ignored' },
  untagged: { untagged: true, exclude_series: true, exclude_network: true }
};

describe('buildMediaQuery — baseline', () => {
  it('sends only paging and sort when nothing is filtered', () => {
    expect(buildMediaQuery(base)).toEqual({
      sort: 'created_at',
      order: 'desc',
      page: 1,
      page_size: 50
    });
  });

  it('reports an unfiltered state as unfiltered', () => {
    expect(isFiltered(base)).toBe(false);
    expect(isFiltered({ ...base, view: 'missing' })).toBe(true);
    expect(isFiltered({ ...base, q: 'dune' })).toBe(true);
  });
});

describe('viewToParams — mirrors app/services/media_query.py', () => {
  for (const [view, expected] of Object.entries(VIEW_PARAMS)) {
    it(`maps "${view}" to ${JSON.stringify(expected)}`, () => {
      expect(viewToParams(view as SavedViewId)).toEqual(expected);
    });
  }

  it('keeps network media in the metadata view (long-standing semantics)', () => {
    // stats.no_metadata_count includes network media, so the view must too —
    // otherwise the badge and the list disagree.
    expect(viewToParams('metadata')).not.toHaveProperty('exclude_network');
  });

  it('applies issue scope to every other issue view', () => {
    for (const view of ['problem', 'missing', 'no_poster', 'untagged'] as const) {
      expect(viewToParams(view)).toMatchObject({
        exclude_series: true,
        exclude_network: true
      });
    }
  });

  it('falls back to no parameters for an unknown view id', () => {
    expect(viewToParams('bogus' as SavedViewId)).toEqual({});
  });
});

describe('buildMediaQuery — content section', () => {
  it('maps each section to type / series parameters', () => {
    expect(sectionToParams('movie')).toEqual({ type: 'video', has_series: false });
    expect(sectionToParams('tv')).toEqual({ has_series: true });
    expect(sectionToParams('image')).toEqual({ type: 'image' });
    expect(sectionToParams('audio')).toEqual({ type: 'audio' });
    expect(sectionToParams('all')).toEqual({});
  });

  it('carries the section into the request', () => {
    expect(buildMediaQuery({ ...base, section: 'movie' })).toMatchObject({
      type: 'video',
      has_series: false
    });
  });
});

describe('buildMediaQuery — bucket filters go to the server', () => {
  it('translates resolution buckets into inclusive ranges', () => {
    expect(resolutionToParams('4k')).toEqual({ resolution_min: 2160 });
    expect(resolutionToParams('1080p')).toEqual({ resolution_min: 1080, resolution_max: 2159 });
    expect(resolutionToParams('720p')).toEqual({ resolution_min: 720, resolution_max: 1079 });
    expect(resolutionToParams('480p')).toEqual({ resolution_min: 480, resolution_max: 719 });
    expect(resolutionToParams('other')).toEqual({ resolution_max: 479 });
    expect(resolutionToParams('')).toEqual({});
  });

  it('translates duration buckets into inclusive ranges', () => {
    expect(durationToParams('short')).toEqual({ duration_max: 600 });
    expect(durationToParams('medium')).toEqual({ duration_min: 600, duration_max: 3600 });
    expect(durationToParams('long')).toEqual({ duration_min: 3600 });
    expect(durationToParams('')).toEqual({});
  });

  it('never does bucket filtering client-side (regression: media page double-filtered)', () => {
    const p = buildMediaQuery({ ...base, resolution: '1080p', duration: 'long' });
    expect(p).toMatchObject({
      resolution_min: 1080,
      resolution_max: 2159,
      duration_min: 3600
    });
  });
});

describe('buildMediaQuery — attribute vs rating slider', () => {
  it('maps the three attributes', () => {
    expect(buildMediaQuery({ ...base, attribute: 'rated' })).toMatchObject({ rating_min: 1 });
    expect(buildMediaQuery({ ...base, attribute: 'unrated' })).toMatchObject({ rating_max: 0 });
    expect(buildMediaQuery({ ...base, attribute: 'favorite' })).toMatchObject({ favorite: true });
  });

  it('prefers an explicit attribute over the free-floating rating slider', () => {
    const p = buildMediaQuery({ ...base, attribute: 'favorite', ratingMin: 4 });
    expect(p).toMatchObject({ favorite: true });
    expect(p.rating_min).toBeUndefined();
  });

  it('uses the slider when no attribute is selected', () => {
    expect(buildMediaQuery({ ...base, ratingMin: 4 })).toMatchObject({ rating_min: 4 });
  });
});

describe('buildMediaQuery — tags, source, search', () => {
  it('sends one tag without tag_match, several tags with it', () => {
    expect(buildMediaQuery({ ...base, tags: ['a'] })).toMatchObject({ tags: ['a'] });
    expect(buildMediaQuery({ ...base, tags: ['a'] })).not.toHaveProperty('tag_match');

    expect(buildMediaQuery({ ...base, tags: ['a', 'b'], tagMatch: 'all' })).toMatchObject({
      tags: ['a', 'b'],
      tag_match: 'all'
    });
  });

  it('keeps "any" implicit so the backend default is used', () => {
    expect(buildMediaQuery({ ...base, tags: ['a', 'b'], tagMatch: 'any' })).not.toHaveProperty(
      'tag_match'
    );
  });

  it('passes scope and user-data filters through', () => {
    const p = buildMediaQuery({ ...base, libraryId: '3', dir: 'DC', source: 'network' });
    expect(p).toMatchObject({ library_id: '3', dir: 'DC', source: 'network' });
  });

  it('trims the search text and omits it when blank', () => {
    expect(buildMediaQuery({ ...base, q: '  dune ' })).toMatchObject({ q: 'dune' });
    expect(buildMediaQuery({ ...base, q: '   ' })).not.toHaveProperty('q');
  });

  it('treats year 0 as "explicitly unknown year" (not as "no filter")', () => {
    expect(buildMediaQuery({ ...base, year: 0 })).toMatchObject({ year: 0 });
    expect(buildMediaQuery({ ...base, year: null })).not.toHaveProperty('year');
  });
});

describe('buildMediaQuery — view composes with the other filters', () => {
  it('keeps facets while applying the view scope', () => {
    const p = buildMediaQuery({
      ...base,
      view: 'untagged',
      genre: 'Drama',
      libraryId: '2',
      attribute: 'rated'
    });
    expect(p).toMatchObject({
      untagged: true,
      exclude_series: true,
      exclude_network: true,
      genre: 'Drama',
      library_id: '2',
      rating_min: 1
    });
  });
});

describe('URL round-trip', () => {
  const cases: MediaQueryState[] = [
    base,
    { ...base, view: 'missing' },
    {
      ...base,
      view: 'metadata',
      libraryId: '7',
      dir: 'Movies/2024',
      section: 'movie',
      genre: 'SciFi',
      country: 'CN',
      year: 2024,
      resolution: '1080p',
      duration: 'long',
      attribute: 'favorite',
      tags: ['a', 'b'],
      tagMatch: 'all',
      tagTypeId: 2,
      source: 'local',
      q: 'dune',
      sort: 'duration',
      order: 'asc',
      page: 3,
      pageSize: 200,
      display: 'grid'
    }
  ];

  for (const state of cases) {
    it(`round-trips view=${state.view} page=${state.page}`, () => {
      expect(parseMediaQuery(serializeMediaQuery(state))).toEqual(state);
    });
  }

  it('drops default values from the URL', () => {
    expect(serializeMediaQuery(base).toString()).toBe('');
  });

  it('ignores unknown or malformed values instead of throwing', () => {
    const parsed = parseMediaQuery(
      '?view=nope&section=bogus&res=8k&dur=xx&attr=maybe&source=ftp&page=-3&sort=huh'
    );
    expect(parsed.view).toBe('all');
    expect(parsed.section).toBe('all');
    expect(parsed.resolution).toBe('');
    expect(parsed.duration).toBe('');
    expect(parsed.attribute).toBe('');
    expect(parsed.source).toBe('');
    expect(parsed.page).toBe(1);
    expect(parsed.sort).toBe('created_at');
  });

  it('parses the documented short keys', () => {
    const parsed = parseMediaQuery(
      '?view=no_poster&lib=4&res=4k&dur=short&attr=rated&tags=a,b&tagmatch=all&tagtype=1&page=2&size=100&display=grid'
    );
    expect(parsed).toMatchObject({
      view: 'no_poster',
      libraryId: '4',
      resolution: '4k',
      duration: 'short',
      attribute: 'rated',
      tags: ['a', 'b'],
      tagMatch: 'all',
      tagTypeId: 1,
      page: 2,
      pageSize: 100,
      display: 'grid'
    });
  });
});

describe('applyPatch — 换库必然清目录', () => {
  const base = (over: Partial<MediaQueryState> = {}): MediaQueryState => ({
    ...DEFAULT_MEDIA_QUERY,
    libraryId: '5',
    dir: 'A',
    ...over
  });

  it('clears dir when the library actually changes', () => {
    const next = applyPatch(base(), { libraryId: '6' });
    expect(next.libraryId).toBe('6');
    expect(next.dir).toBe('');
  });

  it('keeps dir when the patch does not touch the library', () => {
    const next = applyPatch(base(), { q: 'akira' });
    expect(next.dir).toBe('A');
    expect(next.q).toBe('akira');
  });

  it('keeps dir when the patch sets the same library', () => {
    const next = applyPatch(base(), { libraryId: '5', page: 2 });
    expect(next.dir).toBe('A');
    expect(next.page).toBe(2);
  });

  it('lets an explicit dir win (clicking a folder in the tree)', () => {
    const next = applyPatch(base(), { libraryId: '6', dir: 'B' });
    expect(next.dir).toBe('B');
  });

  it('drops dir when the library is cleared', () => {
    const next = applyPatch(base(), { libraryId: '' });
    expect(next.libraryId).toBe('');
    expect(next.dir).toBe('');
  });

  it('does not mutate the input state and copies tags', () => {
    const state = base({ tags: ['1'] });
    const next = applyPatch(state, { page: 3 });
    expect(state.page).toBe(1);
    next.tags.push('2');
    expect(state.tags).toEqual(['1']);
  });
});

describe('dir 依附于库（URL 两侧都遵守）', () => {
  it('serialize drops dir when there is no library', () => {
    const sp = serializeMediaQuery({ ...DEFAULT_MEDIA_QUERY, libraryId: '', dir: 'A' });
    expect(sp.get('dir')).toBeNull();
  });

  it('serialize keeps dir when a library is set', () => {
    const sp = serializeMediaQuery({ ...DEFAULT_MEDIA_QUERY, libraryId: '5', dir: 'A' });
    expect(sp.get('dir')).toBe('A');
  });

  it('parse ignores a stray dir without a library', () => {
    const q = parseMediaQuery('?dir=A&q=x');
    expect(q.dir).toBe('');
    expect(q.libraryId).toBe('');
  });

  it('parse keeps dir when the library is present', () => {
    const q = parseMediaQuery('?lib=5&dir=A');
    expect(q.dir).toBe('A');
  });
});
