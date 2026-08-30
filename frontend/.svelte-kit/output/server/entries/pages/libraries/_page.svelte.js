import { k as head, e as escape_html, f as ensure_array_like, h as attr_style, c as attr, a as attr_class, d as derived } from "../../../chunks/index.js";
import "@sveltejs/kit/internal";
import "../../../chunks/exports.js";
import "../../../chunks/utils2.js";
import "@sveltejs/kit/internal/server";
import "../../../chunks/root.js";
import "../../../chunks/state.svelte.js";
import "../../../chunks/client2.js";
import { a as formatNumber } from "../../../chunks/format.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let libraries = [];
    let scanningIds = /* @__PURE__ */ new Set();
    const scrapeLabels = { none: "不刮削", movie: "电影", tv: "电视剧", av: "AV", custom: "自定义" };
    const typeLabels = { video: "视频", audio: "音频", document: "文档" };
    const totalMedia = derived(() => libraries.reduce((s, l) => s + (l.media_count ?? 0), 0));
    const safeColor = (c) => /^#[0-9a-fA-F]{6}$/.test(c ?? "") ? c : "";
    head("1fy8wck", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>资源库 — vitoice</title>`);
      });
    });
    $$renderer2.push(`<div class="lib-page svelte-1fy8wck"><div class="page-head svelte-1fy8wck"><div class="head-left svelte-1fy8wck"><h1 class="svelte-1fy8wck">资源库</h1> <p class="svelte-1fy8wck">管理所有媒体资源库的扫描、刮削与监控配置。</p></div> <div class="head-right svelte-1fy8wck"><div class="stat-pill svelte-1fy8wck"><span class="stat-num svelte-1fy8wck">${escape_html(formatNumber(libraries.length))}</span> <span class="stat-label svelte-1fy8wck">个库</span></div> <div class="stat-pill svelte-1fy8wck"><span class="stat-num svelte-1fy8wck">${escape_html(formatNumber(totalMedia()))}</span> <span class="stat-label svelte-1fy8wck">个媒体</span></div> <button class="btn primary svelte-1fy8wck">+ 新建库</button></div></div> `);
    if (libraries.length === 0) {
      $$renderer2.push("<!--[2-->");
      $$renderer2.push(`<div class="empty-state svelte-1fy8wck"><div class="empty-icon svelte-1fy8wck">📂</div> <h2 class="svelte-1fy8wck">还没有资源库</h2> <p class="svelte-1fy8wck">创建第一个资源库，开始导入和管理你的媒体文件。</p> <button class="btn primary svelte-1fy8wck">前往导入向导</button></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="lib-table svelte-1fy8wck"><div class="table-head svelte-1fy8wck"><div class="col-name svelte-1fy8wck">名称</div> <div class="col-path svelte-1fy8wck">路径</div> <div class="col-type">类型</div> <div class="col-scrape">刮削模式</div> <div class="col-watch">监控</div> <div class="col-count">媒体数</div> <div class="col-actions svelte-1fy8wck">操作</div></div> <!--[-->`);
      const each_array = ensure_array_like(libraries);
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let lib = each_array[$$index];
        $$renderer2.push(`<div class="table-row svelte-1fy8wck"><div class="col-name svelte-1fy8wck"><span class="lib-dot svelte-1fy8wck"${attr_style(`background:${safeColor(lib.color) || "var(--accent)"}`)}></span> <span class="lib-name svelte-1fy8wck">${escape_html(lib.name)}</span> `);
        if (lib.is_restricted) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="restricted-tag svelte-1fy8wck" title="限制内容库">18+</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div> <div class="col-path svelte-1fy8wck"${attr("title", lib.root_path)}><span class="path-text svelte-1fy8wck">${escape_html(lib.root_path)}</span></div> <div class="col-type"><span class="badge svelte-1fy8wck">${escape_html(typeLabels[lib.type] ?? lib.type)}</span></div> <div class="col-scrape"><span class="scrape-tag svelte-1fy8wck">${escape_html(scrapeLabels[lib.scrape_mode] ?? lib.scrape_mode)}</span></div> <div class="col-watch"><span${attr_class("watch-pill svelte-1fy8wck", void 0, { "on": lib.watch_enabled })}>${escape_html(lib.watch_enabled ? "已启用" : "未启用")}</span></div> <div class="col-count"><span class="count-num svelte-1fy8wck">${escape_html(formatNumber(lib.media_count ?? 0))}</span></div> <div class="col-actions svelte-1fy8wck"><button class="action-btn edit svelte-1fy8wck" title="编辑">编辑</button> <button class="action-btn scan svelte-1fy8wck" title="扫描"${attr("disabled", scanningIds.has(lib.id), true)}>${escape_html(scanningIds.has(lib.id) ? "扫描中…" : "扫描")}</button> <button class="action-btn danger svelte-1fy8wck" title="删除">删除</button></div></div>`);
      }
      $$renderer2.push(`<!--]--></div> <div class="page-foot svelte-1fy8wck"><div class="foot-note svelte-1fy8wck"><strong class="svelte-1fy8wck">说明：</strong>删除资源库仅会从软件记录中移除该库及其媒体索引，<u class="svelte-1fy8wck">不会删除磁盘上的实际文件</u>。
        删除时可选择是否同时清理因此变空的标签（内置标签不会被删除）。</div></div>`);
    }
    $$renderer2.push(`<!--]--></div> `);
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
  });
}
export {
  _page as default
};
