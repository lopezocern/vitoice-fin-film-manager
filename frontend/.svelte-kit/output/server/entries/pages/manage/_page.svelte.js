import { a as attr_class, h as attr_style, c as attr, f as ensure_array_like, j as bind_props, d as derived, i as stringify, e as escape_html, s as store_get, u as unsubscribe_stores, k as head } from "../../../chunks/index.js";
import { p as page, l as librariesStore } from "../../../chunks/libraries.svelte.js";
import "clsx";
import { c as client } from "../../../chunks/client2.js";
import "@sveltejs/kit/internal";
import "../../../chunks/exports.js";
import "../../../chunks/utils2.js";
import "@sveltejs/kit/internal/server";
import "../../../chunks/root.js";
import "../../../chunks/state.svelte.js";
import { b as formatSize, f as formatTime, c as formatResolution, d as formatDate } from "../../../chunks/format.js";
import { t as tick } from "../../../chunks/index-server.js";
import { m as mediaApi, h as hasNetworkSource, f as flattenTags } from "../../../chunks/media.js";
import { T as TagSelector, C as ConfirmDialog, E as EditMediaDialog } from "../../../chunks/EditMediaDialog.js";
import { s as settingsStore } from "../../../chunks/settings.svelte.js";
import { t as tagOps, a as tagManageStore } from "../../../chunks/tagOps.svelte.js";
function RatingStars($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let {
      value = 0,
      size = 16,
      readonly = false,
      allowClear = true,
      onrate
    } = $$props;
    const display = derived(() => value);
    function starLabel(i) {
      return `${i} 星`;
    }
    $$renderer2.push(`<div${attr_class("rating-stars svelte-od9xzs", void 0, { "readonly": readonly })}${attr_style(`--star-size:${stringify(size)}px`)}${attr("role", readonly ? "img" : "slider")}${attr("aria-valuenow", value)}${attr("aria-valuemin", 0)}${attr("aria-valuemax", 5)}><!--[-->`);
    const each_array = ensure_array_like(Array(5));
    for (let i = 0, $$length = each_array.length; i < $$length; i++) {
      each_array[i];
      const idx = i + 1;
      $$renderer2.push(`<button type="button"${attr_class("star svelte-od9xzs", void 0, { "filled": idx <= display(), "dim": idx > display() })}${attr("disabled", readonly, true)}${attr("aria-label", starLabel(idx))}><svg viewBox="0 0 24 24"${attr("width", size)}${attr("height", size)} aria-hidden="true" class="svelte-od9xzs"><path d="M12 2.5l2.95 5.98 6.6.96-4.77 4.65 1.13 6.57L12 17.55l-5.91 3.11 1.13-6.57L2.45 9.44l6.6-.96L12 2.5z"></path></svg></button>`);
    }
    $$renderer2.push(`<!--]--></div>`);
    bind_props($$props, { value });
  });
}
function OverviewView($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    $$renderer2.push(`<div class="overview-view svelte-zplaka">`);
    {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="loading-state svelte-zplaka">加载中...</div>`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
function DirectoryTree($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    let { libraries } = $$props;
    const selectedLib = derived(() => store_get($$store_subs ??= {}, "$page", page).url.searchParams.get("lib") || "");
    const selectedDir = derived(() => {
      const dir = store_get($$store_subs ??= {}, "$page", page).url.searchParams.get("dir");
      return dir || "";
    });
    let expandedPaths = /* @__PURE__ */ new Set();
    let loadedChildren = /* @__PURE__ */ new Map();
    let loadingPaths = /* @__PURE__ */ new Set();
    function pathKey(libId, relPath) {
      return `${libId}::${relPath}`;
    }
    function isExpanded(libId, relPath) {
      return expandedPaths.has(pathKey(libId, relPath));
    }
    function isLoading(libId, relPath) {
      return loadingPaths.has(pathKey(libId, relPath));
    }
    let expandAll = false;
    const flatTree = derived(() => {
      const result = [];
      const walk = (libId, relPath, depth) => {
        const key = pathKey(libId, relPath);
        const children = loadedChildren.get(key);
        if (!children) return;
        for (const child of children) {
          const childExpanded = isExpanded(libId, child.rel_path);
          const childLoading = isLoading(libId, child.rel_path);
          if (child.node_type === "directory") {
            result.push({
              kind: "directory",
              libId,
              node: child,
              depth,
              expanded: childExpanded,
              loading: childLoading
            });
            if (childExpanded) {
              walk(libId, child.rel_path, depth + 1);
            }
          } else {
            result.push({
              kind: "file",
              libId,
              node: child,
              depth,
              expanded: false,
              loading: false
            });
          }
        }
      };
      for (const lib of libraries) {
        const libExpanded = isExpanded(lib.id, "") || expandAll;
        result.push({
          kind: "library",
          libId: lib.id,
          lib,
          depth: 0,
          expanded: libExpanded,
          loading: isLoading(lib.id, "")
        });
        if (libExpanded) {
          walk(lib.id, "", 1);
        }
      }
      return result;
    });
    {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="fs-tree svelte-17pgt0m"><!--[-->`);
      const each_array_1 = ensure_array_like(flatTree());
      for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
        let item = each_array_1[$$index_1];
        if (item.kind === "library") {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<div class="fs-lib-row svelte-17pgt0m"><button class="fs-arrow-btn svelte-17pgt0m"${attr("aria-label", item.expanded ? "收起" : "展开")}><span class="fs-arrow svelte-17pgt0m">${escape_html(item.expanded ? "▾" : "▸")}</span></button> <button${attr_class("fs-lib svelte-17pgt0m", void 0, { "active": selectedLib() === item.libId && !selectedDir() })}><svg class="fs-icon svelte-17pgt0m" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path></svg> <span class="fs-label svelte-17pgt0m"${attr("title", item.lib?.name)}>${escape_html(item.lib?.name)}</span> `);
          if (item.lib?.media_count != null) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span class="fs-count svelte-17pgt0m">${escape_html(item.lib.media_count)}</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></button></div>`);
        } else if (item.kind === "directory") {
          $$renderer2.push("<!--[1-->");
          $$renderer2.push(`<div class="fs-dir-row svelte-17pgt0m"${attr_style(`padding-left: ${4 + item.depth * 14}px`)}><button class="fs-arrow-btn svelte-17pgt0m"${attr("aria-label", item.expanded ? "收起" : "展开")}><span class="fs-arrow svelte-17pgt0m">${escape_html(item.expanded ? "▾" : "▸")}</span></button> <button${attr_class("fs-dir svelte-17pgt0m", void 0, {
            "active": selectedLib() === item.libId && selectedDir() === (item.node?.rel_path ?? "")
          })}><svg class="fs-icon svelte-17pgt0m" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path></svg> <span class="fs-label svelte-17pgt0m"${attr("title", item.node?.name)}>${escape_html(item.node?.name)}</span> `);
          if (item.node?.child_count != null) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span class="fs-count svelte-17pgt0m">${escape_html(item.node.child_count)}</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></button></div>`);
        } else {
          $$renderer2.push("<!--[-1-->");
          $$renderer2.push(`<div${attr_class("fs-file svelte-17pgt0m", void 0, {
            "scraped": item.node?.is_scraped,
            "unscraped": item.node?.media_id && !item.node?.is_scraped,
            "not-imported": !item.node?.media_id
          })}${attr_style(`padding-left: ${8 + item.depth * 14}px`)} role="button" tabindex="0"${attr("title", item.node?.name)}><span class="fs-file-icon svelte-17pgt0m">`);
          if (item.node?.is_scraped) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 2h7l3 3v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"></path><path d="M6 8l1.5 1.5L10 7" stroke-linecap="round" stroke-linejoin="round"></path></svg>`);
          } else if (item.node?.media_id) {
            $$renderer2.push("<!--[1-->");
            $$renderer2.push(`<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 2h7l3 3v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"></path></svg>`);
          } else {
            $$renderer2.push("<!--[-1-->");
            $$renderer2.push(`<svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.4"><path d="M3 2h7l3 3v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"></path></svg>`);
          }
          $$renderer2.push(`<!--]--></span> <span class="fs-label svelte-17pgt0m">${escape_html(item.node?.name)}</span> `);
          if (item.node?.size) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span class="fs-size svelte-17pgt0m">${escape_html(formatSize(item.node.size))}</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--> `);
          if (item.node?.media_id && !item.node?.is_scraped) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span class="fs-badge svelte-17pgt0m" title="未刮削">!</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></div>`);
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]--> `);
      if (flatTree().length === 0) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="fs-empty svelte-17pgt0m">暂无媒体库</div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div>`);
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
const defaultState = {
  filterLib: "",
  filterDir: "",
  filterType: "",
  filterTags: [],
  filterTagType: "",
  filterStatus: "",
  filterSource: "",
  sortField: "created_at",
  sortOrder: "desc",
  view: "list",
  page: 1,
  pageSize: 50,
  scrollTop: 0,
  hasState: false
};
const state = { ...defaultState };
const manageFilterStore = {
  get state() {
    return state;
  }
};
function NetworkImportDialog($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { open = false, onsuccess } = $$props;
    let libraries = [];
    let url = "";
    let title = "";
    let libraryId = "";
    let platform = "";
    let submitting = false;
    const showAdultResolve = derived(() => settingsStore.showRestricted && settingsStore.allowAdultNetwork);
    let adultFancode = "";
    let adultResolving = false;
    let adultResults = [];
    const canSubmit = derived(() => url.trim().length > 0 && title.trim().length > 0 && libraryId);
    if (open) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="modal-overlay svelte-g67bjd"><div class="modal-card svelte-g67bjd"><div class="modal-header svelte-g67bjd"><h2 class="svelte-g67bjd">网络媒体导入</h2> <button class="close-btn svelte-g67bjd">✕</button></div> <div class="modal-body svelte-g67bjd">`);
      {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (showAdultResolve()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="adult-section svelte-g67bjd"><div class="adult-head svelte-g67bjd">聚合站解析 <span class="adult-badge svelte-g67bjd">成人内容</span></div> <div class="adult-row svelte-g67bjd"><input type="text"${attr("value", adultFancode)} placeholder="输入番号，如 SNOS-334"${attr("disabled", adultResolving, true)} class="svelte-g67bjd"/> <button class="btn-secondary svelte-g67bjd"${attr("disabled", !adultFancode.trim(), true)}>${escape_html("解析")}</button></div> `);
        {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (adultResults.length > 0) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<div class="adult-results svelte-g67bjd"><!--[-->`);
          const each_array = ensure_array_like(adultResults);
          for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
            let r = each_array[$$index];
            $$renderer2.push(`<button class="adult-result svelte-g67bjd"${attr("disabled", !r.m3u8_url, true)}${attr("title", r.m3u8_url ? "填入下方表单" : r.error)}><span class="adult-srv svelte-g67bjd">${escape_html(r.server)}</span> <span class="adult-url svelte-g67bjd">${escape_html(r.m3u8_url ?? (r.error || "解析失败"))}</span> `);
            if (r.expires_in) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="adult-exp svelte-g67bjd">有效 ${escape_html(Math.round(r.expires_in / 3600))}h</span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></button>`);
          }
          $$renderer2.push(`<!--]--></div> <div class="form-hint svelte-g67bjd">点击某条结果将自动填入下方 URL 表单，再选择目标库导入</div>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div> <hr class="adult-divider svelte-g67bjd"/>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> <div class="form-group svelte-g67bjd"><label for="net-url" class="svelte-g67bjd">网络 URL *</label> <input id="net-url" type="url"${attr("value", url)} placeholder="https://example.com/video.mp4 或 .m3u8"${attr("disabled", submitting, true)} class="svelte-g67bjd"/> <div class="form-hint svelte-g67bjd">支持直链视频 (mp4/webm)、HLS 流 (m3u8) 或平台链接</div></div> <div class="form-group svelte-g67bjd"><label for="net-title" class="svelte-g67bjd">标题 *</label> <input id="net-title" type="text"${attr("value", title)} placeholder="媒体标题"${attr("disabled", submitting, true)} class="svelte-g67bjd"/></div> <div class="form-group svelte-g67bjd"><label for="net-library" class="svelte-g67bjd">目标库 *</label> `);
      $$renderer2.select(
        {
          id: "net-library",
          value: libraryId,
          disabled: submitting,
          class: ""
        },
        ($$renderer3) => {
          $$renderer3.option({ value: "" }, ($$renderer4) => {
            $$renderer4.push(`选择库…`);
          });
          $$renderer3.push(`<!--[-->`);
          const each_array_1 = ensure_array_like(libraries);
          for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
            let lib = each_array_1[$$index_1];
            $$renderer3.option({ value: lib.id }, ($$renderer4) => {
              $$renderer4.push(`${escape_html(lib.name)}`);
            });
          }
          $$renderer3.push(`<!--]-->`);
        },
        "svelte-g67bjd"
      );
      $$renderer2.push(`</div> <div class="form-group svelte-g67bjd"><label for="net-platform" class="svelte-g67bjd">平台 (可选)</label> <input id="net-platform" type="text"${attr("value", platform)} placeholder="自动检测或手动输入"${attr("disabled", submitting, true)} class="svelte-g67bjd"/></div></div> <div class="modal-footer svelte-g67bjd"><button class="btn-secondary svelte-g67bjd"${attr("disabled", submitting, true)}>取消</button> <button class="btn-primary svelte-g67bjd"${attr("disabled", !canSubmit(), true)}>${escape_html("导入")}</button></div></div></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
    bind_props($$props, { open });
  });
}
function MediaManageView($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { libraries = [], tags = [], tagTypes = [] } = $$props;
    let filterType = "";
    let filterTags = [];
    let filterStatus = "";
    let sortField = "created_at";
    let sortOrder = "desc";
    let view = "list";
    let didRestoreScroll = false;
    let page2 = 1;
    let pageSize = 50;
    let items = [];
    let total = 0;
    let loading = false;
    let error = null;
    let selected = /* @__PURE__ */ new Set();
    let tagSelectorOpen = false;
    let deleteDialogOpen = false;
    let networkImportOpen = false;
    let editDialogOpen = false;
    let editMediaTarget = null;
    let toast = null;
    let toastTimer = null;
    function showToast(msg, type = "ok") {
      toast = { msg, type };
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast = null, 3e3);
    }
    const libraryMap = derived(() => Object.fromEntries(libraries.map((l) => [l.id, l.name])));
    const flatTags = derived(() => flattenTags(tags));
    const tagMap = derived(() => Object.fromEntries(flatTags().map((t) => [t.id, t.name])));
    const selectedCount = derived(() => selected.size);
    const allOnPageSelected = derived(() => items.length > 0 && items.every((m) => selected.has(m.id)));
    const someOnPageSelected = derived(() => items.some((m) => selected.has(m.id)) && !allOnPageSelected());
    const totalPages = derived(() => Math.max(1, Math.ceil(total / pageSize)));
    const selectedItems = derived(() => items.filter((m) => selected.has(m.id)));
    let filterTagType = "";
    const statusOptions = [
      { value: "", label: "全部状态" },
      { value: "problem", label: "存在问题" },
      { value: "missing", label: "文件缺失" },
      { value: "unmatched", label: "待处理" },
      { value: "rated", label: "已评分" },
      { value: "unrated", label: "未评分" },
      { value: "favorite", label: "收藏" },
      { value: "untagged", label: "无标签" }
    ];
    const sortOptions = [
      { value: "created_at", label: "添加时间" },
      { value: "filename", label: "标题" },
      { value: "size", label: "大小" },
      { value: "duration", label: "时长" },
      { value: "rating", label: "评分" }
    ];
    const typeOptions = [
      { value: "", label: "全部类型" },
      { value: "video", label: "视频" },
      { value: "audio", label: "音频" },
      { value: "image", label: "图片" }
    ];
    function buildParams() {
      const p = { sort: sortField, order: sortOrder, page: page2, page_size: pageSize };
      if (filterTags.length) p.tags = filterTags;
      return p;
    }
    function applyClientFilters(list) {
      return list;
    }
    async function restoreScrollPosition() {
      if (didRestoreScroll) return;
      didRestoreScroll = true;
      const top = manageFilterStore.state.scrollTop;
      if (top <= 0) return;
      await tick();
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const el = document.querySelector(".manage-content");
          if (el) el.scrollTop = top;
        });
      });
    }
    let reqId = 0;
    async function loadMedia() {
      const myId = ++reqId;
      loading = true;
      error = null;
      try {
        const params = buildParams();
        if (filterStatus === "untagged" || filterStatus === "problem" || filterStatus === "unmatched") ;
        const res = await mediaApi.list(params);
        if (myId !== reqId) return;
        items = applyClientFilters(res.items ?? []);
        total = filterStatus === "untagged" || filterStatus === "problem" || filterStatus === "unmatched" ? items.length : res.total ?? 0;
        void restoreScrollPosition();
      } catch (e) {
        if (myId !== reqId) return;
        error = "加载媒体失败，请检查后端服务是否运行";
        items = [];
        total = 0;
      } finally {
        if (myId === reqId) loading = false;
      }
    }
    librariesStore.revision;
    function clearSelection() {
      selected = /* @__PURE__ */ new Set();
    }
    function selectedNumericIds() {
      return selectedItems().map((m) => Number(m.id)).filter((n) => !isNaN(n));
    }
    async function batchAddTags(tagIds) {
      if (tagIds.length === 0) return;
      tagSelectorOpen = false;
      const mediaIds = selectedNumericIds();
      if (mediaIds.length === 0) return;
      const numericTagIds = tagIds.map((id) => Number(id)).filter((n) => !isNaN(n));
      try {
        const resp = await client.post("/media/batch", {
          action: "tag",
          media_ids: mediaIds,
          params: { tag_ids: numericTagIds }
        });
        const fail = resp.failed.length;
        showToast(`已为 ${resp.success_count} 项媒体添加标签${fail ? `，${fail} 项失败` : ""}`, fail ? "err" : "ok");
      } catch {
        showToast("批量打标失败", "err");
      }
      clearSelection();
      loadMedia();
    }
    let batchScraping = false;
    async function batchDelete() {
      deleteDialogOpen = false;
      const mediaIds = selectedNumericIds();
      if (mediaIds.length === 0) return;
      try {
        const resp = await client.post("/media/batch", {
          action: "delete",
          media_ids: mediaIds,
          params: { permanent: false }
        });
        const fail = resp.failed.length;
        librariesStore.notifyChanged();
        showToast(`已移入回收站 ${resp.success_count} 项（磁盘文件未删除）${fail ? `，${fail} 项失败` : ""}`, fail ? "err" : "ok");
      } catch {
        showToast("批量删除失败", "err");
      }
      clearSelection();
      loadMedia();
    }
    function onPageSizeChange(e) {
      pageSize = Number(e.target.value);
      page2 = 1;
    }
    function pageList(current, tp, maxVisible) {
      if (tp <= maxVisible) return Array.from({ length: tp }, (_, i) => i + 1);
      const pages = [1];
      const half = Math.max(1, Math.floor((maxVisible - 3) / 2));
      let left = Math.max(2, current - half);
      let right = Math.min(tp - 1, current + half);
      if (right - left + 1 < maxVisible - 2) {
        const slack = maxVisible - 2 - (right - left + 1);
        if (left === 2) right = Math.min(tp - 1, right + slack);
        else if (right === tp - 1) left = Math.max(2, left - slack);
      }
      if (left > 2) pages.push("…");
      for (let i = left; i <= right; i++) pages.push(i);
      if (right < tp - 1) pages.push("…");
      pages.push(tp);
      return pages;
    }
    const maxVisiblePages = derived(
      () => 15
    );
    const libLabel = derived(() => "库");
    const typeLabel = derived(() => typeOptions.find((o) => o.value === filterType)?.label ?? "类型");
    const tagLabel = derived(() => {
      const names = filterTags.map((id) => tagMap()[id]).filter((n) => !!n);
      const nameStr = names.length ? names.slice(0, 2).join("、") + (names.length > 2 ? ` +${names.length - 2}` : "") : "";
      if (filterTags.length > 0 && filterTagType !== "") {
        const tt = tagTypes.find((x) => x.id === filterTagType);
        return nameStr ? `${nameStr} · ${tt?.name ?? "分类"}` : `标签 · ${tt?.name ?? "分类"}`;
      }
      if (filterTags.length > 0) return nameStr ? `标签: ${nameStr}` : "标签";
      return "标签";
    });
    const statusLabel = derived(() => statusOptions.find((o) => o.value === filterStatus)?.label ?? "状态");
    const sortLabel = derived(() => `${sortOptions.find((o) => o.value === sortField)?.label ?? "排序"} ${"↓"}`);
    const activeFilterCount = derived(() => 0 + 0 + 0 + filterTags.length + 0 + 0 + 0);
    const DEFAULT_COL_WIDTHS = {
      title: 220,
      lib: 80,
      duration: 70,
      res: 80,
      size: 70,
      rating: 80,
      tags: 150
    };
    const COL_WIDTHS_KEY = "manage-col-widths";
    let colWidths = {
      ...DEFAULT_COL_WIDTHS,
      ...JSON.parse(localStorage.getItem(COL_WIDTHS_KEY) || "{}")
    };
    const gridTemplate = derived(() => `36px 56px minmax(${colWidths.title ?? 220}px, 2fr) ${colWidths.lib ?? 80}px ${colWidths.duration ?? 70}px ${colWidths.res ?? 80}px ${colWidths.size ?? 70}px ${colWidths.rating ?? 80}px minmax(${colWidths.tags ?? 150}px, 1fr)`);
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      $$renderer3.push(`<div class="toolbar svelte-1xiju0e"><div class="chips svelte-1xiju0e"><div class="chip-wrap svelte-1xiju0e"><button${attr_class("chip svelte-1xiju0e", void 0, { "active": false })}><span>${escape_html(libLabel())}</span><span class="caret svelte-1xiju0e">▾</span></button> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> <div class="chip-wrap svelte-1xiju0e"><button${attr_class("chip svelte-1xiju0e", void 0, { "active": false })}><span>${escape_html(typeLabel())}</span><span class="caret svelte-1xiju0e">▾</span></button> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> <div class="chip-wrap svelte-1xiju0e"><button${attr_class("chip svelte-1xiju0e", void 0, { "active": filterTags.length > 0 || filterTagType !== "" })}><span>${escape_html(tagLabel())}</span><span class="caret svelte-1xiju0e">▾</span></button> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> <div class="chip-wrap svelte-1xiju0e"><button${attr_class("chip svelte-1xiju0e", void 0, { "active": false })}><span>${escape_html(statusLabel())}</span><span class="caret svelte-1xiju0e">▾</span></button> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> <div class="chip-wrap svelte-1xiju0e"><button class="chip svelte-1xiju0e"><span>${escape_html(sortLabel())}</span><span class="caret svelte-1xiju0e">▾</span></button> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> `);
      if (activeFilterCount() > 0) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<button class="clear svelte-1xiju0e">清除筛选 (${escape_html(activeFilterCount())})</button>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> <div class="toolbar-actions svelte-1xiju0e">`);
      {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<button class="reset-cols-btn svelte-1xiju0e" title="重置列宽"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"></path><path d="M3 4v4h4"></path></svg> <span>重置列宽</span></button>`);
      }
      $$renderer3.push(`<!--]--> <button class="import-btn svelte-1xiju0e"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M8 2v8M4.5 6.5L8 10l3.5-3.5" stroke-linecap="round" stroke-linejoin="round"></path><path d="M2 12v1.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V12" stroke-linecap="round"></path></svg> <span>导入媒体库</span></button> <button class="import-btn svelte-1xiju0e" title="从网络 URL 导入媒体"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg> <span>网络导入</span></button></div> <div class="view-switch svelte-1xiju0e"><button${attr_class("vs-btn svelte-1xiju0e", void 0, { "active": view === "list" })} title="列表视图"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M3 5h18v2H3V5zm0 6h18v2H3v-2zm0 6h18v2H3v-2z" fill="currentColor"></path></svg> <span>列表</span></button> <button${attr_class("vs-btn svelte-1xiju0e", void 0, { "active": view === "grid" })} title="网格视图"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z" fill="currentColor"></path></svg> <span>网格</span></button></div></div> <div${attr_class("batch-bar svelte-1xiju0e", void 0, { "show": selectedCount() > 0 })}><div class="batch-left svelte-1xiju0e"><label class="select-all-wrap svelte-1xiju0e"><input type="checkbox"${attr("checked", allOnPageSelected(), true)}${attr("indeterminate", someOnPageSelected(), true)}/> <span>已选 <strong class="svelte-1xiju0e">${escape_html(selectedCount())}</strong> 项</span></label> <button class="clear-sel svelte-1xiju0e">取消选择</button></div> <div class="batch-actions svelte-1xiju0e"><button class="batch-btn svelte-1xiju0e"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42z" fill="currentColor"></path></svg> 批量打标</button> <button class="batch-btn svelte-1xiju0e"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M12 2l2.95 5.98 6.6.96-4.77 4.65 1.13 6.57L12 17.55l-5.91 3.11 1.13-6.57L2.45 9.44l6.6-.96L12 2z" fill="currentColor"></path></svg> 批量评分</button> <button class="batch-btn svelte-1xiju0e"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-2 6h-4v3h-2v-3H8l4-4 4 4z" fill="currentColor"></path></svg> 移动到库</button> <button class="batch-btn svelte-1xiju0e"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"></path><path d="M12 11v6M9 14l3 3 3-3"></path></svg> 移动到目录</button> <button class="batch-btn svelte-1xiju0e"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg> 批量重命名</button> <button class="batch-btn svelte-1xiju0e"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"></path></svg> 删除</button> <button class="batch-btn svelte-1xiju0e"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" fill="currentColor"></path></svg> 导出</button> <button class="batch-btn svelte-1xiju0e"${attr("disabled", batchScraping, true)}>`);
      {
        $$renderer3.push("<!--[-1-->");
        $$renderer3.push(`<svg viewBox="0 0 24 24" width="14" height="14"><path d="M20.2 6 3 11l-.9-2.4c-.3-.9.2-1.9 1-2.2l14-4.5c.9-.3 1.9.2 2.2 1zM6.2 5.3l3.1 3.9M12.4 3.4l3.1 4M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"></path></svg> 批量刮削`);
      }
      $$renderer3.push(`<!--]--></button></div></div> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> <div class="manage-content svelte-1xiju0e">`);
      if (loading && items.length === 0) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div class="state svelte-1xiju0e">加载中…</div>`);
      } else if (error) {
        $$renderer3.push("<!--[1-->");
        $$renderer3.push(`<div class="state error svelte-1xiju0e">${escape_html(error)}</div>`);
      } else if (items.length === 0) {
        $$renderer3.push("<!--[2-->");
        $$renderer3.push(`<div class="state empty svelte-1xiju0e"><div class="empty-icon svelte-1xiju0e">📭</div> <div class="empty-text svelte-1xiju0e">没有匹配的媒体</div> <div class="empty-hint svelte-1xiju0e">尝试调整筛选条件</div></div>`);
      } else {
        $$renderer3.push("<!--[3-->");
        $$renderer3.push(`<div class="list-view svelte-1xiju0e"><div${attr_class("list-head svelte-1xiju0e", void 0, { "resizing": false })}${attr_style(`grid-template-columns:${gridTemplate()}`)}><div class="checkbox-cell svelte-1xiju0e"><input type="checkbox"${attr("checked", allOnPageSelected(), true)}${attr("indeterminate", someOnPageSelected(), true)} class="svelte-1xiju0e"/></div> <div class="col col-thumb svelte-1xiju0e"></div> <div class="col col-title svelte-1xiju0e"><span>标题</span> <span class="col-resize svelte-1xiju0e"></span></div> <div class="col col-lib svelte-1xiju0e"><span>库</span> <span class="col-resize svelte-1xiju0e"></span></div> <div class="col col-duration svelte-1xiju0e"><span>时长</span> <span class="col-resize svelte-1xiju0e"></span></div> <div class="col col-res svelte-1xiju0e"><span>分辨率</span> <span class="col-resize svelte-1xiju0e"></span></div> <div class="col col-size svelte-1xiju0e"><span>大小</span> <span class="col-resize svelte-1xiju0e"></span></div> <div class="col col-rating svelte-1xiju0e"><span>评分</span> <span class="col-resize svelte-1xiju0e"></span></div> <div class="col col-tags svelte-1xiju0e"><span>标签</span> <span class="col-resize svelte-1xiju0e"></span></div></div> <div class="list-body"><!--[-->`);
        const each_array_8 = ensure_array_like(items);
        for (let $$index_9 = 0, $$length = each_array_8.length; $$index_9 < $$length; $$index_9++) {
          let media = each_array_8[$$index_9];
          $$renderer3.push(`<div${attr_class("row svelte-1xiju0e", void 0, { "selected": selected.has(media.id) })}${attr_style(`grid-template-columns:${gridTemplate()}`)} role="button" tabindex="0"><div class="checkbox-cell svelte-1xiju0e"><input type="checkbox"${attr("checked", selected.has(media.id), true)} class="svelte-1xiju0e"/></div> <div class="col col-thumb svelte-1xiju0e"><div class="mini-thumb svelte-1xiju0e">`);
          if (media.poster) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<img${attr("src", mediaApi.posterUrl(media.id, media.updated_at))} alt="" loading="lazy" class="svelte-1xiju0e" onerror="this.__e=event"/>`);
          } else if (media.thumbnail) {
            $$renderer3.push("<!--[1-->");
            $$renderer3.push(`<img${attr("src", mediaApi.thumbnailUrl(media.id, media.updated_at))} alt="" loading="lazy" class="svelte-1xiju0e" onerror="this.__e=event"/>`);
          } else {
            $$renderer3.push("<!--[-1-->");
            $$renderer3.push(`<span class="fb svelte-1xiju0e">${escape_html(media.type === "video" ? "▶" : media.type === "audio" ? "♪" : "▣")}</span>`);
          }
          $$renderer3.push(`<!--]--></div></div> <div class="col col-title svelte-1xiju0e"${attr("title", media.filename)}><span${attr_class("title-text svelte-1xiju0e", void 0, { "missing": media.file_missing })}>${escape_html(media.filename)}</span> `);
          if (!media.file_missing && (media.source_type === "network" || media.source_type === "both")) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<span class="src-badge net svelte-1xiju0e"${attr("title", media.source_type === "both" ? "本地 + 网络源" : "网络媒体")}>${escape_html(media.source_type === "both" ? "本+网" : "网")}</span>`);
          } else {
            $$renderer3.push("<!--[-1-->");
          }
          $$renderer3.push(`<!--]--> `);
          if (media.file_missing) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<span${attr_class("src-badge svelte-1xiju0e", void 0, { "has-net": hasNetworkSource(media) })}${attr("title", hasNetworkSource(media) ? "本地文件丢失 — 可从网络源播放" : "本地文件丢失")}>${escape_html(hasNetworkSource(media) ? "🔗" : "⚠")}</span>`);
          } else {
            $$renderer3.push("<!--[-1-->");
          }
          $$renderer3.push(`<!--]--> `);
          if (media.title && media.title !== media.filename) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<span class="title-sub svelte-1xiju0e">${escape_html(media.title)}</span>`);
          } else {
            $$renderer3.push("<!--[-1-->");
          }
          $$renderer3.push(`<!--]--> `);
          if (media.favorite) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<span class="fav svelte-1xiju0e">♥</span>`);
          } else {
            $$renderer3.push("<!--[-1-->");
          }
          $$renderer3.push(`<!--]--></div> <div class="col col-lib svelte-1xiju0e">${escape_html(libraryMap()[media.library_id] ?? "—")}</div> <div class="col col-duration svelte-1xiju0e">${escape_html(media.duration ? formatTime(media.duration) : "—")}</div> <div class="col col-res svelte-1xiju0e">${escape_html(formatResolution(media.width, media.height))}</div> <div class="col col-size svelte-1xiju0e">${escape_html(formatSize(media.size))}</div> <div class="col col-rating svelte-1xiju0e">`);
          RatingStars($$renderer3, { value: media.rating, size: 12, readonly: true });
          $$renderer3.push(`<!----></div> <div class="col col-tags svelte-1xiju0e">`);
          if (media.tags && media.tags.length) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<div class="tag-list svelte-1xiju0e"><!--[-->`);
            const each_array_9 = ensure_array_like(media.tags.slice(0, 3));
            for (let $$index_8 = 0, $$length2 = each_array_9.length; $$index_8 < $$length2; $$index_8++) {
              let tid = each_array_9[$$index_8];
              $$renderer3.push(`<span class="tag svelte-1xiju0e">${escape_html(tagMap()[tid] ?? tid)}</span>`);
            }
            $$renderer3.push(`<!--]--> `);
            if (media.tags.length > 3) {
              $$renderer3.push("<!--[0-->");
              $$renderer3.push(`<span class="tag more svelte-1xiju0e">+${escape_html(media.tags.length - 3)}</span>`);
            } else {
              $$renderer3.push("<!--[-1-->");
            }
            $$renderer3.push(`<!--]--></div>`);
          } else {
            $$renderer3.push("<!--[-1-->");
            $$renderer3.push(`—`);
          }
          $$renderer3.push(`<!--]--></div></div>`);
        }
        $$renderer3.push(`<!--]--></div></div>`);
      }
      $$renderer3.push(`<!--]--></div> `);
      if (items.length > 0) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div class="pager svelte-1xiju0e"><div class="pager-left svelte-1xiju0e"><button class="pg-btn svelte-1xiju0e"${attr("disabled", page2 <= 1, true)}>‹</button> <!--[-->`);
        const each_array_11 = ensure_array_like(pageList(page2, totalPages(), maxVisiblePages()));
        for (let $$index_11 = 0, $$length = each_array_11.length; $$index_11 < $$length; $$index_11++) {
          let p = each_array_11[$$index_11];
          if (p === "…") {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<span class="pg-ellipsis svelte-1xiju0e">…</span>`);
          } else {
            $$renderer3.push("<!--[-1-->");
            $$renderer3.push(`<button${attr_class("pg-btn svelte-1xiju0e", void 0, { "active": p === page2 })}>${escape_html(p)}</button>`);
          }
          $$renderer3.push(`<!--]-->`);
        }
        $$renderer3.push(`<!--]--> <button class="pg-btn svelte-1xiju0e"${attr("disabled", page2 >= totalPages(), true)}>›</button></div> <div class="pager-right svelte-1xiju0e"><span>共 ${escape_html(total.toLocaleString("zh-CN"))} 项</span> <span>每页</span> `);
        $$renderer3.select(
          { value: pageSize, onchange: onPageSizeChange, class: "" },
          ($$renderer4) => {
            $$renderer4.option({ value: 30 }, ($$renderer5) => {
              $$renderer5.push(`30`);
            });
            $$renderer4.option({ value: 50 }, ($$renderer5) => {
              $$renderer5.push(`50`);
            });
            $$renderer4.option({ value: 100 }, ($$renderer5) => {
              $$renderer5.push(`100`);
            });
            $$renderer4.option({ value: 200 }, ($$renderer5) => {
              $$renderer5.push(`200`);
            });
          },
          "svelte-1xiju0e"
        );
        $$renderer3.push(`</div></div>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      TagSelector($$renderer3, {
        tags,
        multiple: true,
        title: "批量打标",
        onselect: (ids) => batchAddTags(ids),
        oncancel: () => tagSelectorOpen = false,
        get open() {
          return tagSelectorOpen;
        },
        set open($$value) {
          tagSelectorOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      ConfirmDialog($$renderer3, {
        title: "删除已选媒体",
        description: `将删除已选 ${selectedCount()} 项媒体。

媒体将被移入回收站，30 天内可在回收站中恢复。超过 30 天将被永久删除。`,
        confirmText: "删除",
        danger: true,
        onconfirm: batchDelete,
        oncancel: () => deleteDialogOpen = false,
        get open() {
          return deleteDialogOpen;
        },
        set open($$value) {
          deleteDialogOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      if (toast) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div${attr_class("toast svelte-1xiju0e", void 0, { "ok": toast.type === "ok", "err": toast.type === "err" })}>${escape_html(toast.msg)}</div>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      NetworkImportDialog($$renderer3, {
        onsuccess: loadMedia,
        get open() {
          return networkImportOpen;
        },
        set open($$value) {
          networkImportOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----> `);
      EditMediaDialog($$renderer3, {
        media: editMediaTarget,
        onsuccess: loadMedia,
        get open() {
          return editDialogOpen;
        },
        set open($$value) {
          editDialogOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!---->`);
    }
    do {
      $$settled = true;
      $$inner_renderer = $$renderer2.copy();
      $$render_inner($$inner_renderer);
    } while (!$$settled);
    $$renderer2.subsume($$inner_renderer);
  });
}
function FileExplorerView($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let libraries = [];
    let selectedLibraryId = "";
    let busy = false;
    const currentLibrary = derived(() => libraries.find((lib) => lib.id === selectedLibraryId) ?? null);
    const canImport = derived(() => !!currentLibrary());
    $$renderer2.push(`<div class="explorer svelte-1mbd5pc"><header class="explorer-header svelte-1mbd5pc"><div><div class="eyebrow svelte-1mbd5pc">资源管理器</div> <h1 class="svelte-1mbd5pc">媒体管理</h1> <p class="svelte-1mbd5pc">直接管理系统文件夹、媒体文件和没有实体文件的网络记录</p></div> <div class="header-actions svelte-1mbd5pc"><button class="button svelte-1mbd5pc"${attr("disabled", !canImport() || busy, true)}>新建文件夹</button> <button class="button primary svelte-1mbd5pc"${attr("disabled", !canImport() || busy, true)}><span class="button-icon svelte-1mbd5pc">＋</span> 导入单个文件</button> <button class="button svelte-1mbd5pc"${attr("disabled", !selectedLibraryId, true)}>扫描资源库</button></div></header> <div class="manage-layout svelte-1mbd5pc"><aside class="explorer-tree svelte-1mbd5pc"><div class="tree-heading svelte-1mbd5pc"><span>资源库与目录</span><button class="tree-new-folder svelte-1mbd5pc" title="新建文件夹" aria-label="新建文件夹"${attr("disabled", !canImport() || busy, true)}>＋</button></div> `);
    DirectoryTree($$renderer2, { libraries });
    $$renderer2.push(`<!----></aside> <section class="manage-pane svelte-1mbd5pc">`);
    MediaManageView($$renderer2, {
      libraries: librariesStore.libraries,
      tags: librariesStore.tags,
      tagTypes: librariesStore.tagTypes
    });
    $$renderer2.push(`<!----></section></div></div> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
function ManageModuleView($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { kind } = $$props;
    let media = [];
    let mediaTotal = 0;
    let tasks = [];
    let libraries = [];
    let query = "";
    let status = "all";
    let busyIds = /* @__PURE__ */ new Set();
    const title = derived(() => ({
      issues: "问题中心",
      metadata: "元数据与刮削",
      tasks: "任务队列",
      history: "操作记录",
      libraries: "资源库状态"
    })[kind]);
    const subtitle = derived(() => ({
      issues: "集中处理文件丢失、标签缺失和元数据不完整的媒体",
      metadata: "检查匹配质量、补齐封面，并跟踪批量刮削任务",
      tasks: "查看扫描、刮削和缩略图任务的实时状态",
      history: "基于系统任务记录回溯已执行的后台操作",
      libraries: "监控资源库容量、刮削模式与扫描状态"
    })[kind]);
    const missingFiles = derived(() => media.filter((item) => item.file_missing));
    const untagged = derived(() => media.filter((item) => item.tags.length === 0));
    const incompleteMetadata = derived(() => media.filter((item) => !item.series_id && (!item.poster || !item.scrape_data)));
    const activeTasks = derived(() => tasks.filter((task) => task.status === "running" || task.status === "pending"));
    const filteredTasks = derived(() => tasks.filter((task) => {
      const text = `${task.title} ${task.message ?? ""} ${task.type}`.toLowerCase();
      return text.includes(query.trim().toLowerCase());
    }));
    const metadataItems = derived(() => incompleteMetadata().filter((item) => `${item.title ?? ""} ${item.filename}`.toLowerCase().includes(query.trim().toLowerCase())));
    const historyTasks = derived(() => tasks.filter((t) => ["completed", "failed", "cancelled"].includes(t.status)).sort((a, b) => (b.completed_at ?? b.updated_at).localeCompare(a.completed_at ?? a.updated_at)));
    const filteredHistory = derived(() => historyTasks().filter((task) => {
      const text = `${task.title} ${task.message ?? ""} ${task.type}`.toLowerCase();
      return text.includes(query.trim().toLowerCase());
    }));
    function taskLabel(task) {
      return {
        scan: "扫描",
        scrape: "刮削",
        thumbnail: "缩略图",
        metadata: "元数据",
        ai_tag: "AI 标签",
        subtitle: "字幕",
        hash: "校验"
      }[task.type] ?? task.type;
    }
    function statusLabel(value) {
      return {
        pending: "等待中",
        running: "运行中",
        completed: "已完成",
        failed: "失败",
        cancelled: "已取消"
      }[value];
    }
    $$renderer2.push(`<div class="module-view svelte-1karhhu"><header class="module-head svelte-1karhhu"><div><div class="eyebrow svelte-1karhhu">管理 / ${escape_html(title())}</div> <h1 class="svelte-1karhhu">${escape_html(title())}</h1> <p class="svelte-1karhhu">${escape_html(subtitle())}</p></div> <div class="head-actions svelte-1karhhu">`);
    if (kind === "metadata") {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<button class="btn primary svelte-1karhhu"${attr("disabled", busyIds.has("batch-scrape") || metadataItems().length === 0, true)}>批量刮削</button>`);
    } else if (kind === "tasks") {
      $$renderer2.push("<!--[1-->");
      $$renderer2.push(`<button class="btn svelte-1karhhu"${attr("disabled", busyIds.has("clear-tasks"), true)}>清理已结束</button>`);
    } else if (kind === "libraries") {
      $$renderer2.push("<!--[2-->");
      $$renderer2.push(`<button class="btn primary svelte-1karhhu">新建资源库</button>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> <button class="icon-btn svelte-1karhhu" title="刷新" aria-label="刷新">↻</button></div></header> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (kind === "issues") {
      $$renderer2.push("<!--[2-->");
      $$renderer2.push(`<div class="metric-strip svelte-1karhhu"><button class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(missingFiles().length)}</strong><span class="svelte-1karhhu">文件丢失</span></button> <button class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(untagged().length)}</strong><span class="svelte-1karhhu">缺少标签</span></button> <button class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(incompleteMetadata().length)}</strong><span class="svelte-1karhhu">元数据不完整</span></button> <div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(mediaTotal)}</strong><span class="svelte-1karhhu">媒体记录</span></div></div> <section class="work-section"><div class="section-title svelte-1karhhu"><div><h2 class="svelte-1karhhu">优先处理</h2><p class="svelte-1karhhu">问题按文件可用性、元数据、标签顺序归并</p></div></div> <div class="issue-grid svelte-1karhhu"><article class="issue-panel critical svelte-1karhhu"><header class="svelte-1karhhu"><span>文件丢失</span><strong class="svelte-1karhhu">${escape_html(missingFiles().length)}</strong></header> `);
      const each_array = ensure_array_like(missingFiles().slice(0, 6));
      if (each_array.length !== 0) {
        $$renderer2.push("<!--[-->");
        for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
          let item = each_array[$$index];
          $$renderer2.push(`<button class="compact-row svelte-1karhhu"><span class="svelte-1karhhu"><b class="svelte-1karhhu">${escape_html(item.title ?? item.filename)}</b><small class="svelte-1karhhu">${escape_html(item.path || "本地路径不可用")}</small></span><i class="svelte-1karhhu">检查</i></button>`);
        }
      } else {
        $$renderer2.push("<!--[!-->");
        $$renderer2.push(`<div class="empty svelte-1karhhu">没有丢失文件</div>`);
      }
      $$renderer2.push(`<!--]--> <button class="panel-action svelte-1karhhu">进入文件与路径处理</button></article> <article class="issue-panel svelte-1karhhu"><header class="svelte-1karhhu"><span>缺少封面或匹配</span><strong class="svelte-1karhhu">${escape_html(incompleteMetadata().length)}</strong></header> `);
      const each_array_1 = ensure_array_like(incompleteMetadata().slice(0, 6));
      if (each_array_1.length !== 0) {
        $$renderer2.push("<!--[-->");
        for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
          let item = each_array_1[$$index_1];
          $$renderer2.push(`<div class="compact-row svelte-1karhhu"><span class="svelte-1karhhu"><b class="svelte-1karhhu">${escape_html(item.title ?? item.filename)}</b><small class="svelte-1karhhu">${escape_html(item.poster ? "缺少完整匹配信息" : "缺少封面")}</small></span><button${attr("disabled", busyIds.has(`media-${item.id}`), true)} class="svelte-1karhhu">刮削</button></div>`);
        }
      } else {
        $$renderer2.push("<!--[!-->");
        $$renderer2.push(`<div class="empty svelte-1karhhu">元数据状态正常</div>`);
      }
      $$renderer2.push(`<!--]--> <button class="panel-action svelte-1karhhu">打开元数据工作台</button></article> <article class="issue-panel svelte-1karhhu"><header class="svelte-1karhhu"><span>缺少标签</span><strong class="svelte-1karhhu">${escape_html(untagged().length)}</strong></header> `);
      const each_array_2 = ensure_array_like(untagged().slice(0, 6));
      if (each_array_2.length !== 0) {
        $$renderer2.push("<!--[-->");
        for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
          let item = each_array_2[$$index_2];
          $$renderer2.push(`<button class="compact-row svelte-1karhhu"><span class="svelte-1karhhu"><b class="svelte-1karhhu">${escape_html(item.title ?? item.filename)}</b><small class="svelte-1karhhu">${escape_html(item.filename)}</small></span><i class="svelte-1karhhu">编辑</i></button>`);
        }
      } else {
        $$renderer2.push("<!--[!-->");
        $$renderer2.push(`<div class="empty svelte-1karhhu">当前媒体均有标签</div>`);
      }
      $$renderer2.push(`<!--]--> <button class="panel-action svelte-1karhhu">进入媒体资产批量治理</button></article></div></section>`);
    } else if (kind === "metadata") {
      $$renderer2.push("<!--[3-->");
      $$renderer2.push(`<div class="toolbar svelte-1karhhu"><div class="search svelte-1karhhu"><span>⌕</span><input${attr("value", query)} placeholder="搜索待处理媒体" class="svelte-1karhhu"/></div><span class="result-count svelte-1karhhu">${escape_html(metadataItems().length)} 项待处理</span></div> <div class="data-table metadata-table svelte-1karhhu"><div class="table-head svelte-1karhhu"><span class="svelte-1karhhu">媒体</span><span class="svelte-1karhhu">识别状态</span><span class="svelte-1karhhu">封面</span><span class="svelte-1karhhu">更新时间</span><span class="svelte-1karhhu">操作</span></div> `);
      const each_array_3 = ensure_array_like(metadataItems());
      if (each_array_3.length !== 0) {
        $$renderer2.push("<!--[-->");
        for (let $$index_3 = 0, $$length = each_array_3.length; $$index_3 < $$length; $$index_3++) {
          let item = each_array_3[$$index_3];
          $$renderer2.push(`<div class="table-row svelte-1karhhu"><div class="media-cell svelte-1karhhu"><div class="mini-poster svelte-1karhhu">${escape_html(item.poster ? "图" : "—")}</div><span class="svelte-1karhhu"><b class="svelte-1karhhu">${escape_html(item.title ?? item.filename)}</b><small class="svelte-1karhhu">${escape_html(item.filename)}</small></span></div> <span${attr_class("svelte-1karhhu", void 0, { "warning": !item.scrape_data })}>${escape_html(item.scrape_data ? "已有匹配" : "未匹配")}</span> <span${attr_class("svelte-1karhhu", void 0, { "warning": !item.poster })}>${escape_html(item.poster ? "已就绪" : "缺失")}</span> <span class="svelte-1karhhu">${escape_html(formatDate(item.updated_at))}</span> <div class="row-actions svelte-1karhhu"><button class="svelte-1karhhu">详情</button><button class="accent svelte-1karhhu"${attr("disabled", busyIds.has(`media-${item.id}`), true)}>重新刮削</button></div></div>`);
        }
      } else {
        $$renderer2.push("<!--[!-->");
        $$renderer2.push(`<div class="empty large svelte-1karhhu">没有需要处理的媒体</div>`);
      }
      $$renderer2.push(`<!--]--></div>`);
    } else if (kind === "tasks" || kind === "history") {
      $$renderer2.push("<!--[4-->");
      if (kind === "history") {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="metric-strip task-metrics svelte-1karhhu"><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(historyTasks().length)}</strong><span class="svelte-1karhhu">已结束活动</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(tasks.filter((t) => t.status === "completed").length)}</strong><span class="svelte-1karhhu">完成</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(tasks.filter((t) => t.status === "failed").length)}</strong><span class="svelte-1karhhu">失败</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(tasks.filter((t) => t.status === "cancelled").length)}</strong><span class="svelte-1karhhu">已取消</span></div></div> <div class="toolbar svelte-1karhhu"><div class="search svelte-1karhhu"><span>⌕</span><input${attr("value", query)} placeholder="搜索操作记录" class="svelte-1karhhu"/></div></div> <div class="scope-note svelte-1karhhu">这里展示系统已持久化的任务活动记录（扫描、刮削、缩略图等后台操作）。文件重命名、标签编辑等细粒度审计尚未由后端记录，因此不会在此伪造。</div> <div class="history-list svelte-1karhhu">`);
        const each_array_4 = ensure_array_like(filteredHistory());
        if (each_array_4.length !== 0) {
          $$renderer2.push("<!--[-->");
          for (let $$index_4 = 0, $$length = each_array_4.length; $$index_4 < $$length; $$index_4++) {
            let task = each_array_4[$$index_4];
            $$renderer2.push(`<article class="history-row svelte-1karhhu"><div${attr_class("history-rail svelte-1karhhu", void 0, {
              "done": task.status === "completed",
              "failed": task.status === "failed",
              "cancelled": task.status === "cancelled"
            })}></div> <div class="history-main svelte-1karhhu"><div class="history-title svelte-1karhhu"><b class="svelte-1karhhu">${escape_html(task.title || taskLabel(task))}</b><span${attr_class(`status ${task.status}`, "svelte-1karhhu")}>${escape_html(statusLabel(task.status))}</span></div> <p class="svelte-1karhhu">${escape_html(task.message || task.error || `${taskLabel(task)}任务`)}</p></div> <div class="history-meta svelte-1karhhu"><time>${escape_html(formatDate(task.completed_at ?? task.updated_at))}</time> <span>${escape_html(task.current ?? 0)} / ${escape_html(task.total ?? 0)}</span></div></article>`);
          }
        } else {
          $$renderer2.push("<!--[!-->");
          $$renderer2.push(`<div class="empty large svelte-1karhhu">暂无操作记录</div>`);
        }
        $$renderer2.push(`<!--]--></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<div class="metric-strip task-metrics svelte-1karhhu"><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(activeTasks().length)}</strong><span class="svelte-1karhhu">正在执行</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(tasks.filter((t) => t.status === "failed").length)}</strong><span class="svelte-1karhhu">失败</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(tasks.filter((t) => t.status === "completed").length)}</strong><span class="svelte-1karhhu">已完成</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(tasks.length)}</strong><span class="svelte-1karhhu">保留记录</span></div></div> <div class="toolbar svelte-1karhhu"><div class="search svelte-1karhhu"><span>⌕</span><input${attr("value", query)} placeholder="搜索任务名称或类型" class="svelte-1karhhu"/></div> `);
        $$renderer2.select(
          { value: status, "aria-label": "任务状态", class: "" },
          ($$renderer3) => {
            $$renderer3.option({ value: "all" }, ($$renderer4) => {
              $$renderer4.push(`全部状态`);
            });
            $$renderer3.option({ value: "pending" }, ($$renderer4) => {
              $$renderer4.push(`等待中`);
            });
            $$renderer3.option({ value: "running" }, ($$renderer4) => {
              $$renderer4.push(`运行中`);
            });
            $$renderer3.option({ value: "completed" }, ($$renderer4) => {
              $$renderer4.push(`已完成`);
            });
            $$renderer3.option({ value: "failed" }, ($$renderer4) => {
              $$renderer4.push(`失败`);
            });
            $$renderer3.option({ value: "cancelled" }, ($$renderer4) => {
              $$renderer4.push(`已取消`);
            });
          },
          "svelte-1karhhu"
        );
        $$renderer2.push(`</div> <div class="task-list svelte-1karhhu">`);
        const each_array_5 = ensure_array_like(filteredTasks());
        if (each_array_5.length !== 0) {
          $$renderer2.push("<!--[-->");
          for (let $$index_5 = 0, $$length = each_array_5.length; $$index_5 < $$length; $$index_5++) {
            let task = each_array_5[$$index_5];
            $$renderer2.push(`<article class="task-row svelte-1karhhu"><div${attr_class("status-rail svelte-1karhhu", void 0, {
              "running": task.status === "running",
              "failed": task.status === "failed",
              "done": task.status === "completed"
            })}></div> <div class="task-main svelte-1karhhu"><div class="task-title svelte-1karhhu"><b>${escape_html(task.title || taskLabel(task))}</b><span${attr_class(`status ${task.status}`, "svelte-1karhhu")}>${escape_html(statusLabel(task.status))}</span></div><p class="svelte-1karhhu">${escape_html(task.message || task.error || `${taskLabel(task)}任务`)}</p><div class="progress svelte-1karhhu"><i${attr_style(`width:${Math.max(0, Math.min(100, task.progress || 0))}%`)} class="svelte-1karhhu"></i></div></div> <div class="task-meta svelte-1karhhu"><span>${escape_html(task.current ?? 0)} / ${escape_html(task.total ?? 0)}</span><time>${escape_html(formatDate(task.created_at))}</time></div> `);
            if (task.status === "running" || task.status === "pending") {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<button class="btn danger svelte-1karhhu"${attr("disabled", busyIds.has(`task-${task.id}`), true)}>取消</button>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></article>`);
          }
        } else {
          $$renderer2.push("<!--[!-->");
          $$renderer2.push(`<div class="empty large svelte-1karhhu">没有符合条件的任务记录</div>`);
        }
        $$renderer2.push(`<!--]--></div>`);
      }
      $$renderer2.push(`<!--]-->`);
    } else if (kind === "libraries") {
      $$renderer2.push("<!--[5-->");
      $$renderer2.push(`<div class="metric-strip svelte-1karhhu"><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(libraries.length)}</strong><span class="svelte-1karhhu">资源库</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(libraries.reduce((sum, item) => sum + (item.media_count ?? 0), 0))}</strong><span class="svelte-1karhhu">媒体记录</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(libraries.filter((item) => item.scrape_mode !== "none").length)}</strong><span class="svelte-1karhhu">启用刮削</span></div><div class="svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(activeTasks().length)}</strong><span class="svelte-1karhhu">活动任务</span></div></div> <div class="library-list svelte-1karhhu">`);
      const each_array_6 = ensure_array_like(libraries);
      if (each_array_6.length !== 0) {
        $$renderer2.push("<!--[-->");
        for (let $$index_6 = 0, $$length = each_array_6.length; $$index_6 < $$length; $$index_6++) {
          let library = each_array_6[$$index_6];
          $$renderer2.push(`<article class="library-row svelte-1karhhu"><div class="library-icon svelte-1karhhu">▰</div> <div class="library-main svelte-1karhhu"><div class="svelte-1karhhu"><h2 class="svelte-1karhhu">${escape_html(library.name)}</h2>`);
          if (library.is_restricted) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span class="restricted svelte-1karhhu">限制内容</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></div><p${attr("title", library.path)} class="svelte-1karhhu">${escape_html(library.path)}</p></div> <div class="library-stat svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(library.media_count ?? 0)}</strong><span class="svelte-1karhhu">媒体</span></div> <div class="library-stat svelte-1karhhu"><strong class="svelte-1karhhu">${escape_html(library.scrape_mode ?? "none")}</strong><span class="svelte-1karhhu">刮削模式</span></div> <div class="row-actions svelte-1karhhu"><button${attr("disabled", busyIds.has(`scan-${library.id}`), true)} class="svelte-1karhhu">扫描</button><button${attr("disabled", library.scrape_mode === "none" || busyIds.has(`scrape-${library.id}`), true)} class="svelte-1karhhu">刮削</button><button class="accent svelte-1karhhu">配置</button></div></article>`);
        }
      } else {
        $$renderer2.push("<!--[!-->");
        $$renderer2.push(`<div class="empty large svelte-1karhhu">尚未创建资源库</div>`);
      }
      $$renderer2.push(`<!--]--></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
function TagsManageView($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let tagTypes = [];
    const selectedTypeId = derived(() => tagManageStore.selectedTypeId);
    let tagTree = [];
    let selectedTagId = null;
    let selectedTagMedia = [];
    let multiSelectMode = false;
    let selectedTagIds = /* @__PURE__ */ new Set();
    let batchLoading = false;
    let batchDeleteOpen = false;
    let searchQuery = "";
    let sortBy = "name";
    let tagMediaCounts = {};
    let renamingId = null;
    let renamingName = "";
    let deleteTagOpen = false;
    let deleteTagTarget = null;
    let toast = null;
    let toastTimer = null;
    function showToast(msg, type = "ok") {
      toast = { msg, type };
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast = null, 2600);
    }
    const typeNameDisplay = {
      "actor": "演员",
      "genre": "类型",
      "theme": "主题",
      "custom": "自定义",
      "collection": "合集",
      "studio": "工作室",
      "av_actress": "女优",
      "av_genre": "AV类型",
      "av_studio": "厂商",
      "av_series": "系列",
      "av_director": "导演"
    };
    const displayTypeName = (name) => typeNameDisplay[name] ?? name;
    const selectedType = derived(() => tagTypes.find((t) => t.id === selectedTypeId()) ?? null);
    const flatTags = derived(() => {
      const out = [];
      const walk = (nodes) => {
        for (const n of nodes) {
          out.push(n);
          if (n.children.length > 0) walk(n.children);
        }
      };
      walk(tagTree);
      return out;
    });
    const typeTagCounts = derived(() => {
      const counts = /* @__PURE__ */ new Map();
      for (const t of tagTypes) counts.set(t.id, 0);
      const walk = (nodes) => {
        for (const n of nodes) {
          if (n.tag_type_id != null && counts.has(n.tag_type_id)) {
            counts.set(n.tag_type_id, (counts.get(n.tag_type_id) ?? 0) + 1);
          }
          if (n.children && n.children.length > 0) walk(n.children);
        }
      };
      walk(librariesStore.tags);
      return counts;
    });
    const displayTags = derived(() => {
      let list = flatTags();
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        list = list.filter((t) => t.name.toLowerCase().includes(q));
      }
      list = [...list];
      {
        list.sort((a, b) => a.name.localeCompare(b.name, "zh"));
      }
      return list;
    });
    const selectedTag = derived(() => flatTags().find((t) => t.id === selectedTagId) ?? null);
    const selectedCount = derived(() => selectedTagIds.size);
    async function confirmDeleteTag() {
      if (!deleteTagTarget) return;
      const target = deleteTagTarget;
      try {
        await client.delete(`/tags/${target.id}`);
        const remove = (nodes) => nodes.filter((n) => n.id !== target.id).map((n) => ({ ...n, children: remove(n.children) }));
        tagTree = remove(tagTree);
        if (selectedTagId === target.id) {
          selectedTagId = null;
          selectedTagMedia = [];
        }
        void librariesStore.reload();
        showToast("已删除标签");
      } catch {
        showToast("删除失败", "err");
      } finally {
        deleteTagTarget = null;
        deleteTagOpen = false;
      }
    }
    async function confirmBatchDelete() {
      if (selectedTagIds.size === 0) {
        batchDeleteOpen = false;
        return;
      }
      const ids = [...selectedTagIds];
      batchLoading = true;
      const remove = (nodes, id) => nodes.filter((n) => n.id !== id).map((n) => ({ ...n, children: remove(n.children, id) }));
      let success = 0;
      let failed = 0;
      const deletedIds = /* @__PURE__ */ new Set();
      for (const id of ids) {
        try {
          await client.delete(`/tags/${id}`);
          success++;
          deletedIds.add(id);
        } catch {
          failed++;
        }
      }
      if (deletedIds.size > 0) {
        let tree = tagTree;
        for (const id of deletedIds) {
          tree = remove(tree, id);
        }
        tagTree = tree;
        const newCounts = {};
        for (const [k, v] of Object.entries(tagMediaCounts)) {
          if (!deletedIds.has(Number(k))) newCounts[Number(k)] = v;
        }
        tagMediaCounts = newCounts;
      }
      batchLoading = false;
      batchDeleteOpen = false;
      selectedTagIds = /* @__PURE__ */ new Set();
      if (success > 0) {
        void librariesStore.reload();
        showToast(`已删除 ${success} 个标签${failed > 0 ? `，${failed} 个失败` : ""}`, failed > 0 ? "err" : "ok");
      } else {
        showToast("删除失败", "err");
      }
    }
    function getThumbUrl(m) {
      if (m.thumbnail) return mediaApi.thumbnailUrl(m.id, m.updated_at);
      if (m.poster) return mediaApi.posterUrl(m.id, m.updated_at);
      return "";
    }
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      $$renderer3.push(`<div class="tags-page svelte-158yluj"><div class="tags-head svelte-158yluj"><div><h2 class="svelte-158yluj">标签治理</h2> <p class="svelte-158yluj">维护标签体系、合并重复标签和检查孤立标签</p></div> <button class="button primary svelte-158yluj">＋ 新建标签类型</button></div> <div class="tag-admin svelte-158yluj"><aside class="tag-groups svelte-158yluj"><div class="side-label svelte-158yluj">标签类型</div> <!--[-->`);
      const each_array = ensure_array_like([...tagTypes].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)));
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let type = each_array[$$index];
        $$renderer3.push(`<button${attr_class("tag-group svelte-158yluj", void 0, { "active": selectedTypeId() === type.id })}><span class="tag-group-dot svelte-158yluj"${attr_style(type.color ? `background:${type.color}` : "")}></span> <span class="tag-group-name svelte-158yluj">${escape_html(displayTypeName(type.name))}</span> <span class="tag-group-count svelte-158yluj">${escape_html(typeTagCounts().get(type.id) ?? 0)}</span></button>`);
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></aside> <section class="tag-content svelte-158yluj"><div class="tag-toolbar svelte-158yluj"><span class="toolbar-title svelte-158yluj">类型标签</span> <span class="toolbar-meta svelte-158yluj">${escape_html(flatTags().length)} 个标签</span> <span class="toolbar-spacer svelte-158yluj"></span> <div class="search-input-wrap svelte-158yluj"><svg class="search-icon svelte-158yluj" viewBox="0 0 16 16" width="14" height="14" fill="none"><circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" stroke-width="1.5"></circle><line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"></line></svg> <input type="text" class="search-input svelte-158yluj" placeholder="搜索标签…"${attr("value", searchQuery)}/></div> `);
      $$renderer3.select(
        { class: "sort-select", value: sortBy },
        ($$renderer4) => {
          $$renderer4.option({ value: "name" }, ($$renderer5) => {
            $$renderer5.push(`名称排序`);
          });
          $$renderer4.option({ value: "created_at" }, ($$renderer5) => {
            $$renderer5.push(`创建时间`);
          });
        },
        "svelte-158yluj"
      );
      $$renderer3.push(` `);
      if (selectedTypeId() !== null) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<button class="mini-btn svelte-158yluj">＋ 新建标签</button> <button${attr_class("mini-btn svelte-158yluj", void 0, { "active": multiSelectMode })}${attr("disabled", batchLoading, true)}>${escape_html("批量操作")}</button>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> <div class="card-area svelte-158yluj">`);
      if (selectedTypeId() === null) {
        $$renderer3.push("<!--[1-->");
        $$renderer3.push(`<div class="state-msg empty svelte-158yluj"><div class="empty-icon svelte-158yluj">🏷</div> <div class="empty-text svelte-158yluj">请从侧边栏选择一个标签类型</div></div>`);
      } else if (displayTags().length === 0) {
        $$renderer3.push("<!--[2-->");
        $$renderer3.push(`<div class="state-msg empty svelte-158yluj"><div class="empty-icon svelte-158yluj">🏷</div> <div class="empty-text svelte-158yluj">${escape_html("该类型下暂无标签")}</div> `);
        {
          $$renderer3.push("<!--[0-->");
          $$renderer3.push(`<button class="link-btn svelte-158yluj">新建标签</button>`);
        }
        $$renderer3.push(`<!--]--></div>`);
      } else {
        $$renderer3.push("<!--[-1-->");
        $$renderer3.push(`<div class="card-grid svelte-158yluj"><!--[-->`);
        const each_array_1 = ensure_array_like(displayTags());
        for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
          let tag = each_array_1[$$index_1];
          $$renderer3.push(`<button${attr_class("tag-card svelte-158yluj", void 0, {
            "selected": selectedTagId === tag.id || multiSelectMode,
            "renaming": renamingId === tag.id,
            "multi": multiSelectMode
          })}>`);
          {
            $$renderer3.push("<!--[-1-->");
          }
          $$renderer3.push(`<!--]--> `);
          if (selectedTagId === tag.id && renamingId !== tag.id && !multiSelectMode) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<span class="selected-badge svelte-158yluj">已选中</span>`);
          } else {
            $$renderer3.push("<!--[-1-->");
          }
          $$renderer3.push(`<!--]--> `);
          if (renamingId === tag.id) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<input type="text" class="rename-input svelte-158yluj"${attr("value", renamingName)}/> <div class="rename-actions svelte-158yluj"><button class="icon-btn svelte-158yluj">✓</button> <button class="icon-btn svelte-158yluj">✕</button></div>`);
          } else {
            $$renderer3.push("<!--[-1-->");
            $$renderer3.push(`<span class="card-color-dot svelte-158yluj"${attr_style(`background:${tag.color ?? selectedType()?.color ?? "#8e8e93"}`)}></span> <span class="card-name svelte-158yluj">${escape_html(tag.name)}</span> <span class="card-subtitle svelte-158yluj">${escape_html(tagMediaCounts[tag.id] ?? 0)} 个媒体 · ${escape_html(selectedType()?.is_builtin ? "系统标签" : "用户标签")}</span>`);
          }
          $$renderer3.push(`<!--]--></button>`);
        }
        $$renderer3.push(`<!--]--></div>`);
      }
      $$renderer3.push(`<!--]--></div> `);
      if (tagOps.addingChildTo) {
        $$renderer3.push("<!--[0-->");
        const parent = flatTags().find((t) => String(t.id) === tagOps.addingChildTo);
        if (parent) {
          $$renderer3.push("<!--[0-->");
          $$renderer3.push(`<div class="inline-ops-row svelte-158yluj"><div class="inline-ops-label svelte-158yluj">为「${escape_html(parent.name)}」添加子标签：</div> <input class="inline-ops-input svelte-158yluj" placeholder="子标签名称"${attr("value", tagOps.newChildName)}/> <button class="mini-btn ghost svelte-158yluj">取消</button></div>`);
        } else {
          $$renderer3.push("<!--[-1-->");
        }
        $$renderer3.push(`<!--]-->`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      if (tagOps.moveTypeFor) {
        $$renderer3.push("<!--[0-->");
        const moveTag = flatTags().find((t) => String(t.id) === tagOps.moveTypeFor);
        if (moveTag) {
          $$renderer3.push("<!--[0-->");
          $$renderer3.push(`<div class="inline-ops-row svelte-158yluj"><div class="inline-ops-label svelte-158yluj">将「${escape_html(moveTag.name)}」移动到：</div> <div class="inline-ops-types svelte-158yluj"><!--[-->`);
          const each_array_2 = ensure_array_like(tagTypes);
          for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
            let tt = each_array_2[$$index_2];
            $$renderer3.push(`<button${attr_class("inline-type-option svelte-158yluj", void 0, { "active": tt.id === moveTag.tag_type_id })}><span class="type-dot svelte-158yluj"${attr_style(`background:${tt.color}`)}></span> <span>${escape_html(displayTypeName(tt.name))}</span></button>`);
          }
          $$renderer3.push(`<!--]--></div> <button class="mini-btn ghost svelte-158yluj">取消</button></div>`);
        } else {
          $$renderer3.push("<!--[-1-->");
        }
        $$renderer3.push(`<!--]-->`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      if (selectedTag() && selectedTagId !== null && !multiSelectMode && renamingId !== selectedTagId) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div class="media-section svelte-158yluj"><div class="media-section-head svelte-158yluj"><h2 class="media-title-head svelte-158yluj">「${escape_html(selectedTag().name)}」关联的媒体</h2> <div class="media-head-actions svelte-158yluj"><button class="action-btn svelte-158yluj">重命名</button> <button class="action-btn danger svelte-158yluj">删除</button></div></div> <div class="media-list-wrap svelte-158yluj">`);
        if (selectedTagMedia.length === 0) {
          $$renderer3.push("<!--[1-->");
          $$renderer3.push(`<div class="state-msg subtle svelte-158yluj">暂无关联媒体</div>`);
        } else {
          $$renderer3.push("<!--[-1-->");
          $$renderer3.push(`<div class="media-items svelte-158yluj"><!--[-->`);
          const each_array_3 = ensure_array_like(selectedTagMedia);
          for (let $$index_3 = 0, $$length = each_array_3.length; $$index_3 < $$length; $$index_3++) {
            let m = each_array_3[$$index_3];
            $$renderer3.push(`<div class="media-item svelte-158yluj">`);
            if (m.thumbnail || m.poster) {
              $$renderer3.push("<!--[0-->");
              $$renderer3.push(`<img class="media-thumb svelte-158yluj"${attr("src", getThumbUrl(m))} alt=""/>`);
            } else {
              $$renderer3.push("<!--[-1-->");
              $$renderer3.push(`<div class="media-thumb placeholder svelte-158yluj"></div>`);
            }
            $$renderer3.push(`<!--]--> <span class="media-title svelte-158yluj">${escape_html(m.title || m.filename)}</span> `);
            if (m.year) {
              $$renderer3.push("<!--[0-->");
              $$renderer3.push(`<span class="media-year svelte-158yluj">${escape_html(m.year)}</span>`);
            } else {
              $$renderer3.push("<!--[-1-->");
            }
            $$renderer3.push(`<!--]--></div>`);
          }
          $$renderer3.push(`<!--]--></div>`);
        }
        $$renderer3.push(`<!--]--></div></div>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></section></div></div> `);
      ConfirmDialog($$renderer3, {
        title: "删除标签",
        description: deleteTagTarget ? `确定删除「${deleteTagTarget.name}」？

该操作将影响已使用此标签的媒体记录。` : "",
        confirmText: "删除",
        danger: true,
        onconfirm: confirmDeleteTag,
        oncancel: () => {
          deleteTagTarget = null;
          deleteTagOpen = false;
        },
        get open() {
          return deleteTagOpen;
        },
        set open($$value) {
          deleteTagOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      ConfirmDialog($$renderer3, {
        title: "批量删除标签",
        description: `确定删除选中的 ${selectedCount()} 个标签？

该操作将影响已使用这些标签的媒体记录，且不可撤销。`,
        confirmText: batchLoading ? "删除中…" : "删除",
        danger: true,
        disableConfirm: batchLoading,
        onconfirm: confirmBatchDelete,
        oncancel: () => {
          if (!batchLoading) batchDeleteOpen = false;
        },
        get open() {
          return batchDeleteOpen;
        },
        set open($$value) {
          batchDeleteOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      if (toast) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div${attr_class("toast svelte-158yluj", void 0, { "ok": toast.type === "ok", "err": toast.type === "err" })}>${escape_html(toast.msg)}</div>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]-->`);
    }
    do {
      $$settled = true;
      $$inner_renderer = $$renderer2.copy();
      $$render_inner($$inner_renderer);
    } while (!$$settled);
    $$renderer2.subsume($$inner_renderer);
  });
}
function RecycleBinView($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    function hasNetworkSource2(item) {
      return !!item.urls?.some((u) => u.url_role === "source" && !u.is_expired);
    }
    function statusLabel(item) {
      if (item.file_missing && hasNetworkSource2(item)) return "🔗 网络可用";
      if (item.file_missing) return "⚠ 文件丢失";
      if (item.media_type === "network" || item.media_type === "both") return "🔗 含网络源";
      return "—";
    }
    let items = [];
    let total = 0;
    let loading = false;
    let page2 = 1;
    const pageSize = 50;
    let toast = null;
    let toastTimer = null;
    let restoreDialogOpen = false;
    let permanentDialogOpen = false;
    let emptyDialogOpen = false;
    function showToast(msg, type = "ok") {
      toast = { msg, type };
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast = null, 3e3);
    }
    let listReqId = 0;
    async function loadItems() {
      const myId = ++listReqId;
      loading = true;
      try {
        let currentPage = page2;
        let resp = await client.get(`/recycle-bin?page=${currentPage}&page_size=${pageSize}`);
        if (myId !== listReqId) return;
        let list = resp.items;
        let totalCount = resp.total;
        const totalPages2 = Math.max(1, Math.ceil(totalCount / pageSize));
        if (currentPage > totalPages2) {
          currentPage = totalPages2;
          page2 = totalPages2;
          resp = await client.get(`/recycle-bin?page=${currentPage}&page_size=${pageSize}`);
          if (myId !== listReqId) return;
          list = resp.items;
          totalCount = resp.total;
        }
        items = list;
        total = totalCount;
      } catch {
        showToast("加载回收站失败", "err");
      } finally {
        if (myId === listReqId) loading = false;
      }
    }
    async function confirmRestore() {
      return;
    }
    async function confirmPermanent() {
      return;
    }
    async function confirmPurgeLocal() {
      return;
    }
    const canPurgeLocal = derived(() => false);
    async function confirmEmpty() {
      try {
        const resp = await client.post("/recycle-bin/empty?delete_files=true");
        showToast(`已清空回收站，共删除 ${resp.deleted_count} 项（含本地文件）`);
        page2 = 1;
        await loadItems();
      } catch {
        showToast("清空失败", "err");
      } finally {
        emptyDialogOpen = false;
      }
    }
    const totalPages = derived(() => Math.max(1, Math.ceil(total / pageSize)));
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      $$renderer3.push(`<div class="recycle-view svelte-8tbvj"><div class="warning-bar svelte-8tbvj"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg> <span class="svelte-8tbvj">回收站中的媒体记录将保留直到手动清除。「仅删本地文件」会把媒体恢复回媒体页并标记为"文件丢失"；「彻底删除」会同时删除本地文件和系统记录。</span> `);
      if (total > 0) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<button class="btn-empty svelte-8tbvj">清空回收站</button>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> `);
      if (loading) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div class="empty-state svelte-8tbvj">加载中...</div>`);
      } else if (items.length === 0) {
        $$renderer3.push("<!--[1-->");
        $$renderer3.push(`<div class="empty-state svelte-8tbvj"><svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg> <p>回收站为空</p></div>`);
      } else {
        $$renderer3.push("<!--[-1-->");
        $$renderer3.push(`<div class="recycle-list svelte-8tbvj"><div class="list-header svelte-8tbvj"><span class="col-thumb"></span> <span class="col-title svelte-8tbvj">标题</span> <span class="col-status svelte-8tbvj">状态</span> <span class="col-size">大小</span> <span class="col-date">删除时间</span> <span class="col-actions svelte-8tbvj">操作</span></div> <!--[-->`);
        const each_array = ensure_array_like(items);
        for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
          let item = each_array[$$index];
          $$renderer3.push(`<div class="list-row svelte-8tbvj"><div class="col-thumb svelte-8tbvj">`);
          if (item.poster_path) {
            $$renderer3.push("<!--[0-->");
            $$renderer3.push(`<img${attr("src", `${"http://127.0.0.1:8765"}/api/media/${item.id}/poster`)} alt="" class="svelte-8tbvj"/>`);
          } else if (item.thumbnail_path) {
            $$renderer3.push("<!--[1-->");
            $$renderer3.push(`<img${attr("src", `${"http://127.0.0.1:8765"}/api/media/${item.id}/thumbnail`)} alt="" class="svelte-8tbvj"/>`);
          } else {
            $$renderer3.push("<!--[-1-->");
            $$renderer3.push(`<div class="thumb-placeholder svelte-8tbvj"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><rect x="2" y="6" width="20" height="14" rx="2"></rect><path d="M2 10h20"></path></svg></div>`);
          }
          $$renderer3.push(`<!--]--></div> <div class="col-title svelte-8tbvj"${attr("title", item.title)}>${escape_html(item.title)}</div> <div class="col-status svelte-8tbvj"><span${attr_class("status-tag svelte-8tbvj", void 0, {
            "net": item.file_missing && hasNetworkSource2(item),
            "missing": item.file_missing && !hasNetworkSource2(item)
          })}>${escape_html(statusLabel(item))}</span></div> <div class="col-size">${escape_html(item.file_size ? formatSize(item.file_size) : "-")}</div> <div class="col-date">${escape_html(item.deleted_at ? formatDate(item.deleted_at) : "-")}</div> <div class="col-actions svelte-8tbvj"><button class="btn-restore svelte-8tbvj">恢复</button> <button class="btn-permanent svelte-8tbvj">彻底删除</button></div></div>`);
        }
        $$renderer3.push(`<!--]--></div> `);
        if (totalPages() > 1) {
          $$renderer3.push("<!--[0-->");
          $$renderer3.push(`<div class="pagination svelte-8tbvj"><button${attr("disabled", page2 <= 1, true)} class="svelte-8tbvj">上一页</button> <span>${escape_html(page2)} / ${escape_html(totalPages())}</span> <button${attr("disabled", page2 >= totalPages(), true)} class="svelte-8tbvj">下一页</button></div>`);
        } else {
          $$renderer3.push("<!--[-1-->");
        }
        $$renderer3.push(`<!--]-->`);
      }
      $$renderer3.push(`<!--]--></div> `);
      ConfirmDialog($$renderer3, {
        title: "恢复媒体",
        description: "",
        confirmText: "恢复",
        onconfirm: confirmRestore,
        get open() {
          return restoreDialogOpen;
        },
        set open($$value) {
          restoreDialogOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----> `);
      ConfirmDialog($$renderer3, {
        title: "彻底删除",
        description: "",
        confirmText: "确认删除",
        danger: true,
        extraButtonText: canPurgeLocal() ? "仅删本地文件" : "",
        onextra: confirmPurgeLocal,
        onconfirm: confirmPermanent,
        get open() {
          return permanentDialogOpen;
        },
        set open($$value) {
          permanentDialogOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----> `);
      ConfirmDialog($$renderer3, {
        title: "清空回收站",
        description: `将永久删除回收站中的全部 ${total} 项记录及其本地文件，此操作不可撤销。`,
        confirmText: "全部清空",
        danger: true,
        onconfirm: confirmEmpty,
        get open() {
          return emptyDialogOpen;
        },
        set open($$value) {
          emptyDialogOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----> `);
      if (toast) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div${attr_class("toast svelte-8tbvj", void 0, { "err": toast.type === "err" })}>${escape_html(toast.msg)}</div>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]-->`);
    }
    do {
      $$settled = true;
      $$inner_renderer = $$renderer2.copy();
      $$render_inner($$inner_renderer);
    } while (!$$settled);
    $$renderer2.subsume($$inner_renderer);
  });
}
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    const currentSection = derived(() => {
      const section = store_get($$store_subs ??= {}, "$pageStore", page).url.searchParams.get("section");
      if (section === "overview") return "dashboard";
      if (section === "recycle") return "trash";
      if (section === "assets") return "files";
      if (section === "dashboard" || section === "files" || section === "issues" || section === "metadata" || section === "tags" || section === "trash" || section === "tasks" || section === "history" || section === "libraries") {
        return section;
      }
      const tab = store_get($$store_subs ??= {}, "$pageStore", page).url.searchParams.get("tab");
      if (tab === "tags") return "tags";
      if (tab === "recycle") return "trash";
      return "files";
    });
    head("1s1mgsk", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>管理 — vitoice</title>`);
      });
    });
    $$renderer2.push(`<div class="manage-page svelte-1s1mgsk"><div class="manage-main svelte-1s1mgsk">`);
    if (currentSection() === "dashboard") {
      $$renderer2.push("<!--[0-->");
      OverviewView($$renderer2);
    } else if (currentSection() === "files") {
      $$renderer2.push("<!--[1-->");
      FileExplorerView($$renderer2);
    } else if (currentSection() === "tags") {
      $$renderer2.push("<!--[2-->");
      $$renderer2.push(`<div class="tags-view svelte-1s1mgsk">`);
      TagsManageView($$renderer2);
      $$renderer2.push(`<!----></div>`);
    } else if (currentSection() === "trash") {
      $$renderer2.push("<!--[3-->");
      RecycleBinView($$renderer2);
    } else {
      $$renderer2.push("<!--[-1-->");
      ManageModuleView($$renderer2, { kind: currentSection() });
    }
    $$renderer2.push(`<!--]--></div></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
export {
  _page as default
};
