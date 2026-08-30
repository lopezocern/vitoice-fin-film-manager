import { c as client, A as ApiError, B as BASE_URL } from "./client2.js";
function normalizeTag(raw) {
  return {
    id: String(raw?.id ?? ""),
    name: raw?.name ?? "",
    color: raw?.color ?? void 0,
    count: raw?.media_count ?? void 0,
    tag_type_id: raw?.tag_type_id ?? void 0,
    parent_id: raw?.parent_id != null ? String(raw.parent_id) : null,
    description: raw?.description ?? void 0,
    sort_order: raw?.sort_order ?? void 0,
    created_at: raw?.created_at ?? "",
    updated_at: raw?.updated_at ?? void 0,
    children: (raw?.children ?? []).map(normalizeTag)
  };
}
function flattenTags(tree) {
  const out = [];
  const walk = (nodes) => {
    for (const n of nodes) {
      out.push(n);
      if (n.children && n.children.length > 0) walk(n.children);
    }
  };
  walk(tree);
  return out;
}
const tagsApi = {
  // noCache=true 绕过 client 层 30s GET 缓存（受限开关切换后侧边栏需立即刷新）
  list: async (params) => {
    const query = {};
    if (params?.tag_type_id !== void 0) query.tag_type_id = String(params.tag_type_id);
    if (params?.library_id) query.library_id = params.library_id;
    if (params?.exclude_av) query.exclude_av = "true";
    if (params?.av_only) query.av_only = "true";
    return (await client.get("/tags", query, void 0, params?.noCache)).map(normalizeTag);
  },
  get: async (id) => normalizeTag(await client.get(`/tags/${id}`)),
  create: async (input) => {
    const payload = { name: input.name };
    if (input.color !== void 0) payload.color = input.color;
    if (input.tag_type_id !== void 0) payload.tag_type_id = input.tag_type_id;
    if (input.parent_id !== void 0) payload.parent_id = input.parent_id;
    return normalizeTag(await client.post("/tags", payload));
  },
  update: async (id, input) => normalizeTag(await client.put(`/tags/${id}`, input)),
  delete: (id) => client.delete(`/tags/${id}`),
  suggest: async (mediaId) => {
    try {
      const res = await client.get(`/tags/suggest`, { media_id: mediaId });
      return Array.isArray(res) ? res : [];
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return [];
      console.error("Tag suggest failed", e);
      return [];
    }
  }
};
function isAvMedia(media) {
  return !!media.scrape_data?.fancode;
}
function hasNetworkSource(media) {
  return !!media.urls?.some((u) => u.url_role === "source" && !u.is_expired);
}
function normalizeMedia(raw) {
  const mime = raw?.mime_type ?? "";
  let type = "image";
  if (mime.startsWith("video")) type = "video";
  else if (mime.startsWith("audio")) type = "audio";
  else {
    const ext = (raw?.file_name ?? "").toLowerCase();
    if (/\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|ts|rmvb)$/.test(ext)) type = "video";
    else if (/\.(mp3|flac|wav|aac|ogg|wma|m4a|ape)$/.test(ext)) type = "audio";
  }
  const tags = Array.isArray(raw?.tags) ? raw.tags.map((t) => t && t.id !== void 0 ? String(t.id) : "") : [];
  return {
    id: String(raw?.id ?? ""),
    library_id: String(raw?.library_id ?? ""),
    path: raw?.file_path ?? "",
    filename: raw?.file_name ?? "",
    title: raw?.title ?? void 0,
    year: raw?.year ?? void 0,
    release_date: raw?.release_date ?? void 0,
    season_number: raw?.season_number ?? void 0,
    episode_number: raw?.episode_number ?? void 0,
    series_id: raw?.series_id ?? void 0,
    series_title: raw?.series_title ?? void 0,
    description: raw?.description ?? void 0,
    type,
    source_type: raw?.media_type ?? "local",
    file_missing: !!raw?.file_missing,
    size: raw?.file_size ?? 0,
    duration: raw?.duration ?? void 0,
    width: raw?.width ?? void 0,
    height: raw?.height ?? void 0,
    thumbnail: raw?.thumbnail_path ?? void 0,
    poster: raw?.poster_path ?? void 0,
    rating: raw?.rating ?? 0,
    favorite: !!raw?.is_favorite,
    tags,
    metadata: { progress: raw?.playback_position, ...raw ?? {} },
    scrape_data: raw?.scrape_data ?? void 0,
    urls: Array.isArray(raw?.urls) ? raw.urls : [],
    segments: Array.isArray(raw?.segments) ? raw.segments : [],
    created_at: raw?.created_at ?? "",
    updated_at: raw?.updated_at ?? "",
    last_played_at: raw?.last_played_at ?? void 0
  };
}
async function syncMediaTags(mediaId, names) {
  if (!names || names.length === 0) return;
  const existing = flattenTags(await tagsApi.list());
  const byName = new Map(existing.map((t) => [t.name.toLowerCase(), t]));
  const desiredIds = [];
  for (const name of names) {
    const key = name.toLowerCase();
    let tag = byName.get(key);
    if (!tag) {
      tag = await tagsApi.create({ name });
      byName.set(key, tag);
    }
    const id = Number(tag.id);
    if (!desiredIds.includes(id)) desiredIds.push(id);
  }
  for (const tagId of desiredIds) {
    try {
      await client.post(`/media/${mediaId}/tags`, { tag_id: tagId });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) ;
      else {
        console.error("Failed to attach tag", tagId, "to media", mediaId, e);
      }
    }
  }
}
const mediaApi = {
  home: async (recommendationSeed) => {
    const raw = await client.get(
      "/media/home",
      recommendationSeed === void 0 ? void 0 : { recommendation_seed: recommendationSeed },
      void 0,
      true
    );
    const normalizeItem = (item) => item.kind === "series" ? { kind: "series", data: item.data } : { kind: "media", data: normalizeMedia(item.data) };
    return {
      continue_watching: (raw?.continue_watching ?? []).map(normalizeItem),
      recently_added: (raw?.recently_added ?? []).map(normalizeItem),
      recently_played: (raw?.recently_played ?? []).map(normalizeItem),
      recommendations: (raw?.recommendations ?? []).map(normalizeItem)
    };
  },
  list: async (params = {}, signal) => {
    const apiParams = {};
    if (params.library_id !== void 0) apiParams.library_id = params.library_id;
    if (params.dir !== void 0) apiParams.dir = params.dir;
    if (params.type !== void 0) apiParams.content_type = params.type;
    if (params.source !== void 0) apiParams.source = params.source;
    if (params.file_missing !== void 0) apiParams.file_missing = params.file_missing;
    if (params.q !== void 0) apiParams.search = params.q;
    if (params.tags && params.tags.length > 0) apiParams.tag_ids = params.tags.join(",");
    if (params.favorite !== void 0) apiParams.is_favorite = params.favorite;
    if (params.rating_min !== void 0) apiParams.rating_min = params.rating_min;
    if (params.rating_max !== void 0) apiParams.rating_max = params.rating_max;
    if (params.duration_min !== void 0) apiParams.duration_min = params.duration_min;
    if (params.duration_max !== void 0) apiParams.duration_max = params.duration_max;
    if (params.resolution_min !== void 0) apiParams.resolution_min = params.resolution_min;
    if (params.resolution_max !== void 0) apiParams.resolution_max = params.resolution_max;
    if (params.in_progress !== void 0) apiParams.in_progress = params.in_progress;
    if (params.genre !== void 0) apiParams.genre = params.genre;
    if (params.country !== void 0) apiParams.country = params.country;
    if (params.year !== void 0) apiParams.year = params.year;
    if (params.sort !== void 0) apiParams.sort_by = params.sort;
    if (params.order !== void 0) apiParams.sort_order = params.order;
    if (params.page !== void 0) apiParams.page = params.page;
    if (params.page_size !== void 0) apiParams.page_size = params.page_size;
    if (params.exclude_series !== void 0) apiParams.exclude_series = params.exclude_series;
    if (params.has_series !== void 0) apiParams.has_series = params.has_series;
    if (params.tag_match !== void 0) apiParams.tag_match = params.tag_match;
    const raw = await client.get("/media", apiParams, signal, true);
    const items = Array.isArray(raw?.items) ? raw.items.map(normalizeMedia) : [];
    return {
      items,
      total: raw?.total ?? items.length,
      page: raw?.page ?? 1,
      page_size: raw?.page_size ?? items.length
    };
  },
  get: async (id) => normalizeMedia(await client.get(`/media/${id}`, void 0, void 0, true)),
  /** Fetch available filter options (genres, countries, years) from scraped media. */
  getFilterOptions: async () => client.get("/media/filters"),
  /** Counts and high-level filter values used by the media home page. */
  getFacets: async () => client.get("/media/facets", void 0, void 0, true),
  update: async (id, input) => {
    const payload = {};
    if (input.rating !== void 0) payload.rating = input.rating;
    if (input.favorite !== void 0) payload.is_favorite = input.favorite;
    if (input.thumbnail !== void 0) payload.thumbnail_path = input.thumbnail;
    if (input.title !== void 0) payload.title = input.title;
    if (input.year !== void 0) payload.year = input.year;
    if (input.description !== void 0) payload.description = input.description;
    if (input.season_number !== void 0) payload.season_number = input.season_number;
    if (input.episode_number !== void 0) payload.episode_number = input.episode_number;
    const updatedRaw = await client.put(`/media/${id}`, payload);
    if (input.tags && input.tags.length > 0) {
      try {
        await syncMediaTags(id, input.tags);
      } catch (e) {
        console.error("Tag sync failed for media", id, e);
      }
    }
    try {
      return await mediaApi.get(id);
    } catch {
      return normalizeMedia(updatedRaw);
    }
  },
  delete: (id) => client.delete(`/media/${id}`),
  // ---- Resource URL CRUD ----
  createUrl: async (mediaId, data) => client.post(`/media/${mediaId}/urls`, data),
  updateUrl: async (mediaId, urlId, data) => client.put(`/media/${mediaId}/urls/${urlId}`, data),
  deleteUrl: async (mediaId, urlId) => client.delete(`/media/${mediaId}/urls/${urlId}`),
  /** Trigger a TMDB scrape for a single media item; returns the updated media. */
  scrape: async (id) => normalizeMedia(await client.post(`/media/${id}/scrape`, {})),
  /** AI 辅助二次刮削：AI 分析文件名后重试 TMDB 匹配。 */
  aiRescrape: async (id) => client.post(`/media/${id}/ai-rescrape`, {}),
  /** Rename the physical file on disk and optionally re-scrape. */
  rename: async (id, newName, reScrape = false) => normalizeMedia(await client.put(`/media/${id}/rename`, {
    new_name: newName,
    re_scrape: reScrape
  })),
  streamUrl: (id) => `${BASE_URL}/media/${id}/stream`,
  /**
   * Thumbnail URL. Pass `media.updated_at` as the version to bust the
   * 7-day browser cache — the server sends `Cache-Control: max-age=604800`,
   * so a bare URL would keep showing the old thumbnail until the cache
   * expires even after the file was regenerated (rename/re-scrape/smart-frame).
   */
  thumbnailUrl: (id, version) => `${BASE_URL}/media/${id}/thumbnail${version ? `?v=${encodeURIComponent(version)}` : ""}`,
  /**
   * Poster URL. Pass `media.updated_at` as the version to bust the
   * 7-day browser cache after a custom cover upload/delete — the server
   * sends `Cache-Control: max-age=604800`, so a bare URL would keep
   * showing the old cover until the cache expires.
   */
  posterUrl: (id, version) => `${BASE_URL}/media/${id}/poster${version ? `?v=${encodeURIComponent(version)}` : ""}`,
  /**
   * Backdrop URL (TMDB movie/tv hero atmosphere). The backend lazily fetches
   * and caches the image; returns 404 for AV / media without a backdrop.
   */
  backdropUrl: (id, version) => `${BASE_URL}/media/${id}/backdrop${version ? `?v=${encodeURIComponent(version)}` : ""}`
};
export {
  flattenTags as f,
  hasNetworkSource as h,
  isAvMedia as i,
  mediaApi as m,
  tagsApi as t
};
