import { client, BASE_URL, ApiError, type Params } from './client';

export type MediaType = 'video' | 'audio' | 'image';

export type UrlRole = 'source' | 'reference';

/** Backend media_type — source type (distinct from content MediaType above). */
export type SourceMediaType = 'local' | 'network' | 'both' | 'offline';

export interface MediaUrl {
  id: number;
  media_id: number;
  url: string;
  url_role: UrlRole;
  title: string | null;
  platform: string | null;
  /** 在线源名称（从 /online 入库时写入） */
  source_name?: string | null;
  source_id?: string | null;
  /** 线路 flag，如 lzm3u8 */
  line_name?: string | null;
  /** 集名，如 第01集 */
  episode_name?: string | null;
  episode_index?: number | null;
  is_expired: boolean;
  created_at: string;
  updated_at: string;
}

export interface ScrapeData {
  tagline?: string;
  tmdb_rating?: number;
  tmdb_vote_count?: number;
  tmdb_id?: number;
  original_title?: string;
  original_language?: string;
  status?: string;
  homepage?: string;
  imdb_id?: string;
  genres?: string[];
  production_countries?: string[];
  production_companies?: string[];
  spoken_languages?: string[];
  runtime_minutes?: number;
  budget?: number;
  revenue?: number;
  belongs_to_collection?: string;
  episode_run_time?: number[] | number;
  number_of_seasons?: number;
  number_of_episodes?: number;
  in_production?: boolean;
  networks?: string[];
  created_by?: string[];
  cast?: { name: string; character?: string; profile_path?: string | null }[];
  directors?: string[];
  writers?: string[];
  // AV-specific (JavBus)
  fancode?: string;
  actresses?: string[];
  studio?: string;
  label?: string;
  series?: string;
  cover_url?: string;
  // TMDB movie/tv backdrop (detail-page hero atmosphere); AV has none
  backdrop_path?: string | null;
}

/** Returns true if the media was scraped as AV (JavBus) — used to pick the
 *  correct poster aspect ratio (landscape for AV covers vs portrait for TMDB). */
export function isAvMedia(media: Media): boolean {
  return !!media.scrape_data?.fancode;
}

/** Returns true if the media has at least one source URL (playable network resource). */
export function hasNetworkSource(media: Media): boolean {
  return !!media.urls?.some((u) => u.url_role === 'source' && !u.is_expired);
}

/** Returns the first playable source URL, or null if none. */
export function getNetworkSourceUrl(media: Media): string | null {
  const source = media.urls?.find((u) => u.url_role === 'source' && !u.is_expired);
  return source?.url ?? null;
}

/** 片段标记（对应后端 SegmentResponse：segments 表权威数据）。 */
export interface SegmentItem {
  id: number;
  media_id: number;
  name: string;
  start_time: number;
  end_time: number | null;
  description?: string | null;
  color?: string | null;
  sort_order: number;
}

export interface Media {
  id: string;
  library_id: string;
  path: string;
  filename: string;
  title?: string;
  year?: number;
  release_date?: string;  // YYYY-MM-DD from TMDB
  season_number?: number;
  episode_number?: number;
  series_id?: number;
  series_title?: string;
  description?: string;
  type: MediaType;
  source_type: SourceMediaType;
  file_missing: boolean;
  metadata_ignored?: boolean;
  /** 详情接口探测：该本地文件是否会被后端转码（转码流不支持 Range，seek 需走重载） */
  needs_transcode?: boolean;
  size: number;
  duration?: number;
  width?: number;
  height?: number;
  thumbnail?: string;
  poster?: string;
  /** 4×4 缩略图集是否已生成（列表接口按文件存在性返回） */
  has_contact_sheet?: boolean;
  rating: number;
  favorite: boolean;
  tags: string[];
  metadata?: Record<string, unknown>;
  scrape_data?: ScrapeData;
  urls?: MediaUrl[];
  segments?: SegmentItem[];
  created_at: string;
  updated_at: string;
  last_played_at?: string;
}

/**
 * Backend wire shape of a Media row (see `MediaResponse` in the API).
 *
 * Declared as a type alias, not an interface, on purpose: `normalizeMedia`
 * spreads the payload into `Media.metadata` (`Record<string, unknown>`), and
 * only type aliases get an implicit index signature. Every field is optional
 * and nullable because list endpoints omit fields the detail endpoint returns.
 */
export type MediaPayload = {
  id?: number | string | null;
  library_id?: number | string | null;
  file_path?: string | null;
  /** 未脱敏的真实路径，仅详情接口返回；mpv 内核读文件用。 */
  local_path?: string | null;
  file_name?: string | null;
  mime_type?: string | null;
  title?: string | null;
  year?: number | null;
  release_date?: string | null;
  season_number?: number | null;
  episode_number?: number | null;
  series_id?: number | null;
  series_title?: string | null;
  description?: string | null;
  media_type?: SourceMediaType | null;
  file_missing?: boolean | null;
  metadata_ignored?: boolean | null;
  needs_transcode?: boolean | null;
  file_size?: number | null;
  duration?: number | null;
  width?: number | null;
  height?: number | null;
  thumbnail_path?: string | null;
  poster_path?: string | null;
  has_contact_sheet?: boolean | null;
  rating?: number | null;
  is_favorite?: boolean | null;
  /** Attached tag objects; only their `id` survives normalization. */
  tags?: Array<{ id?: number | string; name?: string } | null> | null;
  playback_position?: number | null;
  scrape_data?: ScrapeData | null;
  urls?: MediaUrl[] | null;
  segments?: SegmentItem[] | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_played_at?: string | null;
};

/** GET /api/media — paginated list, items still un-normalized. */
export interface MediaListRawResponse {
  items: Partial<MediaPayload>[];
  total?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}

/** One entry of GET /api/media/home before normalization. */
export type MediaHomeRawItem =
  | { kind: 'media'; data: Partial<MediaPayload> | null }
  | { kind: 'series'; data: import('./series').Series };

export interface MediaHomeRawResponse {
  continue_watching?: MediaHomeRawItem[];
  recently_added?: MediaHomeRawItem[];
  recently_played?: MediaHomeRawItem[];
  recommendations?: MediaHomeRawItem[];
}

export type MediaHomeItem =
  | { kind: 'media'; data: Media }
  | { kind: 'series'; data: import('./series').Series };

export interface MediaHomeResponse {
  continue_watching: MediaHomeItem[];
  recently_added: MediaHomeItem[];
  recently_played: MediaHomeItem[];
  recommendations: MediaHomeItem[];
}

export type MediaSortField =
  | 'created_at'
  | 'updated_at'
  | 'filename'
  | 'size'
  | 'duration'
  | 'rating';

export interface MediaListParams {
  library_id?: string;
  dir?: string;
  type?: MediaType;
  source?: 'local' | 'network' | 'offline';
  file_missing?: boolean;
  q?: string;
  tags?: string[];
  favorite?: boolean;
  rating_min?: number;
  rating_max?: number;
  duration_min?: number;
  duration_max?: number;
  resolution_min?: number;
  resolution_max?: number;
  in_progress?: boolean;
  genre?: string;
  country?: string;
  year?: number;
  sort?: MediaSortField;
  order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
  exclude_series?: boolean;
  has_series?: boolean;
  tag_match?: 'any' | 'all';
  // --- Issue predicates (mirror app/services/media_query.py) ---
  /** `false` → neither a poster nor a thumbnail exists. */
  has_poster?: boolean;
  /** `missing` = needs work, `ignored` = user opted out, `complete` = done. */
  metadata_status?: MetadataStatus;
  /** `true` → the item has no tags at all. */
  untagged?: boolean;
  /** Exclude NETWORK-only media (they never have a local file). */
  exclude_network?: boolean;
  /** Union of file_missing / no_poster / metadata_missing — never a sum. */
  problem?: boolean;
  /**
   * 只取匹配的 id（跨页全选用）。忽略分页，`items` 返回空数组。
   * 后端上限 20000 条，超出会 413 并提示缩小范围。
   */
  ids_only?: boolean;
}

/** GET /api/media?ids_only=true 的返回（items 为空）。 */
export interface MediaIdListResponse {
  total: number;
  ids: number[];
}

export type MetadataStatus = 'missing' | 'ignored' | 'complete';

export interface MediaListResponse {
  items: Media[];
  total: number;
  page: number;
  page_size: number;
  total_pages?: number;
}

export interface MediaFacetItem {
  value: string;
  count: number;
}

export interface MediaTagFacet extends MediaFacetItem {
  id: number;
  color?: string | null;
}

export interface MediaFacets {
  all: number;
  movies: number;
  series: number;
  episodes: number;
  images: number;
  audio: number;
  genres: MediaFacetItem[];
  countries: MediaFacetItem[];
  years: MediaFacetItem[];
  tags: MediaTagFacet[];
}

export interface UpdateMediaInput {
  rating?: number;
  favorite?: boolean;
  tags?: string[];
  thumbnail?: string;
  title?: string;
  year?: number;
  description?: string;
  season_number?: number;
  episode_number?: number;
  metadata?: Record<string, unknown>;
}

/** AI 二次刮削结果（对应后端 AIRescrapeResponse）。 */
export interface AIRescrapeResponse {
  success: boolean;
  suggested_title: string | null;
  suggested_year: number | null;
  matched_title: string | null;
  matched_year: number | null;
  message: string;
}

/** AI 打标建议（对应后端 AITagSuggestion）。 */
export interface AITagSuggestion {
  name: string;
  type: string;
  confidence: number;
}

/** 播放结束推荐项（GET /media/{id}/related）。 */
export interface RelatedMediaItem {
  id: number;
  title: string;
  year: number | null;
  duration: number | null;
  has_thumbnail: boolean;
  reason: 'series' | 'tag' | 'library';
}

/** 缺失文件找回 — 一对「缺失记录 → 存活同名记录」。 */
export interface ReconcilePair {
  missing_id: number;
  live_id: number;
  file_name: string;
  file_size: number | null;
  size_matched: boolean;
  missing_path: string | null;
  live_path: string | null;
  missing_progress: number;
  live_progress: number;
  live_watched: boolean;
  missing_tag_count: number;
  live_tag_count: number;
}

export interface ReconcilePreview {
  pairs: ReconcilePair[];
  count: number;
}


/** Map a backend Media object to the frontend-shaped Media object. */
export function normalizeMedia(raw: Partial<MediaPayload> | null | undefined): Media {
  const mime: string = raw?.mime_type ?? '';
  let type: MediaType = 'image';
  if (mime.startsWith('video')) type = 'video';
  else if (mime.startsWith('audio')) type = 'audio';
  else {
    // Fallback: detect from file extension when mime_type is missing
    const ext = (raw?.file_name ?? '').toLowerCase();
    if (/\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|ts|rmvb)$/.test(ext)) type = 'video';
    else if (/\.(mp3|flac|wav|aac|ogg|wma|m4a|ape)$/.test(ext)) type = 'audio';
  }

  // Tags from the API are full objects [{id, name, ...}]; store IDs as strings
  const tags: string[] = Array.isArray(raw?.tags)
    ? raw.tags.map((t) => (t && t.id !== undefined ? String(t.id) : ''))
    : [];

  return {
    id: String(raw?.id ?? ''),
    library_id: String(raw?.library_id ?? ''),
    path: raw?.file_path ?? '',
    filename: raw?.file_name ?? '',
    title: raw?.title ?? undefined,
    year: raw?.year ?? undefined,
    release_date: raw?.release_date ?? undefined,
    season_number: raw?.season_number ?? undefined,
    episode_number: raw?.episode_number ?? undefined,
    series_id: raw?.series_id ?? undefined,
    series_title: raw?.series_title ?? undefined,
    description: raw?.description ?? undefined,
    type,
    source_type: raw?.media_type ?? 'local',
    file_missing: !!raw?.file_missing,
    metadata_ignored: !!raw?.metadata_ignored,
    needs_transcode: !!raw?.needs_transcode,
    size: raw?.file_size ?? 0,
    duration: raw?.duration ?? undefined,
    width: raw?.width ?? undefined,
    height: raw?.height ?? undefined,
    thumbnail: raw?.thumbnail_path ?? undefined,
    poster: raw?.poster_path ?? undefined,
    has_contact_sheet: !!raw?.has_contact_sheet,
    rating: raw?.rating ?? 0,
    favorite: !!raw?.is_favorite,
    tags,
    metadata: { progress: raw?.playback_position, ...(raw ?? {}) },
    scrape_data: raw?.scrape_data ?? undefined,
    urls: Array.isArray(raw?.urls) ? raw.urls : [],
    segments: Array.isArray(raw?.segments) ? raw.segments : [],
    created_at: raw?.created_at ?? '',
    updated_at: raw?.updated_at ?? '',
    last_played_at: raw?.last_played_at ?? undefined
  };
}

/** Make the media's tag associations exactly match the requested tag IDs. */
async function syncMediaTags(
  mediaId: string,
  desiredTagIds: string[],
  currentTagIds: string[] = [],
): Promise<void> {
  const desired = new Set(desiredTagIds.map(Number).filter(Number.isInteger));
  const current = new Set(currentTagIds.map(Number).filter(Number.isInteger));

  for (const tagId of current) {
    if (desired.has(tagId)) continue;
    await client.delete(`/media/${mediaId}/tags/${tagId}`);
  }
  for (const tagId of desired) {
    if (current.has(tagId)) continue;
    try {
      await client.post(`/media/${mediaId}/tags`, { tag_id: tagId });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // Already attached — expected when another refresh raced this one.
      } else {
        throw e;
      }
    }
  }
}

export const mediaApi = {
  home: async (recommendationSeed?: number): Promise<MediaHomeResponse> => {
    const raw = await client.get<MediaHomeRawResponse>(
      '/media/home',
      recommendationSeed === undefined ? undefined : { recommendation_seed: recommendationSeed },
      undefined,
      true
    );
    const normalizeItem = (item: MediaHomeRawItem): MediaHomeItem =>
      item.kind === 'series'
        ? { kind: 'series', data: item.data }
        : { kind: 'media', data: normalizeMedia(item.data) };
    return {
      continue_watching: (raw?.continue_watching ?? []).map(normalizeItem),
      recently_added: (raw?.recently_added ?? []).map(normalizeItem),
      recently_played: (raw?.recently_played ?? []).map(normalizeItem),
      recommendations: (raw?.recommendations ?? []).map(normalizeItem)
    };
  },
  list: async (params: MediaListParams = {}, signal?: AbortSignal): Promise<MediaListResponse> => {
    // Map frontend-style param names to backend-style query param names.
    // Backend expects: tag_ids (comma-str), media_type, is_favorite, search,
    // sort_by, sort_order — not tags, type, favorite, q, sort, order.
    const apiParams: Params = {};
    if (params.library_id !== undefined) apiParams.library_id = params.library_id;
    if (params.dir !== undefined) apiParams.dir = params.dir;
    if (params.type !== undefined) apiParams.content_type = params.type;
    if (params.source !== undefined) apiParams.source = params.source;
    if (params.file_missing !== undefined) apiParams.file_missing = params.file_missing;
    if (params.q !== undefined) apiParams.search = params.q;
    if (params.tags && params.tags.length > 0) apiParams.tag_ids = params.tags.join(',');
    if (params.favorite !== undefined) apiParams.is_favorite = params.favorite;
    if (params.rating_min !== undefined) apiParams.rating_min = params.rating_min;
    if (params.rating_max !== undefined) apiParams.rating_max = params.rating_max;
    if (params.duration_min !== undefined) apiParams.duration_min = params.duration_min;
    if (params.duration_max !== undefined) apiParams.duration_max = params.duration_max;
    if (params.resolution_min !== undefined) apiParams.resolution_min = params.resolution_min;
    if (params.resolution_max !== undefined) apiParams.resolution_max = params.resolution_max;
    if (params.in_progress !== undefined) apiParams.in_progress = params.in_progress;
    if (params.genre !== undefined) apiParams.genre = params.genre;
    if (params.country !== undefined) apiParams.country = params.country;
    if (params.year !== undefined) apiParams.year = params.year;
    if (params.sort !== undefined) apiParams.sort_by = params.sort;
    if (params.order !== undefined) apiParams.sort_order = params.order;
    if (params.page !== undefined) apiParams.page = params.page;
    if (params.page_size !== undefined) apiParams.page_size = params.page_size;
    if (params.exclude_series !== undefined) apiParams.exclude_series = params.exclude_series;
    if (params.has_series !== undefined) apiParams.has_series = params.has_series;
    if (params.tag_match !== undefined) apiParams.tag_match = params.tag_match;
    // Issue predicates — names match the backend 1:1, so no renaming needed.
    if (params.has_poster !== undefined) apiParams.has_poster = params.has_poster;
    if (params.metadata_status !== undefined) apiParams.metadata_status = params.metadata_status;
    if (params.untagged !== undefined) apiParams.untagged = params.untagged;
    if (params.exclude_network !== undefined) apiParams.exclude_network = params.exclude_network;
    if (params.problem !== undefined) apiParams.problem = params.problem;
    if (params.ids_only !== undefined) apiParams.ids_only = params.ids_only;

    // 媒体列表默认 noCache：列表是"当前筛选/设置状态"的实时反映（受限开关、
    // 打标、移动库等操作后必须立即拿到最新），30s GET 缓存会导致操作后
    // 列表显示旧数据（用户感知为"刷新不即时"）。列表请求量小，本地后端可承受。
    const raw = await client.get<MediaListRawResponse>('/media', apiParams, signal, true);
    const items = Array.isArray(raw?.items) ? raw.items.map(normalizeMedia) : [];
    const pageSize = raw?.page_size ?? items.length;
    return {
      items,
      total: raw?.total ?? items.length,
      page: raw?.page ?? 1,
      page_size: pageSize,
      total_pages:
        raw?.total_pages ??
        (raw?.total !== undefined && pageSize > 0 ? Math.ceil(raw.total / pageSize) : undefined)
    };
  },

  /**
   * 取「与当前筛选条件匹配的全部 id」——跨页全选用。
   *
   * 为什么不复用 list() 逐页拉：一页 200 条约 800KB 完整对象，874 条要 3.4MB，
   * 上万条则是几十 MB。这个接口只返回 id 列，且不分页。
   */
  listIds: async (params: MediaListParams = {}): Promise<MediaIdListResponse> => {
    const apiParams: Params = { ids_only: true };
    if (params.library_id !== undefined) apiParams.library_id = params.library_id;
    if (params.dir !== undefined) apiParams.dir = params.dir;
    if (params.type !== undefined) apiParams.content_type = params.type;
    if (params.source !== undefined) apiParams.source = params.source;
    if (params.file_missing !== undefined) apiParams.file_missing = params.file_missing;
    if (params.q !== undefined) apiParams.search = params.q;
    if (params.tags && params.tags.length > 0) apiParams.tag_ids = params.tags.join(',');
    if (params.favorite !== undefined) apiParams.is_favorite = params.favorite;
    if (params.rating_min !== undefined) apiParams.rating_min = params.rating_min;
    if (params.rating_max !== undefined) apiParams.rating_max = params.rating_max;
    if (params.duration_min !== undefined) apiParams.duration_min = params.duration_min;
    if (params.duration_max !== undefined) apiParams.duration_max = params.duration_max;
    if (params.resolution_min !== undefined) apiParams.resolution_min = params.resolution_min;
    if (params.resolution_max !== undefined) apiParams.resolution_max = params.resolution_max;
    if (params.in_progress !== undefined) apiParams.in_progress = params.in_progress;
    if (params.genre !== undefined) apiParams.genre = params.genre;
    if (params.country !== undefined) apiParams.country = params.country;
    if (params.year !== undefined) apiParams.year = params.year;
    if (params.exclude_series !== undefined) apiParams.exclude_series = params.exclude_series;
    if (params.has_series !== undefined) apiParams.has_series = params.has_series;
    if (params.tag_match !== undefined) apiParams.tag_match = params.tag_match;
    if (params.has_poster !== undefined) apiParams.has_poster = params.has_poster;
    if (params.metadata_status !== undefined) apiParams.metadata_status = params.metadata_status;
    if (params.untagged !== undefined) apiParams.untagged = params.untagged;
    if (params.exclude_network !== undefined) apiParams.exclude_network = params.exclude_network;
    if (params.problem !== undefined) apiParams.problem = params.problem;

    const raw = await client.get<{ total?: number; ids?: number[] | null }>(
      '/media',
      apiParams,
      undefined,
      true
    );
    return { total: raw?.total ?? 0, ids: raw?.ids ?? [] };
  },

  get: async (id: string): Promise<Media> =>
    normalizeMedia(
      await client.get<Partial<MediaPayload>>(`/media/${id}`, undefined, undefined, true)
    ),

  /** Fetch available filter options (genres, countries, years) from scraped media. */
  getFilterOptions: async (): Promise<{ genres: string[]; countries: string[]; years: number[] }> =>
    client.get('/media/filters'),

  /** Counts and high-level filter values used by the media home page.
   *  Optional library_id scopes the result so分类 buttons & tag filter row
   *  refresh when switching libraries; omit for the global watch-center view. */
  getFacets: async (libraryId?: string): Promise<MediaFacets> =>
    client.get(
      '/media/facets',
      libraryId ? { library_id: libraryId } : undefined,
      undefined,
      true
    ),

  update: async (id: string, input: UpdateMediaInput): Promise<Media> => {
    // Build the backend payload — only the fields the backend accepts.
    const payload: Record<string, unknown> = {};
    if (input.rating !== undefined) payload.rating = input.rating;
    if (input.favorite !== undefined) payload.is_favorite = input.favorite;
    if (input.thumbnail !== undefined) payload.thumbnail_path = input.thumbnail;
    if (input.title !== undefined) payload.title = input.title;
    if (input.year !== undefined) payload.year = input.year;
    if (input.description !== undefined) payload.description = input.description;
    if (input.season_number !== undefined) payload.season_number = input.season_number;
    if (input.episode_number !== undefined) payload.episode_number = input.episode_number;
    // `tags` is intentionally dropped here — handled separately below.

    const current = input.tags !== undefined ? await mediaApi.get(id) : undefined;
    const updatedRaw = await client.put<Partial<MediaPayload>>(`/media/${id}`, payload);

    if (input.tags !== undefined) {
      await syncMediaTags(id, input.tags, current?.tags ?? []);
    }

    // Re-fetch normalized media so tags/other fields are current.
    try {
      return await mediaApi.get(id);
    } catch {
      return normalizeMedia(updatedRaw);
    }
  },

  delete: (id: string) => client.delete<void>(`/media/${id}`),

  // ---- Resource URL CRUD ----
  createUrl: async (mediaId: string, data: { url: string; url_role: UrlRole; title?: string; platform?: string }): Promise<MediaUrl> =>
    client.post<MediaUrl>(`/media/${mediaId}/urls`, data),

  updateUrl: async (mediaId: string, urlId: number, data: { url?: string; url_role?: UrlRole; title?: string; platform?: string }): Promise<MediaUrl> =>
    client.put<MediaUrl>(`/media/${mediaId}/urls/${urlId}`, data),

  deleteUrl: async (mediaId: string, urlId: number): Promise<void> =>
    client.delete<void>(`/media/${mediaId}/urls/${urlId}`),

  // ---- Segment CRUD ----
  /** 删除片段标记（后端 DELETE /segments/{segment_id}）。 */
  deleteSegment: (segmentId: number): Promise<void> =>
    client.delete<void>(`/segments/${segmentId}`),

  /** Trigger a TMDB scrape for a single media item; returns the updated media. */
  scrape: async (id: string): Promise<Media> =>
    normalizeMedia(await client.post<Partial<MediaPayload>>(`/media/${id}/scrape`, {})),

  /** AI 辅助二次刮削：AI 分析文件名后重试 TMDB 匹配。 */
  aiRescrape: async (id: string): Promise<AIRescrapeResponse> =>
    client.post<AIRescrapeResponse>(`/media/${id}/ai-rescrape`, {}),

  /** AI 打标：调用 AI 生成标签建议并写入（source="ai"，未验证状态）。 */
  aiTags: async (id: string): Promise<AITagSuggestion[]> =>
    client.post<AITagSuggestion[]>(`/media/${id}/ai-tags`, {}),

  /** 生成（或重新生成）4×4 缩略图集（16 帧 1920×1080，手动触发）。 */
  generateContactSheet: async (id: string): Promise<{ success: boolean; url: string }> =>
    client.post<{ success: boolean; url: string }>(`/media/${id}/contact-sheet`, {}),

  /** 播放结束推荐：同系列下一集 > 同标签 > 同库。 */
  related: async (id: string, limit = 8): Promise<RelatedMediaItem[]> => {
    const raw = await client.get<{ items: RelatedMediaItem[] }>(
      `/media/${id}/related`,
      { limit },
      undefined,
      true
    );
    return raw?.items ?? [];
  },

  /** 缺失文件找回：预览可合并的「缺失记录 → 存活同名记录」对。noCache — 执行合并后立即重查，不能吃 30s GET 缓存。 */
  reconcilePreview: async (libraryId?: number): Promise<ReconcilePreview> => {
    const params: Params = {};
    if (libraryId != null) params.library_id = libraryId;
    return client.get<ReconcilePreview>('/media/missing/reconcile-preview', params, undefined, true);
  },

  /** 缺失文件找回：执行合并（用户数据并入存活记录，旧记录进回收站）。 */
  reconcileExecute: async (
    pairs: { missing_id: number; live_id: number }[]
  ): Promise<{ merged: number[]; failed: { missing_id: number | null; error: string }[]; merged_count: number }> =>
    client.post('/media/missing/reconcile', { pairs }),

  /**
   * Contact sheet URL (4×4, 1920×1080). Pass a version (e.g. Date.now())
   * after regeneration to bust the browser cache.
   */
  contactSheetUrl: (id: string, version?: string) =>
    `${BASE_URL}/media/${id}/contact-sheet${version ? `?v=${encodeURIComponent(version)}` : ''}`,

  /** Rename the physical file on disk and optionally re-scrape. */
  rename: async (id: string, newName: string, reScrape = false): Promise<Media> =>
    normalizeMedia(await client.put<Partial<MediaPayload>>(`/media/${id}/rename`, {
      new_name: newName,
      re_scrape: reScrape,
    })),

  /** Convert a file-missing (OFFLINE) media into a pure network video (NETWORK).
   *  Requires at least one non-expired source URL — add one first via the
   *  aggregator resolve or manual link. Clears file_missing and file_path. */
  convertToNetwork: async (id: string): Promise<Media> =>
    normalizeMedia(
      await client.post<Partial<MediaPayload>>(`/media/${id}/convert-to-network`, {})
    ),

  streamUrl: (id: string) => `${BASE_URL}/media/${id}/stream`,
  /**
   * Thumbnail URL. Pass `media.updated_at` as the version to bust the
   * 7-day browser cache — the server sends `Cache-Control: max-age=604800`,
   * so a bare URL would keep showing the old thumbnail until the cache
   * expires even after the file was regenerated (rename/re-scrape/smart-frame).
   */
  thumbnailUrl: (id: string, version?: string) =>
    `${BASE_URL}/media/${id}/thumbnail${version ? `?v=${encodeURIComponent(version)}` : ''}`,
  /**
   * Poster URL. Pass `media.updated_at` as the version to bust the
   * 7-day browser cache after a custom cover upload/delete — the server
   * sends `Cache-Control: max-age=604800`, so a bare URL would keep
   * showing the old cover until the cache expires.
   */
  posterUrl: (id: string, version?: string) =>
    `${BASE_URL}/media/${id}/poster${version ? `?v=${encodeURIComponent(version)}` : ''}`,
  /**
   * Backdrop URL (TMDB movie/tv hero atmosphere). The backend lazily fetches
   * and caches the image; returns 404 for AV / media without a backdrop.
   */
  backdropUrl: (id: string, version?: string) =>
    `${BASE_URL}/media/${id}/backdrop${version ? `?v=${encodeURIComponent(version)}` : ''}`,

  /**
   * Ask the backend to pre-generate progress-bar hover previews around a
   * position, in the background. Called when the player opens and after each
   * seek, so hovering the progress bar near the current position shows frames
   * instantly instead of waiting for an ffmpeg extraction. Returns as soon as
   * the job is queued.
   */
  prefetchScreenshots: (id: string, center: number, window?: number) => {
    const q = new URLSearchParams({ center: String(Math.max(0, Math.round(center))) });
    if (window != null) q.set('window', String(window));
    return client.post<{ started: boolean; reason?: string; center?: number; window?: number }>(
      `/media/${id}/screenshots/prefetch?${q.toString()}`
    );
  }
};
