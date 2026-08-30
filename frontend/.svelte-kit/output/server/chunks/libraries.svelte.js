import { g as getContext } from "./index.js";
import "clsx";
import "@sveltejs/kit/internal";
import "./exports.js";
import "./utils2.js";
import "@sveltejs/kit/internal/server";
import "./root.js";
import "./state.svelte.js";
import { c as client } from "./client2.js";
import { t as tagsApi, m as mediaApi } from "./media.js";
const getStores = () => {
  const stores$1 = getContext("__svelte__");
  return {
    /** @type {typeof page} */
    page: {
      subscribe: stores$1.page.subscribe
    },
    /** @type {typeof navigating} */
    navigating: {
      subscribe: stores$1.navigating.subscribe
    },
    /** @type {typeof updated} */
    updated: stores$1.updated
  };
};
const page = {
  subscribe(fn) {
    const store = getStores().page;
    return store.subscribe(fn);
  }
};
function normalizeLibrary(raw) {
  return {
    id: String(raw?.id ?? ""),
    name: raw?.name ?? "",
    path: raw?.root_path ?? "",
    root_path: raw?.root_path ?? "",
    description: raw?.description ?? void 0,
    scrape_mode: raw?.scrape_mode ?? void 0,
    is_restricted: raw?.is_restricted ?? false,
    media_count: raw?.media_count ?? 0,
    created_at: raw?.created_at ?? "",
    updated_at: raw?.updated_at ?? ""
  };
}
const librariesApi = {
  // noCache=true 时绕过 client 层 30s GET 缓存——侧边栏 reload/受限开关切换
  // 等场景必须拿到最新数据（否则保存 show_restricted 后 30s 内仍显示旧库列表）。
  list: async (noCache = false) => (await client.get("/libraries", void 0, void 0, noCache)).map(normalizeLibrary),
  get: async (id) => normalizeLibrary(await client.get(`/libraries/${id}`)),
  create: async (input) => {
    const payload = {
      name: input.name,
      root_path: input.path
    };
    if (input.description !== void 0) payload.description = input.description;
    return normalizeLibrary(await client.post("/libraries", payload));
  },
  update: async (id, input) => {
    const payload = {};
    if (input.name !== void 0) payload.name = input.name;
    if (input.path !== void 0) payload.root_path = input.path;
    if (input.description !== void 0) payload.description = input.description;
    return normalizeLibrary(await client.put(`/libraries/${id}`, payload));
  },
  delete: (id, cleanEmptyTags = false) => client.delete(
    `/libraries/${id}`,
    cleanEmptyTags ? { clean_empty_tags: true } : void 0
  ),
  scan: (id) => client.post(`/libraries/${id}/scan`),
  rescan: (id) => client.post(`/libraries/${id}/rescan`),
  /** Get the file system directory tree for a library (lazy-loaded). */
  tree: async (id, path = "") => {
    const params = {};
    if (path) params.path = path;
    const res = await client.get(`/libraries/${id}/tree`, params);
    return (res?.nodes ?? []).map((n) => ({
      name: n.name ?? "",
      rel_path: n.rel_path ?? "",
      node_type: n.node_type ?? "file",
      size: n.size ?? void 0,
      modified_at: n.modified_at ?? void 0,
      media_id: n.media_id ?? void 0,
      is_scraped: !!n.is_scraped,
      has_poster: !!n.has_poster,
      child_count: n.child_count ?? void 0
    }));
  },
  /** Create a new directory within a library. */
  createDirectory: async (id, parentPath, dirName) => client.post(`/libraries/${id}/directories`, {
    parent_path: parentPath,
    dir_name: dirName
  }),
  /** Rename a directory on disk (updates all affected media paths). */
  renameDirectory: async (id, oldRelPath, newName) => client.put(`/libraries/${id}/directories/rename`, {
    old_rel_path: oldRelPath,
    new_name: newName
  }),
  /** Delete a directory on disk. */
  deleteDirectory: async (id, relPath, recursive = false) => {
    const params = { rel_path: relPath };
    if (recursive) params.recursive = true;
    return client.delete(`/libraries/${id}/directories`, params);
  },
  /** Move files to a target directory within a library. */
  moveFiles: async (sourceLibraryId, mediaIds, targetLibraryId, targetDir = "") => client.put(
    `/libraries/${sourceLibraryId}/files/move`,
    { target_library_id: parseInt(targetLibraryId), target_dir: targetDir },
    { media_ids: mediaIds.join(",") }
  )
};
class LibrariesStore {
  libraries = [];
  tags = [];
  tagTypes = [];
  smartFolders = [];
  totalCount = 0;
  favoriteCount = 0;
  loading = false;
  loaded = false;
  /**
   * 数据版本号：reload() 成功后自增。
   * 媒体页/管理页在 $effect 中追踪该值——侧边栏内任何修改媒体数据的操作
   * (打标/取消打标/移动库/删除标签等, 均通过 tagOps → reload) 后,
   * 可见页面列表能立即刷新, 无需等用户切页/切筛选。
   */
  revision = 0;
  /** Load all sidebar data from the backend. Safe to call multiple times. */
  async reload() {
    this.loading = true;
    const [libs, tgs, types, folders, all, favs] = await Promise.allSettled([
      librariesApi.list(true),
      tagsApi.list({ noCache: true }),
      client.get("/tag-types"),
      client.get("/smart-folders"),
      mediaApi.list({ page: 1, page_size: 1 }),
      mediaApi.list({ favorite: true, page: 1, page_size: 1 })
    ]);
    if (libs.status === "fulfilled") this.libraries = libs.value ?? [];
    if (tgs.status === "fulfilled") this.tags = tgs.value ?? [];
    if (types.status === "fulfilled") this.tagTypes = types.value ?? [];
    if (folders.status === "fulfilled") this.smartFolders = folders.value ?? [];
    if (all.status === "fulfilled") this.totalCount = all.value.total ?? 0;
    if (favs.status === "fulfilled") this.favoriteCount = favs.value.total ?? 0;
    this.loading = false;
    this.loaded = true;
    this.revision++;
  }
  /**
   * 数据变更通知（轻量，不请求后端）：仅递增 revision。
   * 媒体页/管理页 $effect 追踪 revision，变化即重新加载列表——
   * 用于删除/回收/恢复等本地操作后立即刷新可见列表，
   * 避免"操作生效但界面未及时刷新"。
   */
  notifyChanged() {
    this.revision++;
  }
  /** Ensure data is loaded at least once (idempotent). */
  async ensureLoaded() {
    if (!this.loaded) {
      await this.reload();
    }
  }
}
const librariesStore = new LibrariesStore();
export {
  librariesStore as l,
  page as p
};
