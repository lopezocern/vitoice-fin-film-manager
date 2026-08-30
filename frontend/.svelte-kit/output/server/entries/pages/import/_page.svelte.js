import { k as head, f as ensure_array_like, a as attr_class, e as escape_html, c as attr, d as derived } from "../../../chunks/index.js";
import "@sveltejs/kit/internal";
import "../../../chunks/exports.js";
import "../../../chunks/utils2.js";
import "@sveltejs/kit/internal/server";
import "../../../chunks/root.js";
import "../../../chunks/state.svelte.js";
import "../../../chunks/client2.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let step = 0;
    let creating = false;
    let transitioning = false;
    let libName = "";
    let libPath = "";
    let scrapeMode = "none";
    let watchEnabled = true;
    let isRestricted = false;
    let picking = false;
    const steps = [
      { label: "创建库" },
      { label: "扫描" },
      { label: "缩略图" },
      { label: "完成" }
    ];
    const scrapeOptions = [
      { value: "none", label: "不刮削", desc: "仅扫描文件，不获取元数据" },
      { value: "movie", label: "电影", desc: "按电影规则刮削元数据" },
      { value: "tv", label: "电视剧", desc: "按剧集规则刮削元数据" },
      { value: "av", label: "AV", desc: "按 AV 规则刮削元数据" },
      { value: "custom", label: "自定义", desc: "使用自定义刮削规则" }
    ];
    const canProceedStep0 = derived(() => libName.trim().length > 0 && libPath.trim().length > 0);
    head("1kumcmu", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>导入向导 — vitoice</title>`);
      });
    });
    $$renderer2.push(`<div class="wizard-page svelte-1kumcmu"><div class="wizard-card svelte-1kumcmu"><div class="stepper svelte-1kumcmu"><!--[-->`);
    const each_array = ensure_array_like(steps);
    for (let i = 0, $$length = each_array.length; i < $$length; i++) {
      let s = each_array[i];
      $$renderer2.push(`<div${attr_class("step svelte-1kumcmu", void 0, { "done": i < step, "active": i === step })}><div class="dot svelte-1kumcmu">`);
      if (i < step) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<svg viewBox="0 0 24 24" width="14" height="14" class="svelte-1kumcmu"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill="currentColor" class="svelte-1kumcmu"></path></svg>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<span class="svelte-1kumcmu">${escape_html(i + 1)}</span>`);
      }
      $$renderer2.push(`<!--]--></div> <span class="step-label svelte-1kumcmu">${escape_html(s.label)}</span></div> `);
      if (i < steps.length - 1) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div${attr_class("step-line svelte-1kumcmu", void 0, { "done": i < step })}></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></div> <div class="step-body svelte-1kumcmu">`);
    {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="step-content svelte-1kumcmu"><div class="welcome svelte-1kumcmu"><h1 class="svelte-1kumcmu">欢迎使用 vitoice</h1> <p class="svelte-1kumcmu">让我们创建第一个资源库，开始管理你的媒体文件。</p></div> <div class="form-group svelte-1kumcmu"><label for="lib-name" class="svelte-1kumcmu">库名称</label> <input id="lib-name" type="text" placeholder="例如：我的视频库"${attr("value", libName)} class="svelte-1kumcmu"/></div> <div class="form-group svelte-1kumcmu"><label for="lib-path" class="svelte-1kumcmu">目录路径</label> <div class="path-row svelte-1kumcmu"><input id="lib-path" type="text" placeholder="选择或输入目录路径"${attr("value", libPath)} class="svelte-1kumcmu"/> <button class="pick-btn svelte-1kumcmu"${attr("disabled", picking, true)}>${escape_html("浏览…")}</button></div> <span class="hint svelte-1kumcmu">vitoice 将扫描该目录下的所有媒体文件</span></div> <div class="form-group svelte-1kumcmu"><span class="field-label svelte-1kumcmu">刮削模式</span> <div class="scrape-grid svelte-1kumcmu"><!--[-->`);
      const each_array_1 = ensure_array_like(scrapeOptions);
      for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
        let o = each_array_1[$$index_1];
        $$renderer2.push(`<button type="button"${attr_class("scrape-card svelte-1kumcmu", void 0, { "active": scrapeMode === o.value })}><span class="scrape-label svelte-1kumcmu">${escape_html(o.label)}</span> <span class="scrape-desc svelte-1kumcmu">${escape_html(o.desc)}</span></button>`);
      }
      $$renderer2.push(`<!--]--></div></div> <div class="form-group toggle-row svelte-1kumcmu"><div class="toggle-info svelte-1kumcmu"><span class="toggle-label svelte-1kumcmu">启用文件监控</span> <span class="hint svelte-1kumcmu">目录变化时自动更新媒体记录</span></div> <button type="button"${attr_class("toggle svelte-1kumcmu", void 0, { "on": watchEnabled })} role="switch"${attr("aria-checked", watchEnabled)}><span class="knob svelte-1kumcmu"></span></button></div> <div class="form-group toggle-row svelte-1kumcmu"><div class="toggle-info svelte-1kumcmu"><span class="toggle-label svelte-1kumcmu">限制内容</span> <span class="hint svelte-1kumcmu">标记为限制的库在「显示限制内容」关闭时隐藏（选择 AV 模式时自动开启）</span></div> <button type="button"${attr_class("toggle svelte-1kumcmu", void 0, { "on": isRestricted })} role="switch"${attr("aria-checked", isRestricted)}><span class="knob svelte-1kumcmu"></span></button></div> `);
      {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div>`);
    }
    $$renderer2.push(`<!--]--></div> <div class="wizard-foot svelte-1kumcmu">`);
    {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<span class="svelte-1kumcmu"></span> <button class="btn btn-primary svelte-1kumcmu"${attr("disabled", !canProceedStep0() || creating || transitioning, true)}>${escape_html("下一步")}</button>`);
    }
    $$renderer2.push(`<!--]--></div></div></div> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
export {
  _page as default
};
