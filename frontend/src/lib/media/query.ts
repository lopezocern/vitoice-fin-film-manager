/**
 * One query state, one request builder.
 *
 * The manage table and the media grid used to build their request params in two
 * different places: `lib/manage/filters.ts` (tested) and an inline
 * `buildApiParams()` inside a 1,784-line route component (untested). Both
 * mapped the same backend endpoint. This module replaces both: it is pure,
 * unit-tested, and the only place that knows how a UI state becomes
 * `GET /api/media` parameters.
 *
 * Design notes
 * ------------
 * * `view` (an issue preset) and `attribute` (rated / unrated / favorite) are
 *   separate on purpose: "untagged AND rated" must be expressible.
 * * Bucket filters (resolution / duration) are translated into exact
 *   min/max parameters rather than filtered client-side — the backend has
 *   supported that all along, and the media page was already double-filtering.
 */
import type { MediaListParams, MediaSortField } from '$lib/api/media';
import type { AttributeStatus, SavedViewId } from './status';
import { savedView } from './views';

// Structural duplicates of the unions in `$lib/components/media/types`. Kept
// local so this module has no dependency on component internals; PR3 points the
// component file at these definitions to end the duplication.
export type ResolutionFilter = '4k' | '1080p' | '720p' | '480p' | 'other' | '';
export type DurationFilter = 'short' | 'medium' | 'long' | '';
export type ContentSection = 'all' | 'movie' | 'tv' | 'image' | 'audio';
export type MediaSourceFilter = '' | 'local' | 'network';
export type DisplayMode = 'table' | 'grid';

/** Everything one media list needs in order to render itself. */
export interface MediaQueryState {
  // scope
  libraryId: string;
  dir: string;
  // content
  section: ContentSection;
  // facets
  genre: string;
  country: string;
  year: number | null;
  resolution: ResolutionFilter;
  duration: DurationFilter;
  ratingMin: number | null;
  // user-data attribute (single select, mirrors the manage toolbar)
  attribute: AttributeStatus;
  // tags
  tags: string[];
  tagMatch: 'any' | 'all';
  tagTypeId: number | null;
  // issue view + source
  view: SavedViewId;
  source: MediaSourceFilter;
  // text search
  q: string;
  // sort / paging
  sort: MediaSortField;
  order: 'asc' | 'desc';
  page: number;
  pageSize: number;
  // presentation
  display: DisplayMode;
}

export const DEFAULT_PAGE_SIZE = 50;

/** Sort fields the backend accepts (see `_ALLOWED_SORT_FIELDS` in api/media.py). */
export const SORT_FIELDS = [
  'created_at',
  'updated_at',
  'filename',
  'size',
  'duration',
  'rating'
] as const;

/** Bucket values, used to validate untrusted URL input. */
export const RESOLUTIONS = ['4k', '1080p', '720p', '480p', 'other'] as const;
export const DURATIONS = ['short', 'medium', 'long'] as const;

export const DEFAULT_MEDIA_QUERY: MediaQueryState = {
  libraryId: '',
  dir: '',
  section: 'all',
  genre: '',
  country: '',
  year: null,
  resolution: '',
  duration: '',
  ratingMin: null,
  attribute: '',
  tags: [],
  tagMatch: 'any',
  tagTypeId: null,
  view: 'all',
  source: '',
  q: '',
  sort: 'created_at',
  order: 'desc',
  page: 1,
  pageSize: DEFAULT_PAGE_SIZE,
  display: 'table'
};

// `legacyClientStatuses` 过渡开关已随旧管理表一起删除（PR6）：
// `problem` / `untagged` 现在一律走服务端谓词。

// ---------------------------------------------------------------------------
// Bucket → parameter translation
// ---------------------------------------------------------------------------

/** Resolution bucket → inclusive height range. */
export function resolutionToParams(
  bucket: ResolutionFilter
): Pick<MediaListParams, 'resolution_min' | 'resolution_max'> {
  switch (bucket) {
    case '4k':
      return { resolution_min: 2160 };
    case '1080p':
      return { resolution_min: 1080, resolution_max: 2159 };
    case '720p':
      return { resolution_min: 720, resolution_max: 1079 };
    case '480p':
      return { resolution_min: 480, resolution_max: 719 };
    case 'other':
      return { resolution_max: 479 };
    default:
      return {};
  }
}

/** Duration bucket → inclusive seconds range. Boundaries match the media page. */
export function durationToParams(
  bucket: DurationFilter
): Pick<MediaListParams, 'duration_min' | 'duration_max'> {
  switch (bucket) {
    case 'short':
      return { duration_max: 600 };
    case 'medium':
      return { duration_min: 600, duration_max: 3600 };
    case 'long':
      return { duration_min: 3600 };
    default:
      return {};
  }
}

/** Content section → type / series parameters. */
export function sectionToParams(
  section: ContentSection
): Pick<MediaListParams, 'type' | 'has_series'> {
  switch (section) {
    case 'movie':
      // A movie is a video that does not belong to a series.
      return { type: 'video', has_series: false };
    case 'tv':
      return { has_series: true };
    case 'image':
      return { type: 'image' };
    case 'audio':
      return { type: 'audio' };
    default:
      return {};
  }
}

// ---------------------------------------------------------------------------
// Saved view → parameters (must mirror app/services/media_query.py)
// ---------------------------------------------------------------------------

/** Issue scope: standalone, non-network rows only. */
const ISSUE_SCOPE = { exclude_series: true, exclude_network: true } as const;

export function viewToParams(view: SavedViewId): MediaListParams {
  // The id is validated here so a bad URL value cannot silently widen the list.
  if (!savedView(view) || savedView(view).id !== view) return {};

  switch (view) {
    case 'missing':
      return { file_missing: true, ...ISSUE_SCOPE };
    case 'no_poster':
      return { has_poster: false, ...ISSUE_SCOPE };
    case 'metadata':
      // Keeps the long-standing semantics: episodes excluded, network media
      // included. Must match stats.no_metadata_count.
      return { metadata_status: 'missing', exclude_series: true };
    case 'ignored':
      return { metadata_status: 'ignored' };
    case 'untagged':
      return { untagged: true, ...ISSUE_SCOPE };
    case 'problem':
      return { problem: true, ...ISSUE_SCOPE };
    case 'all':
    default:
      return {};
  }
}

// ---------------------------------------------------------------------------
// The builder
// ---------------------------------------------------------------------------

/** Turn a `MediaQueryState` into `mediaApi.list()` arguments. */
export function buildMediaQuery(state: MediaQueryState): MediaListParams {
  const params: MediaListParams = {
    sort: state.sort,
    order: state.order,
    page: state.page,
    page_size: state.pageSize
  };

  // scope
  if (state.libraryId) params.library_id = state.libraryId;
  if (state.dir) params.dir = state.dir;

  // content + facets
  Object.assign(params, sectionToParams(state.section));
  if (state.genre) params.genre = state.genre;
  if (state.country) params.country = state.country;
  if (state.year !== null) params.year = state.year;
  Object.assign(params, resolutionToParams(state.resolution));
  Object.assign(params, durationToParams(state.duration));

  // attribute — an explicit attribute wins over the free-floating rating slider
  if (state.attribute === 'rated') params.rating_min = 1;
  else if (state.attribute === 'unrated') params.rating_max = 0;
  else if (state.attribute === 'favorite') params.favorite = true;
  else if (state.ratingMin !== null) params.rating_min = state.ratingMin;

  // tags
  if (state.tags.length > 0) {
    params.tags = state.tags;
    if (state.tags.length > 1 && state.tagMatch === 'all') params.tag_match = 'all';
  }

  // text
  if (state.q.trim()) params.q = state.q.trim();

  // source (mutually exclusive with the issue views that already imply it)
  if (state.source) params.source = state.source;

  // issue view last: it carries the scope flags and must not be overridden
  Object.assign(params, viewToParams(state.view));

  return params;
}

// ---------------------------------------------------------------------------
// URL (de)serialization
// ---------------------------------------------------------------------------

const URL_KEYS = {
  view: 'view',
  library: 'lib',
  dir: 'dir',
  section: 'section',
  genre: 'genre',
  country: 'country',
  year: 'year',
  resolution: 'res',
  duration: 'dur',
  rating: 'rating',
  attribute: 'attr',
  tags: 'tags',
  tagMatch: 'tagmatch',
  tagType: 'tagtype',
  source: 'source',
  q: 'q',
  sort: 'sort',
  order: 'order',
  page: 'page',
  size: 'size',
  display: 'display'
} as const;

/** Read a query state out of URL params, ignoring unknown values. */
export function parseMediaQuery(
  search: URLSearchParams | string,
  base: MediaQueryState = DEFAULT_MEDIA_QUERY
): MediaQueryState {
  const sp = typeof search === 'string' ? new URLSearchParams(search) : search;
  const next: MediaQueryState = { ...base, tags: [...base.tags] };

  const str = (key: string): string => sp.get(key) ?? '';

  const view = str(URL_KEYS.view);
  if (view && savedView(view).id === view) next.view = view as SavedViewId;

  next.libraryId = str(URL_KEYS.library);
  // dir 依附于库：没有 library 的 dir 一律丢弃（旧链接/手改 URL 时不会悄悄生效）
  next.dir = next.libraryId ? str(URL_KEYS.dir) : '';

  const section = str(URL_KEYS.section);
  if (['movie', 'tv', 'image', 'audio'].includes(section)) {
    next.section = section as ContentSection;
  } else {
    next.section = 'all';
  }

  next.genre = str(URL_KEYS.genre);
  next.country = str(URL_KEYS.country);

  const year = Number(str(URL_KEYS.year));
  next.year = str(URL_KEYS.year) !== '' && Number.isFinite(year) ? year : null;

  const res = str(URL_KEYS.resolution);
  next.resolution = (RESOLUTIONS as readonly string[]).includes(res)
    ? (res as ResolutionFilter)
    : '';

  const dur = str(URL_KEYS.duration);
  next.duration = (DURATIONS as readonly string[]).includes(dur) ? (dur as DurationFilter) : '';

  const rating = Number(str(URL_KEYS.rating));
  next.ratingMin = str(URL_KEYS.rating) !== '' && Number.isFinite(rating) ? rating : null;

  const attr = str(URL_KEYS.attribute);
  next.attribute = (['rated', 'unrated', 'favorite'] as const).includes(attr as never)
    ? (attr as AttributeStatus)
    : '';

  const tags = str(URL_KEYS.tags);
  next.tags = tags ? tags.split(',').map((t) => t.trim()).filter(Boolean) : [];

  next.tagMatch = str(URL_KEYS.tagMatch) === 'all' ? 'all' : 'any';

  const tagType = Number(str(URL_KEYS.tagType));
  next.tagTypeId = str(URL_KEYS.tagType) !== '' && Number.isFinite(tagType) ? tagType : null;

  const source = str(URL_KEYS.source);
  next.source = source === 'local' || source === 'network' ? source : '';

  next.q = str(URL_KEYS.q);

  const sort = str(URL_KEYS.sort);
  // URL values are untrusted: an unknown sort would be silently swallowed by
  // the backend, so validate here and keep the previous value instead.
  if ((SORT_FIELDS as readonly string[]).includes(sort)) next.sort = sort as MediaSortField;

  next.order = str(URL_KEYS.order) === 'asc' ? 'asc' : 'desc';

  const page = Number(str(URL_KEYS.page));
  next.page = Number.isFinite(page) && page >= 1 ? Math.floor(page) : 1;

  const size = Number(str(URL_KEYS.size));
  next.pageSize = Number.isFinite(size) && size >= 1 ? Math.floor(size) : base.pageSize;

  const display = str(URL_KEYS.display);
  next.display = display === 'grid' ? 'grid' : 'table';

  return next;
}

/**
 * Write a query state into URL params, dropping defaults.
 *
 * Kept symmetric with {@link parseMediaQuery} so a round-trip is lossless and
 * the URL never carries empty parameters.
 */
export function serializeMediaQuery(state: MediaQueryState): URLSearchParams {
  const sp = new URLSearchParams();
  const put = (key: string, value: string | number | null | undefined): void => {
    if (value === null || value === undefined || value === '') return;
    sp.set(key, String(value));
  };

  if (state.view !== 'all') put(URL_KEYS.view, state.view);
  put(URL_KEYS.library, state.libraryId);
  // 目录依附于库：没有库就不写 dir，避免"清掉库后残留 dir 在下次选库时突然生效"
  if (state.libraryId) put(URL_KEYS.dir, state.dir);
  if (state.section !== 'all') put(URL_KEYS.section, state.section);
  put(URL_KEYS.genre, state.genre);
  put(URL_KEYS.country, state.country);
  put(URL_KEYS.year, state.year);
  put(URL_KEYS.resolution, state.resolution);
  put(URL_KEYS.duration, state.duration);
  put(URL_KEYS.rating, state.ratingMin);
  put(URL_KEYS.attribute, state.attribute);
  put(URL_KEYS.tags, state.tags.length ? state.tags.join(',') : '');
  if (state.tags.length > 1 && state.tagMatch === 'all') put(URL_KEYS.tagMatch, 'all');
  put(URL_KEYS.tagType, state.tagTypeId);
  put(URL_KEYS.source, state.source);
  put(URL_KEYS.q, state.q.trim());
  if (state.sort !== DEFAULT_MEDIA_QUERY.sort) put(URL_KEYS.sort, state.sort);
  if (state.order !== DEFAULT_MEDIA_QUERY.order) put(URL_KEYS.order, state.order);
  if (state.page !== 1) put(URL_KEYS.page, state.page);
  if (state.pageSize !== DEFAULT_PAGE_SIZE) put(URL_KEYS.size, state.pageSize);
  if (state.display !== 'table') put(URL_KEYS.display, state.display);

  return sp;
}

/** True when the state would produce more than the default listing. */
export function isFiltered(state: MediaQueryState): boolean {
  const params = buildMediaQuery(state);
  return Object.keys(params).some(
    (key) => !['sort', 'order', 'page', 'page_size'].includes(key)
  );
}

/**
 * 把一次界面操作合并进查询状态。
 *
 * 唯一的规则性逻辑：**换库必然清目录**。
 * 目录是"某库内的相对路径"，换了库之后旧 dir 在新库里几乎必然不存在，
 * 表现就是"侧栏点别处/工具栏换库后右侧列表空了但面包屑还挂着旧目录"。
 * 放在这里而不是组件里，是因为工具栏、侧栏、批量操作都会改 libraryId，
 * 每个调用点各自记得清 dir 是迟早会漏的。
 *
 * 显式传入 dir 的操作（例如点目录树）不受影响。
 */
export function applyPatch(
  state: MediaQueryState,
  partial: Partial<MediaQueryState>
): MediaQueryState {
  const next: MediaQueryState = { ...state, ...partial, tags: [...(partial.tags ?? state.tags)] };
  if (partial.libraryId !== undefined && partial.libraryId !== state.libraryId && partial.dir === undefined) {
    next.dir = '';
  }
  // 库被清空时目录随之失效
  if (!next.libraryId) next.dir = '';
  return next;
}
