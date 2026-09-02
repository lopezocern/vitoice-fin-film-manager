import { describe, it, expect } from 'vitest';
import { buildManageParams, applyClientFilters, filterTreeByType, type ManageQueryState } from './filters';
import type { Media } from '$lib/api/media';
import type { Tag } from '$lib/api/tags';

const baseState: ManageQueryState = {
  sortField: 'created_at',
  sortOrder: 'desc',
  page: 1,
  pageSize: 50,
  libraryId: '',
  dir: '',
  type: '',
  tags: [],
  status: '',
  source: ''
};

function media(patch: Partial<Media>): Media {
  return { id: '1', title: 't', tags: [], ...patch } as unknown as Media;
}

function tag(id: string, tagTypeId: number | undefined, children?: Tag[]): Tag {
  return { id, name: id, tag_type_id: tagTypeId, created_at: '', children } as Tag;
}

describe('buildManageParams', () => {
  it('sends only paging/sort when nothing is filtered', () => {
    expect(buildManageParams(baseState)).toEqual({
      sort: 'created_at',
      order: 'desc',
      page: 1,
      page_size: 50
    });
  });

  it('maps every status to its server-side parameter', () => {
    expect(buildManageParams({ ...baseState, status: 'favorite' })).toMatchObject({ favorite: true });
    expect(buildManageParams({ ...baseState, status: 'rated' })).toMatchObject({ rating_min: 1 });
    expect(buildManageParams({ ...baseState, status: 'unrated' })).toMatchObject({ rating_max: 0 });
    expect(buildManageParams({ ...baseState, status: 'missing' })).toMatchObject({ file_missing: true });
  });

  it('leaves client-only statuses out of the request', () => {
    for (const status of ['untagged', 'problem', 'unmatched'] as const) {
      const p = buildManageParams({ ...baseState, status });
      expect(p.file_missing).toBeUndefined();
      expect(p.favorite).toBeUndefined();
    }
  });

  it('maps source filters, with "missing" folding into file_missing', () => {
    expect(buildManageParams({ ...baseState, source: 'local' })).toMatchObject({ source: 'local' });
    expect(buildManageParams({ ...baseState, source: 'network' })).toMatchObject({ source: 'network' });
    expect(buildManageParams({ ...baseState, source: 'missing' })).toMatchObject({ file_missing: true });
  });

  it('passes library / dir / type / tags through', () => {
    const p = buildManageParams({
      ...baseState,
      libraryId: '3',
      dir: 'DC',
      type: 'video',
      tags: ['a', 'b']
    });
    expect(p).toMatchObject({ library_id: '3', dir: 'DC', type: 'video', tags: ['a', 'b'] });
  });
});

describe('applyClientFilters', () => {
  const tagged = media({ tags: ['x'] });
  const untagged = media({ tags: [] });
  const noTagsField = media({ tags: undefined });
  // poster / scrape_data 逐项设置，保证三条判定互不串味
  const clean = media({ file_missing: false, poster: 'p', scrape_data: {} as Media['scrape_data'] });
  const missingFile = media({ file_missing: true, poster: 'p', scrape_data: {} as Media['scrape_data'] });
  const noPoster = media({ file_missing: false, poster: '', scrape_data: {} as Media['scrape_data'] });
  const noScrape = media({ file_missing: false, poster: 'p', scrape_data: undefined });

  it('untagged keeps only media without tags (missing array counts as untagged)', () => {
    expect(applyClientFilters([tagged, untagged, noTagsField], 'untagged')).toEqual([untagged, noTagsField]);
  });

  it('problem keeps missing files, missing posters and missing scrape data', () => {
    expect(applyClientFilters([clean, missingFile, noPoster, noScrape], 'problem')).toEqual([
      missingFile,
      noPoster,
      noScrape
    ]);
  });

  it('unmatched keeps only media with neither poster nor scrape data', () => {
    // 两者缺其一不算：有刮削数据但没海报、有海报但没刮削数据都应被排除
    const bothMissing = media({ file_missing: false, poster: '', scrape_data: undefined });
    expect(applyClientFilters([clean, noPoster, noScrape, missingFile, bothMissing], 'unmatched')).toEqual([
      bothMissing
    ]);
  });

  it('server-side statuses are a no-op', () => {
    const all = [clean, missingFile, noPoster];
    for (const status of ['', 'rated', 'unrated', 'favorite', 'missing'] as const) {
      expect(applyClientFilters(all, status)).toEqual(all);
    }
  });
});

describe('filterTreeByType', () => {
  it('keeps a matching node with its whole sub-tree', () => {
    const tree = [tag('a', 1, [tag('a1', 2), tag('a2', 9)])];
    expect(filterTreeByType(tree, 1).map((t) => t.id)).toEqual(['a']);
  });

  it('promotes matching descendants of a non-matching node', () => {
    const tree = [tag('a', 1, [tag('a1', 2), tag('b1', 3)])];
    expect(filterTreeByType(tree, 3).map((t) => t.id)).toEqual(['b1']);
  });

  it('drops sub-trees with no match', () => {
    const tree = [tag('a', 1, [tag('a1', 2)]), tag('b', 4)];
    expect(filterTreeByType(tree, 4).map((t) => t.id)).toEqual(['b']);
  });

  it('returns an empty list when nothing matches', () => {
    expect(filterTreeByType([tag('a', 1), tag('b', 1)], 7)).toEqual([]);
  });
});
