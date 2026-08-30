import "clsx";
import "@sveltejs/kit/internal";
import "../../chunks/exports.js";
import "../../chunks/utils2.js";
import "@sveltejs/kit/internal/server";
import "../../chunks/root.js";
import "../../chunks/state.svelte.js";
import { a as attr_class, c as attr, e as escape_html, d as derived, s as store_get, u as unsubscribe_stores, f as ensure_array_like, h as attr_style, i as stringify, j as bind_props } from "../../chunks/index.js";
import { o as onDestroy } from "../../chunks/index-server.js";
import { p as page, l as librariesStore } from "../../chunks/libraries.svelte.js";
import "../../chunks/client2.js";
import { n as navigation } from "../../chunks/navigation.svelte.js";
import { s as settingsStore } from "../../chunks/settings.svelte.js";
import { s as safeColor, t as tagOps, d as displayTypeName, T as TYPE_PALETTE } from "../../chunks/tagOps.svelte.js";
import { f as flattenTags, m as mediaApi } from "../../chunks/media.js";
import { g as goto } from "../../chunks/client.js";
import { f as formatTime } from "../../chunks/format.js";
class TasksStore {
  items = [];
  open = false;
  loading = false;
  get active() {
    return this.items.filter((t) => t.status === "pending" || t.status === "running");
  }
  get count() {
    return this.active.length;
  }
  get hasFailed() {
    return this.items.some((t) => t.status === "failed");
  }
  isActive(status) {
    return this.items.some((t) => t.status === status);
  }
  setItems(items) {
    this.items = items;
  }
  upsert(task) {
    const idx = this.items.findIndex((t) => t.id === task.id);
    if (idx >= 0) {
      this.items[idx] = task;
    } else {
      this.items = [task, ...this.items];
    }
  }
  updateProgress(id, patch) {
    const idx = this.items.findIndex((t) => t.id === id);
    if (idx >= 0) {
      this.items[idx] = { ...this.items[idx], ...patch };
    }
  }
  remove(id) {
    this.items = this.items.filter((t) => t.id !== id);
  }
  clearCompleted() {
    this.items = this.items.filter((t) => t.status === "pending" || t.status === "running");
  }
  toggle() {
    this.open = !this.open;
  }
  /** 立即从后端拉取最新任务列表（任务发起成功后调用，徽标马上出现）。 */
  async refresh() {
    const { tasksApi } = await import("../../chunks/tasks.js");
    try {
      const items = await tasksApi.list();
      this.setItems(items ?? []);
    } catch {
    }
  }
  openPanel() {
    this.open = true;
  }
  closePanel() {
    this.open = false;
  }
}
const tasks = new TasksStore();
let workAreaMaximized = false;
function workAreaSize() {
  return {
    width: window.screen.availWidth,
    height: window.screen.availHeight
  };
}
function isWorkAreaMaximized() {
  return workAreaMaximized;
}
function sizeLooksMaximized(size) {
  const { width, height } = workAreaSize();
  return size.width >= width - 2 && size.height >= height - 2;
}
function TopNav($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    const path = derived(() => store_get($$store_subs ??= {}, "$page", page).url.pathname);
    const searchShortcut = "Ctrl K";
    let theme = "dark";
    function tabActive(prefix) {
      return path() === prefix || path().startsWith(prefix + "/");
    }
    let isMaximized = false;
    let unlistenResize = null;
    async function getCurrentWindow() {
      try {
        const { getCurrentWindow: getCurrentWindow2 } = await import("@tauri-apps/api/window");
        return getCurrentWindow2();
      } catch {
        return null;
      }
    }
    async function initWindow() {
      const win = await getCurrentWindow();
      if (!win) return;
      try {
        isMaximized = await win.isMaximized() || isWorkAreaMaximized();
      } catch {
      }
      unlistenResize = await win.onResized(async () => {
        try {
          const s = await win.outerSize();
          isMaximized = s ? sizeLooksMaximized(s) : await win.isMaximized();
        } catch {
        }
      });
    }
    onDestroy(() => {
      unlistenResize?.();
    });
    let isTauri = false;
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      isTauri = true;
      initWindow().catch(() => {
      });
    }
    $$renderer2.push(`<header class="topnav svelte-lpwtu7" data-tauri-drag-region=""><div class="left svelte-lpwtu7" data-tauri-drag-region=""><button class="logo svelte-lpwtu7" data-tauri-drag-region="false" aria-label="vitoice 首页"><svg class="logo-mark svelte-lpwtu7" viewBox="0 0 64 64" width="24" height="24" fill="none" aria-hidden="true"><rect x="2" y="2" width="60" height="60" rx="16" fill="url(#logo-grad)"></rect><path d="M19 19.5v25l20.5-12.5z" fill="#f4fffb"></path><rect x="44" y="24" width="4" height="16" rx="2" fill="#f4fffb"></rect><rect x="52" y="19" width="4" height="26" rx="2" fill="#f4fffb" opacity="0.78"></rect><defs><linearGradient id="logo-grad" x1="0" y1="0" x2="32" y2="32"><stop stop-color="#3ed6a4"></stop><stop offset="1" stop-color="#0e9473"></stop></linearGradient></defs></svg> <span class="logo-text svelte-lpwtu7">vitoice</span></button> <nav class="tabs svelte-lpwtu7" data-tauri-drag-region=""><button${attr_class("tab svelte-lpwtu7", void 0, { "active": tabActive("/media") })}${attr("aria-current", tabActive("/media") ? "page" : void 0)} data-tauri-drag-region="false"><svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="10" rx="1.5"></rect><path d="M2 6h12M5 3v10M11 3v10" stroke-opacity="0.5"></path></svg> <span>媒体</span></button> <button${attr_class("tab svelte-lpwtu7", void 0, { "active": tabActive("/manage") })}${attr("aria-current", tabActive("/manage") ? "page" : void 0)} data-tauri-drag-region="false"><svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4h6M2 8h9M2 12h5" stroke-linecap="round"></path><circle cx="12" cy="4" r="1.8"></circle><circle cx="11" cy="8" r="1.8"></circle><circle cx="10" cy="12" r="1.8"></circle></svg> <span>管理</span></button> <button${attr_class("tab svelte-lpwtu7", void 0, { "active": tabActive("/settings") || path() === "/libraries" })}${attr("aria-current", tabActive("/settings") || path() === "/libraries" ? "page" : void 0)} data-tauri-drag-region="false"><svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="2.2"></circle><path d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1M12.6 12.6l-1.1-1.1M4.5 4.5L3.4 3.4"></path></svg> <span>设置</span> <span class="changed svelte-lpwtu7">含资源库</span></button></nav></div> <div class="center svelte-lpwtu7" data-tauri-drag-region=""><button class="search svelte-lpwtu7" data-tauri-drag-region="false" type="button"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="7" cy="7" r="5"></circle><line x1="10.5" y1="10.5" x2="14" y2="14" stroke-linecap="round"></line></svg> <span class="search-placeholder svelte-lpwtu7">搜索媒体</span> <kbd class="search-kbd svelte-lpwtu7">${escape_html(searchShortcut)}</kbd></button></div> <div class="right svelte-lpwtu7" data-tauri-drag-region=""><button class="theme-switch svelte-lpwtu7" data-tauri-drag-region="false" role="switch"${attr("aria-checked", theme === "light")} aria-label="切换深浅色" title="切换深浅色"><svg class="sun svelte-lpwtu7" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><circle cx="8" cy="8" r="2.7"></circle><path d="M8 1.5v1.4M8 13.1v1.4M1.5 8h1.4M13.1 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1" stroke-linecap="round"></path></svg> <svg class="moon svelte-lpwtu7" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7z" stroke-linejoin="round"></path></svg> <span class="theme-switch-thumb svelte-lpwtu7"></span></button> <button class="icon-btn task-btn svelte-lpwtu7" title="任务中心" data-tauri-drag-region="false" aria-label="任务中心"><svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="6"></circle><path d="M8 4.5V8l2.2 1.4" stroke-linecap="round" stroke-linejoin="round"></path></svg> `);
    if (tasks.count > 0) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="badge svelte-lpwtu7">${escape_html(tasks.count)}</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button></div> `);
    if (isTauri) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="window-controls svelte-lpwtu7" data-tauri-drag-region="false"><button class="win-btn svelte-lpwtu7" data-tauri-drag-region="false" aria-label="最小化" title="最小化"><svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4"><line x1="3" y1="6" x2="9" y2="6" stroke-linecap="round"></line></svg></button> <button class="win-btn svelte-lpwtu7" data-tauri-drag-region="false" aria-label="最大化/还原" title="最大化/还原">`);
      if (isMaximized) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="3.5" y="4.5" width="5" height="5" rx="0.8"></rect><path d="M4.5 4.5V3.5h5v5h-1" stroke-opacity="0.55" stroke-linejoin="round"></path></svg>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="3" y="3" width="6" height="6" rx="1"></rect></svg>`);
      }
      $$renderer2.push(`<!--]--></button> <button class="win-btn close svelte-lpwtu7" data-tauri-drag-region="false" aria-label="关闭" title="关闭"><svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4"><line x1="3.5" y1="3.5" x2="8.5" y2="8.5" stroke-linecap="round"></line><line x1="8.5" y1="3.5" x2="3.5" y2="8.5" stroke-linecap="round"></line></svg></button></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></header>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
class SidebarStore {
  collapsed = false;
  width = 260;
  get expanded() {
    return !this.collapsed;
  }
  toggle() {
    this.collapsed = !this.collapsed;
  }
  set(collapsed) {
    this.collapsed = collapsed;
  }
  expand() {
    this.collapsed = false;
  }
  collapse() {
    this.collapsed = true;
  }
}
const sidebar = new SidebarStore();
function MediaSidebar($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const libraries = derived(() => librariesStore.libraries);
    const visibleLibraries = derived(() => settingsStore.showRestricted ? libraries() : libraries().filter((l) => !l.is_restricted));
    const tags = derived(() => librariesStore.tags);
    const tagTypes = derived(() => librariesStore.tagTypes);
    const smartFolders = derived(() => librariesStore.smartFolders);
    const totalCount = derived(() => librariesStore.totalCount);
    const favoriteCount = derived(() => librariesStore.favoriteCount);
    const loading = derived(() => librariesStore.loading);
    const collapsed = derived(() => sidebar.collapsed);
    function isActive(type, value) {
      return navigation.current.type === type && navigation.current.value === value;
    }
    const OPEN_TAG_GROUPS_KEY = "vitoice.sidebar.openTagGroups";
    function loadOpenTagGroups() {
      try {
        if (typeof localStorage === "undefined") return null;
        const raw = localStorage.getItem(OPEN_TAG_GROUPS_KEY);
        if (!raw) return null;
        const arr = JSON.parse(raw);
        if (!Array.isArray(arr)) return null;
        const set = /* @__PURE__ */ new Set();
        for (const v of arr) {
          if (typeof v === "number" && Number.isFinite(v)) set.add(v);
        }
        return set;
      } catch {
        return null;
      }
    }
    let sidebarOpenTagGroups = loadOpenTagGroups();
    const currentLibrary = derived(() => navigation.current.type === "library" ? libraries().find((l) => l.id === navigation.current.value) ?? null : null);
    const isAvLibrary = derived(() => currentLibrary()?.scrape_mode === "av");
    const isNonAvLibrary = derived(() => currentLibrary() !== null && !isAvLibrary());
    const avTypeIds = derived(() => new Set(tagTypes().filter((tt) => tt.name.startsWith("av_")).map((tt) => tt.id)));
    const filteredTags = derived(() => {
      const flat = flattenTags(tags());
      if (avTypeIds().size === 0) return flat;
      if (isAvLibrary()) {
        return flat.filter((t) => avTypeIds().has(t.tag_type_id ?? -1));
      }
      if (isNonAvLibrary()) {
        return flat.filter((t) => !avTypeIds().has(t.tag_type_id ?? -1));
      }
      return flat;
    });
    const groupedTags = derived(() => {
      const map = /* @__PURE__ */ new Map();
      for (const t of filteredTags()) {
        const tid = t.tag_type_id ?? 0;
        if (!map.has(tid)) map.set(tid, []);
        map.get(tid).push(t);
      }
      const typeOrder = (id) => {
        const tt = tagTypes().find((x) => x.id === id);
        return tt?.sort_order ?? 9999;
      };
      return Array.from(map.entries()).sort((a, b) => typeOrder(a[0]) - typeOrder(b[0])).map(([typeId, items]) => ({
        typeId,
        typeName: displayTypeName(tagTypes().find((tt) => tt.id === typeId)?.name ?? "其他"),
        typeColor: tagTypes().find((tt) => tt.id === typeId)?.color ?? null,
        items,
        open: sidebarOpenTagGroups !== null && sidebarOpenTagGroups.has(typeId)
      }));
    });
    $$renderer2.push(`<div class="sidebar-scroll"><section class="section"><div class="section-head" data-tip="资源库"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="sec-title">资源库</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<button class="add-btn" title="新建资源库" aria-label="新建资源库"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="8" y1="3" x2="8" y2="13" stroke-linecap="round"></line><line x1="3" y1="8" x2="13" y2="8" stroke-linecap="round"></line></svg></button>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <button${attr_class("item", void 0, { "active": isActive("all", "all") })} data-tip="全部媒体"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect><path d="M2 6h12M6 2.5v11" stroke-opacity="0.4"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">全部媒体</span> <span class="count">${escape_html(totalCount())}</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <!--[-->`);
    const each_array = ensure_array_like(visibleLibraries());
    for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
      let lib = each_array[$$index];
      $$renderer2.push(`<button${attr_class("item", void 0, { "active": isActive("library", lib.id) })}${attr("data-tip", lib.name)}><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path></svg> `);
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="item-label">${escape_html(lib.name)}</span> `);
        if (lib.media_count != null) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="count">${escape_html(lib.media_count)}</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]-->`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></button>`);
    }
    $$renderer2.push(`<!--]--> `);
    if (collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<button class="item" data-tip="新建资源库" aria-label="新建资源库" title="新建资源库" style="color: var(--accent);"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6"><line x1="8" y1="3" x2="8" y2="13" stroke-linecap="round"></line><line x1="3" y1="8" x2="13" y2="8" stroke-linecap="round"></line></svg></button>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></section> <section class="section"><div class="section-head" data-tip="快捷入口"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 1.5l1.8 4.2 4.2.3-3.3 2.8 1.1 4.1L8 11l-3.8 2.3 1.1-4.1L2 6.5l4.2-.3L8 1.5z" stroke-linejoin="round"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="sec-title">快捷入口</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <button${attr_class("item", void 0, { "active": isActive("continue", "continue") })} data-tip="继续观看"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"></circle><path d="M6.5 5.5v5l4-2.5-4-2.5z" fill="currentColor" stroke="none"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">继续观看</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": isActive("recent", "recent") })} data-tip="最近添加"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"></circle><path d="M8 4.5V8l2.2 1.4" stroke-linecap="round" stroke-linejoin="round"></path><path d="M11 2.5l.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8.8-1.7z" fill="currentColor" stroke="none" opacity="0.8"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">最近添加</span><span class="count">${escape_html(totalCount())}</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": isActive("favorite", "favorite") })} data-tip="我的收藏"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 13.5s-5-3-5-7a2.8 2.8 0 0 1 5-1.5A2.8 2.8 0 0 1 13 6.5c0 4-5 7-5 7z" stroke-linejoin="round"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">我的收藏</span><span class="count">${escape_html(favoriteCount())}</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button></section> <section class="section"><div class="section-head" data-tip="智能文件夹"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4a1 1 0 0 1 1-1h3.5l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4z"></path><path d="M8 6.5l1 2 2 .2-1.5 1.4.4 2L8 11.2 6.1 12.1l.4-2L5 8.7l2-.2 1-2z" fill="currentColor" stroke="none" opacity="0.7"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="sec-title">智能文件夹</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> `);
    if (smartFolders().length === 0 && !loading()) {
      $$renderer2.push("<!--[0-->");
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="empty-hint">暂无智能文件夹</div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<div class="item disabled" data-tip="暂无智能文件夹"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4"><path d="M2 4a1 1 0 0 1 1-1h3.5l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4z"></path></svg></div>`);
      }
      $$renderer2.push(`<!--]-->`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<!--[-->`);
      const each_array_1 = ensure_array_like(smartFolders());
      for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
        let folder = each_array_1[$$index_1];
        $$renderer2.push(`<button${attr_class("item", void 0, { "active": isActive("smartfolder", String(folder.id)) })}${attr("data-tip", folder.name)}><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"${attr_style(safeColor(folder.color) ? `color:${safeColor(folder.color)}` : "")}><path d="M2 4a1 1 0 0 1 1-1h3.5l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4z"></path><path d="M8 6.5l1 2 2 .2-1.5 1.4.4 2L8 11.2 6.1 12.1l.4-2L5 8.7l2-.2 1-2z" fill="currentColor" stroke="none" opacity="0.7"></path></svg> `);
        if (!collapsed()) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="item-label">${escape_html(folder.name)}</span> `);
          if (folder.preview_count != null) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span class="count">${escape_html(folder.preview_count)}</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]-->`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></button>`);
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></section> <section class="section"><div class="section-head" data-tip="标签"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2h6.5L14 7.5 8.5 13 2 6.5V2z" stroke-linejoin="round"></path><circle cx="5" cy="5" r="1" fill="currentColor" stroke="none"></circle></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="sec-title">标签${escape_html(isAvLibrary() ? " (AV)" : "")}</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> `);
    if (filteredTags().length === 0 && !loading()) {
      $$renderer2.push("<!--[0-->");
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="empty-hint">暂无标签</div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<div class="item disabled" data-tip="暂无标签"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4"><path d="M2 2h6.5L14 7.5 8.5 13 2 6.5V2z" stroke-linejoin="round"></path></svg></div>`);
      }
      $$renderer2.push(`<!--]-->`);
    } else if (collapsed()) {
      $$renderer2.push("<!--[1-->");
      $$renderer2.push(`<!--[-->`);
      const each_array_2 = ensure_array_like(filteredTags());
      for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
        let tag = each_array_2[$$index_2];
        $$renderer2.push(`<button${attr_class("item", void 0, { "active": isActive("tag", tag.id) })}${attr("data-tip", tag.name)}><span class="tag-dot"${attr_style(safeColor(tag.color) ? `background:${safeColor(tag.color)}` : "")}></span></button>`);
      }
      $$renderer2.push(`<!--]-->`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="tag-groups svelte-nm05kb"><!--[-->`);
      const each_array_3 = ensure_array_like(groupedTags());
      for (let $$index_4 = 0, $$length = each_array_3.length; $$index_4 < $$length; $$index_4++) {
        let group = each_array_3[$$index_4];
        $$renderer2.push(`<div class="tag-group svelte-nm05kb">`);
        if (tagOps.renamingTypeId === group.typeId) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<div class="tag-group-head renaming svelte-nm05kb"><span class="tag-group-arrow svelte-nm05kb"></span> <input class="mt-rename-input"${attr("value", tagOps.renamingTypeName)}/></div>`);
        } else {
          $$renderer2.push("<!--[-1-->");
          $$renderer2.push(`<button class="tag-group-head svelte-nm05kb"><span class="tag-group-arrow svelte-nm05kb">${escape_html(group.open ? "▾" : "▸")}</span> <span class="tag-group-dot svelte-nm05kb"${attr_style(safeColor(group.typeColor) ? `background:${safeColor(group.typeColor)}` : "")}></span> <span class="tag-group-label svelte-nm05kb">${escape_html(group.typeName)}</span> <span class="tag-group-count svelte-nm05kb">${escape_html(group.items.length)}</span></button>`);
        }
        $$renderer2.push(`<!--]--> `);
        if (group.open) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<div class="tag-group-items svelte-nm05kb"><!--[-->`);
          const each_array_4 = ensure_array_like(group.items);
          for (let $$index_3 = 0, $$length2 = each_array_4.length; $$index_3 < $$length2; $$index_3++) {
            let tag = each_array_4[$$index_3];
            if (tagOps.renamingTagId === tag.id) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="item tag-item renaming svelte-nm05kb"><span class="tag-dot"${attr_style(safeColor(tag.color) ? `background:${safeColor(tag.color)}` : "")}></span> <input class="mt-rename-input"${attr("value", tagOps.renamingTagName)}/></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
              $$renderer2.push(`<button${attr_class("item tag-item svelte-nm05kb", void 0, { "active": isActive("tag", tag.id) })}${attr("data-tip", tag.name)}><span class="tag-dot"${attr_style(safeColor(tag.color) ? `background:${safeColor(tag.color)}` : "")}></span> <span class="item-label">${escape_html(tag.name)}</span> `);
              if (tag.count != null) {
                $$renderer2.push("<!--[0-->");
                $$renderer2.push(`<span class="count">${escape_html(tag.count)}</span>`);
              } else {
                $$renderer2.push("<!--[-1-->");
              }
              $$renderer2.push(`<!--]--></button>`);
            }
            $$renderer2.push(`<!--]-->`);
          }
          $$renderer2.push(`<!--]--></div>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div>`);
      }
      $$renderer2.push(`<!--]--></div>`);
    }
    $$renderer2.push(`<!--]--></section></div>`);
  });
}
function ManageSidebar($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    const collapsed = derived(() => sidebar.collapsed);
    let navCounts = {
      missing: 0,
      noPoster: 0,
      noMetadata: 0,
      deleted: 0,
      runningTasks: 0,
      local: 0,
      network: 0
    };
    const issueCount = derived(() => navCounts.missing + navCounts.noPoster + navCounts.noMetadata);
    let lastManageTab = "media";
    let lastManageSection = "files";
    const tabParam = derived(() => store_get($$store_subs ??= {}, "$page", page).url.searchParams.get("tab"));
    const manageTab = derived(() => tabParam() ?? lastManageTab);
    const sectionParam = derived(() => store_get($$store_subs ??= {}, "$page", page).url.searchParams.get("section"));
    const manageSection = derived(() => sectionParam() === "overview" ? "dashboard" : sectionParam() === "recycle" ? "trash" : sectionParam() && [
      "dashboard",
      "files",
      "issues",
      "assets",
      "metadata",
      "tags",
      "trash",
      "tasks",
      "history",
      "libraries"
    ].includes(sectionParam()) ? sectionParam() : tabParam() ? manageTab() === "tags" ? "tags" : manageTab() === "recycle" ? "trash" : "assets" : store_get($$store_subs ??= {}, "$page", page).url.pathname.startsWith("/manage") ? "files" : lastManageSection);
    const sourceFilter = derived(() => store_get($$store_subs ??= {}, "$page", page).url.searchParams.get("source") || "");
    $$renderer2.push(`<div class="sidebar-scroll"><section class="section"><div class="section-head" data-tip="工作区"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect><path d="M2 6h12M6 2.5v11" stroke-opacity="0.4"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="sec-title">工作区</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <button${attr_class("item", void 0, { "active": manageSection() === "dashboard" })} data-tip="资产概览"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="5" height="5" rx="1"></rect><rect x="9" y="2" width="5" height="5" rx="1"></rect><rect x="2" y="9" width="5" height="5" rx="1"></rect><rect x="9" y="9" width="5" height="5" rx="1"></rect></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">资产概览</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": manageSection() === "files" })} data-tip="媒体管理"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">媒体管理</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (!collapsed() && navCounts.missing > 0) ;
    else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": manageSection() === "issues" })} data-tip="问题中心"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2 1.8 13h12.4L8 2z"></path><path d="M8 6v3.2M8 11.5v.2" stroke-linecap="round"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">问题中心</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (!collapsed() && issueCount() > 0) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-count warn">${escape_html(issueCount())}</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": manageSection() === "metadata" })} data-tip="元数据与刮削"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 2.5h7l3 3V14H3z"></path><path d="M10 2.5V6h3M5.5 9h5M5.5 11.5h3.5"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">元数据与刮削</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (!collapsed() && navCounts.noMetadata > 0) ;
    else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": manageSection() === "tags" })} data-tip="标签治理"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 2h6.5L14 7.5 8.5 13 2 6.5V2z" stroke-linejoin="round"></path><circle cx="5" cy="5" r="1" fill="currentColor" stroke="none"></circle></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">标签治理</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": manageSection() === "trash" })} data-tip="回收站"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 4h10M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">回收站</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (!collapsed() && navCounts.deleted > 0) ;
    else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button></section> <section class="section"><div class="section-head" data-tip="运行状态"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 8h2l1.5-4 3 8 1.5-4h4"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="sec-title">运行状态</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <button${attr_class("item", void 0, { "active": manageSection() === "tasks" })} data-tip="任务队列"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 3h9M5 8h9M5 13h9"></path><circle cx="2.5" cy="3" r=".7" fill="currentColor"></circle><circle cx="2.5" cy="8" r=".7" fill="currentColor"></circle><circle cx="2.5" cy="13" r=".7" fill="currentColor"></circle></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">任务队列</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (!collapsed() && navCounts.runningTasks > 0) ;
    else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": manageSection() === "history" })} data-tip="操作记录"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="5.5"></circle><path d="M8 5v3.5l2.3 1.4"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">操作记录</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button></section> <section class="section"><div class="section-head" data-tip="资源库"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 5h4l1.4 1.5H14V13H2z"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="sec-title">资源库</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <button${attr_class("item", void 0, { "active": manageSection() === "libraries" })} data-tip="资源库状态"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4.5h12v8H2zM4 2.5h8v2"></path><path d="M5 8h6" stroke-opacity=".5"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="item-label">资源库状态</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></button></section> `);
    if (manageSection() === "files") {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<section class="section"><div class="section-head" data-tip="来源"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"></circle><path d="M2 8h12M8 2c1.5 2 1.5 10 0 12M8 2c-1.5 2-1.5 10 0 12" stroke-opacity="0.5"></path></svg> `);
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="sec-title">来源</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div> <button${attr_class("item", void 0, { "active": sourceFilter() === "" })} data-tip="全部来源"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect><path d="M2 6h12" stroke-opacity="0.4"></path></svg> `);
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="item-label">全部来源</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": sourceFilter() === "local" })} data-tip="本地媒体"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="10" rx="1.5"></rect><path d="M4.5 6.5h7M4.5 9.5h4" stroke-opacity="0.5"></path></svg> `);
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="item-label">本地媒体</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (!collapsed() && navCounts.local > 0) ;
      else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": sourceFilter() === "network" })} data-tip="网络媒体"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="5.5"></circle><path d="M2.5 8h11M8 2.5c2 2 2 7 0 11M8 2.5c-2 2-2 7 0 11" stroke-opacity="0.5"></path></svg> `);
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="item-label">网络媒体</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (!collapsed() && navCounts.network > 0) ;
      else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></button> <button${attr_class("item", void 0, { "active": sourceFilter() === "missing" })} data-tip="文件丢失"><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2 1.5 13.5h13L8 2z"></path><path d="M8 6.5v3M8 11.5v.5" stroke-width="1.8" stroke-linecap="round"></path></svg> `);
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="item-label">文件丢失</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (!collapsed() && navCounts.missing > 0) ;
      else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></button></section>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
function SettingsSidebar($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    const collapsed = derived(() => sidebar.collapsed);
    const pathname = derived(() => store_get($$store_subs ??= {}, "$page", page).url.pathname);
    const catParam = derived(() => store_get($$store_subs ??= {}, "$page", page).url.searchParams.get("cat"));
    const entries = [
      {
        id: "libraries",
        label: "资源库",
        href: "/libraries",
        icon: "folder"
      },
      {
        id: "appearance",
        label: "外观",
        href: "/settings?cat=appearance",
        icon: "sun"
      },
      {
        id: "content",
        label: "内容管理",
        href: "/settings?cat=content",
        icon: "shield"
      },
      {
        id: "tools",
        label: "外部工具",
        href: "/settings?cat=tools",
        icon: "wrench"
      },
      {
        id: "thumbnail",
        label: "缩略图",
        href: "/settings?cat=thumbnail",
        icon: "image"
      },
      {
        id: "ai",
        label: "AI 配置",
        href: "/settings?cat=ai",
        icon: "spark"
      },
      {
        id: "scrape",
        label: "刮削",
        href: "/settings?cat=scrape",
        icon: "clapper"
      },
      {
        id: "player",
        label: "播放器",
        href: "/settings?cat=player",
        icon: "play"
      },
      {
        id: "subtitle",
        label: "字幕",
        href: "/settings?cat=subtitle",
        icon: "subtitle"
      },
      {
        id: "database",
        label: "数据库",
        href: "/settings?cat=database",
        icon: "database"
      },
      {
        id: "about",
        label: "关于",
        href: "/settings?cat=about",
        icon: "info"
      }
    ];
    const activeId = derived(() => pathname().startsWith("/libraries") ? "libraries" : catParam() || "appearance");
    function entryIcon($$renderer3, icon) {
      if (icon === "folder") {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>`);
      } else if (icon === "sun") {
        $$renderer3.push("<!--[1-->");
        $$renderer3.push(`<circle cx="8" cy="8" r="2.7"></circle><path d="M8 1.5v1.4M8 13.1v1.4M1.5 8h1.4M13.1 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1" stroke-linecap="round"></path>`);
      } else if (icon === "shield") {
        $$renderer3.push("<!--[2-->");
        $$renderer3.push(`<path d="M8 2l5 1.7v3.2c0 3-1.7 5.3-5 7.1-3.3-1.8-5-4.1-5-7.1V3.7z"></path>`);
      } else if (icon === "wrench") {
        $$renderer3.push("<!--[3-->");
        $$renderer3.push(`<path d="M7.3 6.3a1 1 0 0 0 0 1.4l.8.8a1 1 0 0 0 1.4 0l3.8-3.8a4 4 0 0 1-5.6 5.6L4 13.6a1.5 1.5 0 0 1-2.1-2.1l3.3-3.3a4 4 0 0 1 2.1-1.9z"></path>`);
      } else if (icon === "image") {
        $$renderer3.push("<!--[4-->");
        $$renderer3.push(`<rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect><circle cx="6" cy="6.5" r="1.2"></circle><path d="M2 11.5l4-3 3 2.5 3-2 2 1.5" stroke-linecap="round"></path>`);
      } else if (icon === "spark") {
        $$renderer3.push("<!--[5-->");
        $$renderer3.push(`<path d="M8 1.8l1.6 4.6 4.6 1.6-4.6 1.6L8 14.2l-1.6-4.6L1.8 8l4.6-1.6z" stroke-linejoin="round"></path>`);
      } else if (icon === "clapper") {
        $$renderer3.push("<!--[6-->");
        $$renderer3.push(`<path d="M13.8 3.5H2.2a.7.7 0 0 0-.7.7v7.6a.7.7 0 0 0 .7.7h11.6a.7.7 0 0 0 .7-.7V4.2a.7.7 0 0 0-.7-.7z"></path><path d="M2 7h12M6 3.5v8.5M10 3.5v8.5" stroke-opacity=".5"></path>`);
      } else if (icon === "play") {
        $$renderer3.push("<!--[7-->");
        $$renderer3.push(`<circle cx="8" cy="8" r="6"></circle><path d="M6.5 5.5l4 2.5-4 2.5z" fill="currentColor" stroke="none"></path>`);
      } else if (icon === "subtitle") {
        $$renderer3.push("<!--[8-->");
        $$renderer3.push(`<rect x="2" y="3" width="12" height="10" rx="1.5"></rect><path d="M4.5 10h3M8 10h3.5" stroke-linecap="round"></path>`);
      } else if (icon === "database") {
        $$renderer3.push("<!--[9-->");
        $$renderer3.push(`<ellipse cx="8" cy="3.5" rx="5.5" ry="2"></ellipse><path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9"></path><path d="M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" stroke-opacity=".5"></path>`);
      } else if (icon === "info") {
        $$renderer3.push("<!--[10-->");
        $$renderer3.push(`<circle cx="8" cy="8" r="6"></circle><path d="M8 7.2V11M8 5.2v.2" stroke-linecap="round"></path>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]-->`);
    }
    $$renderer2.push(`<div class="sidebar-scroll"><section class="section"><div class="section-head" data-tip="设置"><svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="2.2"></circle><path d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1M12.6 12.6l-1.1-1.1M4.5 4.5L3.4 3.4"></path></svg> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="sec-title">设置</span>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <!--[-->`);
    const each_array = ensure_array_like(entries);
    for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
      let entry = each_array[$$index];
      $$renderer2.push(`<button${attr_class("item", void 0, { "active": activeId() === entry.id })}${attr("data-tip", entry.label)}><svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">`);
      entryIcon($$renderer2, entry.icon);
      $$renderer2.push(`<!----></svg> `);
      if (!collapsed()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="item-label">${escape_html(entry.label)}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></button>`);
    }
    $$renderer2.push(`<!--]--></section> `);
    if (!collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<section class="section"><div class="empty-hint">设置修改会自动保存。</div></section>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
function TagOverlays($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    if (
      // TagOverlays — renders the tag/type context menus and delete-confirmation
      // dialogs. All state and logic live in the `tagOps` store; this component
      // is purely the overlay UI.
      tagOps.typeContextMenu
    ) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="ctx-backdrop svelte-1pwnhm8" role="button" tabindex="-1" aria-label="关闭菜单"></div> <div class="tag-ctx-menu type-ctx-menu svelte-1pwnhm8"${attr_style(`left: ${Math.min(tagOps.typeContextMenu.x, window.innerWidth - 180)}px; top: ${Math.min(tagOps.typeContextMenu.y, window.innerHeight - 240)}px`)}><button class="ctx-item svelte-1pwnhm8"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" class="svelte-1pwnhm8"><path d="M11 2l3 3-8 8H3v-3l8-8z" stroke-linejoin="round"></path></svg> 重命名</button> <div class="ctx-sub-section"><div class="ctx-sub-label">颜色</div> <div class="ctx-palette"><!--[-->`);
      const each_array = ensure_array_like(TYPE_PALETTE);
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let c = each_array[$$index];
        $$renderer2.push(`<button${attr_class("ctx-color", void 0, { "active": tagOps.typeContextMenu.type.color === c })}${attr_style(`background:${c}`)}></button>`);
      }
      $$renderer2.push(`<!--]--></div></div> <div class="ctx-sep svelte-1pwnhm8"></div> <button class="ctx-item ctx-danger svelte-1pwnhm8"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" class="svelte-1pwnhm8"><path d="M3 4h10M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4"></path></svg> 删除类型</button></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (tagOps.deleteConfirmType) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="del-backdrop svelte-1pwnhm8" role="button" tabindex="-1" aria-label="关闭弹窗"><div class="del-dialog svelte-1pwnhm8" role="dialog" aria-label="删除确认"><div class="del-title svelte-1pwnhm8">确认删除标签类型？</div> <div class="del-desc svelte-1pwnhm8">「${escape_html(displayTypeName(tagOps.deleteConfirmType.name))}」及其所有标签将被永久删除，关联媒体将解除这些标签。</div> <div class="del-actions svelte-1pwnhm8"><button class="del-btn del-cancel svelte-1pwnhm8">取消</button> <button class="del-btn del-ok svelte-1pwnhm8">删除</button></div></div></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (tagOps.tagContextMenu) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="ctx-backdrop svelte-1pwnhm8" role="button" tabindex="-1" aria-label="关闭菜单"></div> <div class="tag-ctx-menu svelte-1pwnhm8"${attr_style(`left: ${Math.min(tagOps.tagContextMenu.x, window.innerWidth - 180)}px; top: ${Math.min(tagOps.tagContextMenu.y, window.innerHeight - 220)}px`)}><button class="ctx-item svelte-1pwnhm8"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" class="svelte-1pwnhm8"><path d="M11 2l3 3-8 8H3v-3l8-8z" stroke-linejoin="round"></path></svg> 重命名</button> <button class="ctx-item svelte-1pwnhm8"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" class="svelte-1pwnhm8"><line x1="8" y1="3" x2="8" y2="13" stroke-linecap="round"></line><line x1="3" y1="8" x2="13" y2="8" stroke-linecap="round"></line></svg> 添加子标签</button> <button class="ctx-item svelte-1pwnhm8"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" class="svelte-1pwnhm8"><circle cx="8" cy="8" r="6"></circle><circle cx="5.5" cy="6" r="0.8" fill="currentColor" stroke="none"></circle><circle cx="10.5" cy="6" r="0.8" fill="currentColor" stroke="none"></circle><circle cx="8" cy="10.5" r="0.8" fill="currentColor" stroke="none"></circle></svg> 设置颜色</button> <button class="ctx-item svelte-1pwnhm8"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" class="svelte-1pwnhm8"><path d="M3 6h7M3 6l2.5-2.5M3 6l2.5 2.5M13 10H6M13 10l-2.5-2.5M13 10l-2.5 2.5" stroke-linecap="round" stroke-linejoin="round"></path></svg> 移动到类型</button> <div class="ctx-sep svelte-1pwnhm8"></div> <button class="ctx-item ctx-danger svelte-1pwnhm8"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" class="svelte-1pwnhm8"><path d="M3 4h10M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4"></path></svg> 删除</button></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (tagOps.deleteConfirmTag) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="del-backdrop svelte-1pwnhm8" role="button" tabindex="-1" aria-label="关闭弹窗"><div class="del-dialog svelte-1pwnhm8" role="dialog" aria-label="删除确认"><div class="del-title svelte-1pwnhm8">确认删除标签？</div> <div class="del-desc svelte-1pwnhm8">「${escape_html(tagOps.deleteConfirmTag.name)}」及其子标签将被永久删除，关联媒体将解除此标签。</div> <div class="del-actions svelte-1pwnhm8"><button class="del-btn del-cancel svelte-1pwnhm8">取消</button> <button class="del-btn del-ok svelte-1pwnhm8">删除</button></div></div></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
function Sidebar($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    const collapsed = derived(() => sidebar.collapsed);
    const isManageRoute = derived(() => store_get($$store_subs ??= {}, "$page", page).url.pathname.startsWith("/manage"));
    const isSettingsRoute = derived(() => store_get($$store_subs ??= {}, "$page", page).url.pathname.startsWith("/settings") || store_get($$store_subs ??= {}, "$page", page).url.pathname.startsWith("/libraries"));
    const isDetailRoute = derived(() => store_get($$store_subs ??= {}, "$page", page).url.pathname.startsWith("/detail"));
    let lastMainRoute = "media";
    const showManageSidebar = derived(() => isManageRoute() || isDetailRoute() && lastMainRoute === "manage");
    const showSettingsSidebar = derived(() => isSettingsRoute() || isDetailRoute() && lastMainRoute === "settings");
    $$renderer2.push(`<aside${attr_class("sidebar svelte-6dohdz", void 0, { "collapsed": collapsed() })}><button class="toggle-btn svelte-6dohdz"${attr("aria-label", collapsed() ? "展开侧栏" : "收起侧栏")}${attr("title", collapsed() ? "展开侧栏" : "收起侧栏")}><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" class="svelte-6dohdz">`);
    if (collapsed()) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<path d="M6 3l5 5-5 5" stroke-linecap="round" stroke-linejoin="round"></path>`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<path d="M10 3L5 8l5 5" stroke-linecap="round" stroke-linejoin="round"></path>`);
    }
    $$renderer2.push(`<!--]--></svg></button> `);
    if (showManageSidebar()) {
      $$renderer2.push("<!--[0-->");
      ManageSidebar($$renderer2);
    } else if (showSettingsSidebar()) {
      $$renderer2.push("<!--[1-->");
      SettingsSidebar($$renderer2);
    } else {
      $$renderer2.push("<!--[-1-->");
      MediaSidebar($$renderer2);
    }
    $$renderer2.push(`<!--]--> `);
    TagOverlays($$renderer2);
    $$renderer2.push(`<!----></aside>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
function TaskDrawer($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let now = Date.now();
    let expandedIds = [];
    const typeMeta = {
      scan: { label: "扫描" },
      thumbnail: { label: "缩略图" },
      metadata: { label: "元数据" },
      ai_tag: { label: "AI 打标" },
      subtitle: { label: "字幕" },
      hash: { label: "哈希" },
      scrape: { label: "刮削" }
    };
    function typeLabel(type) {
      return typeMeta[type]?.label ?? type;
    }
    function statusLabel(status) {
      switch (status) {
        case "pending":
          return "等待中";
        case "running":
          return "进行中";
        case "completed":
          return "已完成";
        case "failed":
          return "失败";
        case "cancelled":
          return "已取消";
        default:
          return status;
      }
    }
    function pct(task) {
      if (task.total > 0) return Math.min(100, Math.round(task.current / task.total * 100));
      if (task.progress) return Math.min(100, Math.round(task.progress));
      return 0;
    }
    function progressUnit(type) {
      switch (type) {
        case "scan":
          return "个文件";
        case "thumbnail":
          return "张缩略图";
        case "metadata":
          return "个文件";
        case "ai_tag":
          return "个媒体";
        case "scrape":
          return "个媒体";
        case "subtitle":
          return "条字幕";
        case "hash":
          return "个媒体";
        default:
          return "项";
      }
    }
    function progressText(task) {
      if (task.total > 0) {
        return `${task.current} / ${task.total} ${progressUnit(task.type)}`;
      }
      return "";
    }
    function activityPrefix(type) {
      switch (type) {
        case "scan":
          return "正在扫描";
        case "thumbnail":
          return "正在生成";
        case "metadata":
          return "正在提取";
        case "ai_tag":
          return "正在分析";
        case "scrape":
          return "正在刮削";
        case "subtitle":
          return "正在提取";
        case "hash":
          return "正在计算";
        default:
          return "正在处理";
      }
    }
    function scrapeSource(task) {
      if (task.type !== "scrape" || !task.message) return null;
      if (task.message.includes("JavBus")) return "JavBus";
      if (task.message.includes("TMDB")) return "TMDB";
      return null;
    }
    function activityText(task) {
      if (!task.message) return "";
      if (task.type === "scrape") {
        const idx = task.message.lastIndexOf(" · ");
        return idx > 0 ? task.message.slice(0, idx) : task.message;
      }
      return task.message;
    }
    function formatDuration(ms) {
      const s = Math.floor(ms / 1e3);
      if (s < 1) return "< 1 秒";
      if (s < 60) return `${s} 秒`;
      const m = Math.floor(s / 60);
      const rs = s % 60;
      if (m < 60) return rs > 0 ? `${m} 分 ${rs} 秒` : `${m} 分`;
      const h = Math.floor(m / 60);
      const rm = m % 60;
      return rm > 0 ? `${h} 时 ${rm} 分` : `${h} 时`;
    }
    function elapsed(task) {
      if (!task.started_at) return "";
      const start = new Date(task.started_at).getTime();
      if (Number.isNaN(start)) return "";
      const end = task.completed_at ? new Date(task.completed_at).getTime() : now;
      if (Number.isNaN(end)) return "";
      return formatDuration(Math.max(0, end - start));
    }
    function eta(task) {
      if (task.status !== "running") return "";
      const p = pct(task);
      if (p <= 0 || p >= 100 || !task.started_at) return "";
      const start = new Date(task.started_at).getTime();
      if (Number.isNaN(start)) return "";
      const elapsedMs = Math.max(0, now - start);
      const remainingMs = elapsedMs / p * (100 - p);
      return formatDuration(remainingMs);
    }
    function formatTime2(iso) {
      if (!iso) return "—";
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return "—";
      return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }
    function resultEntries(task) {
      if (!task.result || typeof task.result !== "object") return [];
      const labels = {
        new_count: "新增",
        processed_count: "已处理",
        generated_count: "已生成",
        tagged_count: "已打标",
        subtitle_count: "字幕",
        duplicate_pairs: "重复对",
        matched_count: "已匹配"
      };
      return Object.entries(task.result).filter(([, v]) => v !== null && v !== void 0).map(([k, v]) => ({
        key: labels[k] ?? k,
        value: typeof v === "object" ? JSON.stringify(v) : String(v)
      }));
    }
    function isExpanded(id) {
      return expandedIds.includes(id);
    }
    if (tasks.open) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="drawer svelte-15x7f8z"><div class="drawer-head svelte-15x7f8z"><div class="head-title svelte-15x7f8z">任务中心 `);
      if (tasks.count > 0) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="count-pill svelte-15x7f8z">${escape_html(tasks.count)}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div> <div class="head-actions svelte-15x7f8z"><button class="head-btn svelte-15x7f8z" title="刷新">↻</button> <button class="head-btn svelte-15x7f8z" title="关闭">×</button></div></div> <div class="drawer-body svelte-15x7f8z">`);
      if (tasks.items.length === 0) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="empty svelte-15x7f8z">暂无任务</div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<ul class="task-list svelte-15x7f8z"><!--[-->`);
        const each_array = ensure_array_like(tasks.items);
        for (let $$index_2 = 0, $$length = each_array.length; $$index_2 < $$length; $$index_2++) {
          let task = each_array[$$index_2];
          const p = pct(task);
          const expanded = isExpanded(task.id);
          $$renderer2.push(`<li class="task svelte-15x7f8z"${attr("data-status", task.status)}${attr("data-expanded", expanded)}><button class="task-head svelte-15x7f8z"${attr("aria-expanded", expanded)}><span class="task-icon svelte-15x7f8z"${attr("data-type", task.type)}><svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" class="svelte-15x7f8z">`);
          if (task.type === "scan") {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z" class="svelte-15x7f8z"></path>`);
          } else if (task.type === "thumbnail") {
            $$renderer2.push("<!--[1-->");
            $$renderer2.push(`<rect x="2" y="3" width="12" height="10" rx="1.5" class="svelte-15x7f8z"></rect><circle cx="5.5" cy="6.5" r="1" class="svelte-15x7f8z"></circle><path d="M2 11l3.5-3 3 2.5L10 9l4 3" stroke-opacity="0.5" class="svelte-15x7f8z"></path>`);
          } else if (task.type === "metadata") {
            $$renderer2.push("<!--[2-->");
            $$renderer2.push(`<circle cx="8" cy="8" r="6" class="svelte-15x7f8z"></circle><path d="M8 4.5V8l2.2 1.4" stroke-linecap="round" class="svelte-15x7f8z"></path>`);
          } else if (task.type === "ai_tag") {
            $$renderer2.push("<!--[3-->");
            $$renderer2.push(`<path d="M8 1.5l1.8 4.2 4.2.3-3.3 2.8 1.1 4.1L8 11l-3.8 2.3 1.1-4.1L2 6.5l4.2-.3L8 1.5z" stroke-linejoin="round" class="svelte-15x7f8z"></path>`);
          } else if (task.type === "subtitle") {
            $$renderer2.push("<!--[4-->");
            $$renderer2.push(`<rect x="2" y="3" width="12" height="10" rx="1.5" class="svelte-15x7f8z"></rect><path d="M4.5 11h2M9 11h2.5M4 8.5h3M9.5 8.5h2.5" stroke-linecap="round" class="svelte-15x7f8z"></path>`);
          } else if (task.type === "hash") {
            $$renderer2.push("<!--[5-->");
            $$renderer2.push(`<path d="M3 4h10M3 8h10M3 12h10" stroke-linecap="round" class="svelte-15x7f8z"></path><circle cx="5.5" cy="4" r="0.9" fill="currentColor" stroke="none" class="svelte-15x7f8z"></circle><circle cx="10" cy="8" r="0.9" fill="currentColor" stroke="none" class="svelte-15x7f8z"></circle><circle cx="6" cy="12" r="0.9" fill="currentColor" stroke="none" class="svelte-15x7f8z"></circle>`);
          } else if (task.type === "scrape") {
            $$renderer2.push("<!--[6-->");
            $$renderer2.push(`<circle cx="8" cy="8" r="5.5" class="svelte-15x7f8z"></circle><path d="M8 4.5v3.5M8 8l2.2 1.5" stroke-linecap="round" class="svelte-15x7f8z"></path><path d="M2.8 5.5l1.6.9M13.2 5.5l-1.6.9" stroke-opacity="0.6" class="svelte-15x7f8z"></path>`);
          } else {
            $$renderer2.push("<!--[-1-->");
            $$renderer2.push(`<circle cx="8" cy="8" r="6" class="svelte-15x7f8z"></circle><path d="M8 5v3.5M8 11h.01" stroke-linecap="round" class="svelte-15x7f8z"></path>`);
          }
          $$renderer2.push(`<!--]--></svg></span> <span class="task-type-badge svelte-15x7f8z">${escape_html(typeLabel(task.type))}</span> <div class="task-main svelte-15x7f8z"><div class="task-title svelte-15x7f8z"${attr("title", task.title)}>${escape_html(task.title || typeLabel(task.type))}</div> `);
          if (task.message && (task.status === "running" || task.status === "pending")) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<div class="task-activity svelte-15x7f8z"${attr("title", task.message)}><span class="activity-prefix svelte-15x7f8z">${escape_html(activityPrefix(task.type))}</span> <span class="activity-text svelte-15x7f8z">${escape_html(activityText(task))}</span> `);
            if (scrapeSource(task)) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="source-badge svelte-15x7f8z"${attr("data-source", scrapeSource(task))}>${escape_html(scrapeSource(task))}</span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></div>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--> <div class="task-sub svelte-15x7f8z"><span class="status-dot svelte-15x7f8z"${attr("data-status", task.status)}></span> ${escape_html(statusLabel(task.status))} `);
          if (progressText(task)) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`· ${escape_html(progressText(task))}`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--> `);
          if (p > 0) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`· ${escape_html(p)}%`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></div></div> <span class="chevron svelte-15x7f8z" aria-hidden="true">${escape_html(expanded ? "▾" : "▸")}</span></button> `);
          if (task.status === "running" || task.status === "pending") {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<div class="bar svelte-15x7f8z"><div class="bar-fill svelte-15x7f8z"${attr_style(`width:${stringify(p)}%`)}></div></div> <div class="task-meta svelte-15x7f8z">`);
            if (task.status === "running") {
              $$renderer2.push("<!--[0-->");
              if (elapsed(task)) {
                $$renderer2.push("<!--[0-->");
                $$renderer2.push(`<span class="svelte-15x7f8z">已用 ${escape_html(elapsed(task))}</span>`);
              } else {
                $$renderer2.push("<!--[-1-->");
              }
              $$renderer2.push(`<!--]--> `);
              if (eta(task)) {
                $$renderer2.push("<!--[0-->");
                $$renderer2.push(`<span class="meta-sep svelte-15x7f8z">·</span><span class="svelte-15x7f8z">预计剩余 ${escape_html(eta(task))}</span>`);
              } else {
                $$renderer2.push("<!--[-1-->");
              }
              $$renderer2.push(`<!--]-->`);
            } else {
              $$renderer2.push("<!--[-1-->");
              $$renderer2.push(`<span class="svelte-15x7f8z">创建于 ${escape_html(formatTime2(task.created_at))}</span> <span class="meta-sep svelte-15x7f8z">·</span><span class="meta-muted svelte-15x7f8z">排队等待中</span>`);
            }
            $$renderer2.push(`<!--]--></div>`);
          } else if (task.status === "completed") {
            $$renderer2.push("<!--[1-->");
            $$renderer2.push(`<div class="bar svelte-15x7f8z"><div class="bar-fill ok svelte-15x7f8z" style="width:100%"></div></div> <div class="task-meta svelte-15x7f8z">`);
            if (elapsed(task)) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="svelte-15x7f8z">用时 ${escape_html(elapsed(task))}</span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> `);
            if (resultEntries(task).length > 0) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<!--[-->`);
              const each_array_1 = ensure_array_like(resultEntries(task));
              for (let i = 0, $$length2 = each_array_1.length; i < $$length2; i++) {
                let r = each_array_1[i];
                if (i > 0 || elapsed(task)) {
                  $$renderer2.push("<!--[0-->");
                  $$renderer2.push(`<span class="meta-sep svelte-15x7f8z">·</span>`);
                } else {
                  $$renderer2.push("<!--[-1-->");
                }
                $$renderer2.push(`<!--]--> <span class="meta-ok svelte-15x7f8z">${escape_html(r.key)} ${escape_html(r.value)}</span>`);
              }
              $$renderer2.push(`<!--]-->`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></div>`);
          } else if (task.status === "failed") {
            $$renderer2.push("<!--[2-->");
            $$renderer2.push(`<div class="bar svelte-15x7f8z"><div class="bar-fill err svelte-15x7f8z" style="width:100%"></div></div> <div class="task-meta svelte-15x7f8z">`);
            if (elapsed(task)) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="svelte-15x7f8z">用时 ${escape_html(elapsed(task))}</span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></div> `);
            if (task.error) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="task-err svelte-15x7f8z"${attr("title", task.error)}>${escape_html(task.error)}</div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]-->`);
          } else if (task.status === "cancelled") {
            $$renderer2.push("<!--[3-->");
            $$renderer2.push(`<div class="bar svelte-15x7f8z"><div class="bar-fill cancelled svelte-15x7f8z"${attr_style(`width:${stringify(p)}%`)}></div></div> <div class="task-meta svelte-15x7f8z">`);
            if (elapsed(task)) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="svelte-15x7f8z">用时 ${escape_html(elapsed(task))}</span><span class="meta-sep svelte-15x7f8z">·</span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> <span class="meta-muted svelte-15x7f8z">已手动取消</span></div>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--> `);
          if (task.status === "pending" || task.status === "running") {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<button class="cancel svelte-15x7f8z">取消</button>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--> `);
          if (expanded) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<div class="task-details svelte-15x7f8z">`);
            if (task.message) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">当前处理</span> <span class="detail-value svelte-15x7f8z"${attr("title", task.message)}>${escape_html(task.message)}</span></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> <div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">进度</span> <span class="detail-value svelte-15x7f8z">`);
            if (task.total > 0) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`${escape_html(task.current)} / ${escape_html(task.total)} ${escape_html(progressUnit(task.type))} (${escape_html(p)}%)`);
            } else if (task.progress > 0) {
              $$renderer2.push("<!--[1-->");
              $$renderer2.push(`${escape_html(p)}%`);
            } else {
              $$renderer2.push("<!--[-1-->");
              $$renderer2.push(`—`);
            }
            $$renderer2.push(`<!--]--></span></div> `);
            if (task.library_id) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">媒体库</span> <span class="detail-value svelte-15x7f8z">ID ${escape_html(task.library_id)}</span></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> `);
            if (task.media_id) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">媒体</span> <span class="detail-value svelte-15x7f8z">ID ${escape_html(task.media_id)}</span></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> `);
            if (elapsed(task)) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">已用时</span> <span class="detail-value svelte-15x7f8z">${escape_html(elapsed(task))}`);
              if (task.status === "running" && eta(task)) {
                $$renderer2.push("<!--[0-->");
                $$renderer2.push(`· 预计剩余 ${escape_html(eta(task))}`);
              } else {
                $$renderer2.push("<!--[-1-->");
              }
              $$renderer2.push(`<!--]--></span></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> <div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">创建</span> <span class="detail-value svelte-15x7f8z">${escape_html(formatTime2(task.created_at))}</span></div> `);
            if (task.started_at) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">开始</span> <span class="detail-value svelte-15x7f8z">${escape_html(formatTime2(task.started_at))}</span></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> `);
            if (task.completed_at) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">完成</span> <span class="detail-value svelte-15x7f8z">${escape_html(formatTime2(task.completed_at))}</span></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> `);
            if (task.error) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="detail-row detail-err svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">错误详情</span> <span class="detail-value svelte-15x7f8z">${escape_html(task.error)}</span></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> `);
            if (resultEntries(task).length > 0) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<div class="detail-row svelte-15x7f8z"><span class="detail-label svelte-15x7f8z">结果</span> <span class="detail-value svelte-15x7f8z"><!--[-->`);
              const each_array_2 = ensure_array_like(resultEntries(task));
              for (let i = 0, $$length2 = each_array_2.length; i < $$length2; i++) {
                let r = each_array_2[i];
                if (i > 0) {
                  $$renderer2.push("<!--[0-->");
                  $$renderer2.push(`，`);
                } else {
                  $$renderer2.push("<!--[-1-->");
                }
                $$renderer2.push(`<!--]-->${escape_html(r.key)} ${escape_html(r.value)}`);
              }
              $$renderer2.push(`<!--]--></span></div>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></div>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></li>`);
        }
        $$renderer2.push(`<!--]--></ul>`);
      }
      $$renderer2.push(`<!--]--></div></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
function SearchModal($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { open = false, onClose } = $$props;
    let query = "";
    let results = [];
    let activeIndex = 0;
    const hasQuery = derived(() => query.trim().length > 0);
    function select(media) {
      goto(`/detail/${media.id}`);
      onClose?.();
    }
    function handleKeydown(e) {
      if (!open) return;
      if (e.key === "Escape") {
        onClose?.();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, results.length - 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
      } else if (e.key === "Enter" && results[activeIndex]) {
        e.preventDefault();
        select(results[activeIndex]);
      }
    }
    onDestroy(() => {
      window.removeEventListener("keydown", handleKeydown);
    });
    if (open) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="overlay svelte-kdzbas" role="presentation"><div class="modal svelte-kdzbas" role="dialog" aria-modal="true" tabindex="-1"><div class="modal-head svelte-kdzbas"><svg class="search-ico svelte-kdzbas" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="7" cy="7" r="5"></circle><line x1="10.5" y1="10.5" x2="14" y2="14" stroke-linecap="round"></line></svg> <input${attr("value", query)} class="modal-input svelte-kdzbas" placeholder="搜索媒体" autocomplete="off" spellcheck="false"/> <button class="esc svelte-kdzbas">ESC</button></div> <div class="modal-body svelte-kdzbas">`);
      if (hasQuery() && results.length === 0) {
        $$renderer2.push("<!--[1-->");
        $$renderer2.push(`<div class="empty svelte-kdzbas">没有找到匹配的媒体</div>`);
      } else if (!hasQuery()) {
        $$renderer2.push("<!--[2-->");
        $$renderer2.push(`<div class="empty svelte-kdzbas">输入关键词以搜索媒体</div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<ul class="result-list svelte-kdzbas"><!--[-->`);
        const each_array = ensure_array_like(results);
        for (let i = 0, $$length = each_array.length; i < $$length; i++) {
          let media = each_array[i];
          $$renderer2.push(`<li><button${attr_class("result svelte-kdzbas", void 0, { "active": i === activeIndex })}><div class="thumb svelte-kdzbas">`);
          if (media.thumbnail) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<img${attr("src", mediaApi.thumbnailUrl(media.id, media.updated_at))} alt="" loading="lazy" class="svelte-kdzbas"/>`);
          } else {
            $$renderer2.push("<!--[-1-->");
            $$renderer2.push(`<span class="thumb-fallback">${escape_html(media.type === "video" ? "▶" : media.type === "audio" ? "♪" : "▣")}</span>`);
          }
          $$renderer2.push(`<!--]--></div> <div class="info svelte-kdzbas"><div class="title svelte-kdzbas">${escape_html(media.filename)}</div> <div class="meta svelte-kdzbas"><span>${escape_html(media.type)}</span> `);
          if (media.duration) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span>· ${escape_html(formatTime(media.duration))}</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--> `);
          if (media.rating > 0) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span>· ★ ${escape_html(media.rating)}</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></div></div></button></li>`);
        }
        $$renderer2.push(`<!--]--></ul>`);
      }
      $$renderer2.push(`<!--]--></div> <div class="modal-foot svelte-kdzbas"><span><kbd class="svelte-kdzbas">↑</kbd><kbd class="svelte-kdzbas">↓</kbd> 导航</span> <span><kbd class="svelte-kdzbas">↵</kbd> 打开</span> <span><kbd class="svelte-kdzbas">ESC</kbd> 关闭</span></div></div></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
    bind_props($$props, { open });
  });
}
function AppShell($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { children } = $$props;
    let searchOpen = false;
    let isTauri = false;
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      isTauri = true;
    }
    function closeSearch() {
      searchOpen = false;
    }
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      $$renderer3.push(`<div class="app-shell svelte-vr1z90">`);
      TopNav($$renderer3);
      $$renderer3.push(`<!----> <div class="app-body svelte-vr1z90">`);
      Sidebar($$renderer3);
      $$renderer3.push(`<!----> <main class="app-main svelte-vr1z90">`);
      children($$renderer3);
      $$renderer3.push(`<!----></main></div> `);
      TaskDrawer($$renderer3);
      $$renderer3.push(`<!----> `);
      SearchModal($$renderer3, {
        onClose: closeSearch,
        get open() {
          return searchOpen;
        },
        set open($$value) {
          searchOpen = $$value;
          $$settled = false;
        }
      });
      $$renderer3.push(`<!----></div> `);
      if (isTauri) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div class="resize-handles svelte-vr1z90" aria-hidden="true"><div class="rh rh-n svelte-vr1z90"></div> <div class="rh rh-s svelte-vr1z90"></div> <div class="rh rh-w svelte-vr1z90"></div> <div class="rh rh-e svelte-vr1z90"></div> <div class="rh rh-nw svelte-vr1z90"></div> <div class="rh rh-ne svelte-vr1z90"></div> <div class="rh rh-sw svelte-vr1z90"></div> <div class="rh rh-se svelte-vr1z90"></div></div>`);
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
function _layout($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { children } = $$props;
    AppShell($$renderer2, {
      children: ($$renderer3) => {
        children($$renderer3);
        $$renderer3.push(`<!---->`);
      }
    });
    $$renderer2.push(`<!----> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
export {
  _layout as default
};
