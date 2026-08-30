import { k as head, e as escape_html, f as ensure_array_like, h as attr_style, c as attr } from "../../../chunks/index.js";
import "../../../chunks/client2.js";
import { a as formatNumber } from "../../../chunks/format.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const DIMENSIONS = {
      tag: {
        label: "标签",
        operators: ["has", "not_has", "has_any", "has_all"],
        valueType: "tag"
      },
      rating: {
        label: "评分",
        operators: ["gte", "lte", "eq", "is_null"],
        valueType: "rating"
      },
      favorite: { label: "收藏", operators: ["eq"], valueType: "bool" },
      media_type: { label: "来源类型", operators: ["eq"], valueType: "media_type" },
      year: {
        label: "年份",
        operators: ["gte", "lte", "eq", "between", "is_null"],
        valueType: "number",
        unit: "年"
      },
      duration: {
        label: "时长",
        operators: ["gt", "lt", "gte", "lte", "eq", "between"],
        valueType: "number",
        unit: "秒"
      },
      resolution: {
        label: "分辨率",
        operators: ["gte", "lte", "eq"],
        valueType: "resolution"
      },
      file_size: {
        label: "文件大小",
        operators: ["gt", "lt", "gte", "lte"],
        valueType: "number",
        unit: "MB"
      },
      library: { label: "资源库", operators: ["eq", "in"], valueType: "library" },
      season: {
        label: "季数",
        operators: ["eq", "gte", "lte", "is_null"],
        valueType: "number"
      },
      episode: {
        label: "集数",
        operators: ["eq", "gte", "lte", "is_null"],
        valueType: "number"
      },
      playback: {
        label: "播放进度",
        operators: ["gt", "is_null"],
        valueType: "number",
        unit: "秒"
      },
      watched: { label: "已看状态", operators: ["eq"], valueType: "bool" },
      missing: { label: "本地缺失", operators: ["eq"], valueType: "bool" },
      recent: {
        label: "添加时间(近N天)",
        operators: ["lte"],
        valueType: "number",
        unit: "天"
      },
      no_tag: { label: "未分类", operators: ["eq"], valueType: "bool" }
    };
    const OPERATOR_LABELS = {
      gt: "大于 >",
      lt: "小于 <",
      gte: "大于等于 ≥",
      lte: "小于等于 ≤",
      eq: "等于 =",
      between: "介于",
      has: "包含",
      not_has: "不包含",
      has_any: "包含任一",
      has_all: "包含全部",
      is_null: "为空",
      in: "属于"
    };
    const RESOLUTION_OPTIONS = [
      { value: 360, label: "360p" },
      { value: 480, label: "480p" },
      { value: 720, label: "720p" },
      { value: 1080, label: "1080p" },
      { value: 1440, label: "1440p" },
      { value: 2160, label: "4K (2160p)" },
      { value: 4320, label: "8K (4320p)" }
    ];
    const MEDIA_TYPE_LABELS = { local: "本地", network: "网络", both: "本地+网络" };
    let folders = [];
    let tags = [];
    let libraries = [];
    function tagName(id) {
      return tags.find((t) => t.id === id)?.name ?? `标签#${id}`;
    }
    function libName(id) {
      return libraries.find((l) => l.id === id)?.name ?? `库#${id}`;
    }
    function safeColor(c) {
      return /^#[0-9a-fA-F]{6}$/.test(c ?? "") ? c : "";
    }
    function describeRule(rule) {
      if (!rule || !rule.children || rule.children.length === 0) {
        return "匹配所有媒体";
      }
      const parts = rule.children.map((child) => {
        if (child.type === "group") {
          return `(${describeRule(child)})`;
        }
        return describeCondition(child);
      });
      const logic = rule.logic === "and" ? " 且 " : " 或 ";
      return parts.join(logic);
    }
    function describeCondition(cond) {
      const dim = DIMENSIONS[cond.dimension];
      const dimLabel = dim?.label ?? cond.dimension;
      if (cond.operator === "is_null") {
        return `${dimLabel} ${cond.value ? "为空" : "不为空"}`;
      }
      const opLabel = OPERATOR_LABELS[cond.operator] ?? cond.operator;
      let valueStr = "";
      if (cond.dimension === "tag") {
        if (Array.isArray(cond.value)) {
          valueStr = cond.value.map((v) => tagName(Number(v))).join(", ");
        } else {
          valueStr = tagName(Number(cond.value));
        }
      } else if (cond.dimension === "library") {
        if (Array.isArray(cond.value)) {
          valueStr = cond.value.map((v) => libName(Number(v))).join(", ");
        } else {
          valueStr = libName(Number(cond.value));
        }
      } else if (cond.dimension === "favorite") {
        valueStr = cond.value ? "是" : "否";
      } else if (cond.dimension === "watched" || cond.dimension === "missing" || cond.dimension === "no_tag") {
        valueStr = cond.value ? "是" : "否";
      } else if (cond.dimension === "media_type") {
        valueStr = MEDIA_TYPE_LABELS[String(cond.value)] ?? String(cond.value);
      } else if (cond.dimension === "rating") {
        const r = typeof cond.value === "number" ? cond.value : 0;
        valueStr = `${"★".repeat(r)} (${r})`;
      } else if (cond.dimension === "resolution") {
        const opt = RESOLUTION_OPTIONS.find((o) => o.value === Number(cond.value));
        valueStr = opt?.label ?? String(cond.value);
      } else if (cond.operator === "between" && Array.isArray(cond.value)) {
        valueStr = `${cond.value[0]} ~ ${cond.value[1]}`;
        if (dim?.unit) valueStr += ` ${dim.unit}`;
      } else {
        valueStr = String(cond.value);
        if (dim?.unit) valueStr += ` ${dim.unit}`;
      }
      return `${dimLabel} ${opLabel} ${valueStr}`;
    }
    head("kipfaa", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>智能文件夹 — vitoice</title>`);
      });
    });
    $$renderer2.push(`<div class="sf-page svelte-kipfaa"><div class="page-head svelte-kipfaa"><div class="head-left svelte-kipfaa"><h1 class="svelte-kipfaa">智能文件夹</h1> <p class="svelte-kipfaa">通过规则自动组织媒体，创建动态虚拟文件夹。</p></div> <div class="head-right svelte-kipfaa"><div class="stat-pill svelte-kipfaa"><span class="stat-num svelte-kipfaa">${escape_html(formatNumber(folders.length))}</span> <span class="stat-label svelte-kipfaa">个文件夹</span></div> <button class="btn primary svelte-kipfaa">+ 新建文件夹</button></div></div> `);
    if (folders.length === 0) {
      $$renderer2.push("<!--[2-->");
      $$renderer2.push(`<div class="empty-state svelte-kipfaa"><div class="empty-icon svelte-kipfaa">📁</div> <h2 class="svelte-kipfaa">还没有智能文件夹</h2> <p class="svelte-kipfaa">创建一个智能文件夹，通过标签、评分、类型等条件自动筛选媒体。</p> <button class="btn primary svelte-kipfaa">新建智能文件夹</button></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="sf-grid svelte-kipfaa"><!--[-->`);
      const each_array = ensure_array_like(folders);
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let f = each_array[$$index];
        $$renderer2.push(`<div class="sf-card svelte-kipfaa"${attr_style(`--card-color:${safeColor(f.color) || "var(--accent)"}`)}><div class="card-color-bar svelte-kipfaa"></div> <div class="card-body svelte-kipfaa"><div class="card-head svelte-kipfaa"><span class="card-dot svelte-kipfaa"></span> <h3 class="card-name svelte-kipfaa"${attr("title", f.name)}>${escape_html(f.name)}</h3></div> <p class="card-desc svelte-kipfaa"${attr("title", describeRule(f.rule_json))}>${escape_html(describeRule(f.rule_json))}</p> <div class="card-foot svelte-kipfaa"><span class="card-count svelte-kipfaa"><span class="count-num svelte-kipfaa">${escape_html(formatNumber(f.preview_count))}</span> <span class="count-label svelte-kipfaa">个媒体</span></span> <div class="card-actions svelte-kipfaa"><button class="action-btn preview svelte-kipfaa" title="预览匹配媒体">预览</button> `);
        if (!f.is_system) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<button class="action-btn edit svelte-kipfaa" title="编辑">编辑</button> <button class="action-btn danger svelte-kipfaa" title="删除">删除</button>`);
        } else {
          $$renderer2.push("<!--[-1-->");
          $$renderer2.push(`<span class="system-badge svelte-kipfaa" title="系统预置文件夹">系统</span>`);
        }
        $$renderer2.push(`<!--]--></div></div></div></div>`);
      }
      $$renderer2.push(`<!--]--></div>`);
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
