import { k as head, e as escape_html, f as ensure_array_like, c as attr, a as attr_class, d as derived } from "../../../chunks/index.js";
import { o as onDestroy } from "../../../chunks/index-server.js";
import "@sveltejs/kit/internal";
import "../../../chunks/exports.js";
import "../../../chunks/utils2.js";
import "@sveltejs/kit/internal/server";
import "../../../chunks/root.js";
import "../../../chunks/state.svelte.js";
import { c as client } from "../../../chunks/client2.js";
import { s as settingsStore } from "../../../chunks/settings.svelte.js";
function eyeIcon($$renderer) {
  $$renderer.push(`<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="svelte-1i19ct2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"></path><circle cx="12" cy="12" r="3"></circle></svg>`);
}
function eyeOffIcon($$renderer) {
  $$renderer.push(`<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="svelte-1i19ct2"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"></path><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"></path><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"></path><line x1="2" y1="2" x2="22" y2="22"></line></svg>`);
}
function folderIcon($$renderer) {
  $$renderer.push(`<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="svelte-1i19ct2"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2z"></path></svg>`);
}
function testResultDisplay($$renderer, result) {
  $$renderer.push(`<div${attr_class("test-result svelte-1i19ct2", void 0, { "ok": result.ok, "fail": !result.ok })}><span class="test-symbol svelte-1i19ct2">${escape_html(result.ok ? "✓" : "✗")}</span> <span class="test-text svelte-1i19ct2">${escape_html(result.msg)}</span></div>`);
}
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const categories = [
      { id: "appearance", label: "外观" },
      { id: "content", label: "内容管理" },
      { id: "tools", label: "外部工具" },
      { id: "thumbnail", label: "缩略图" },
      { id: "ai", label: "AI 配置" },
      { id: "scrape", label: "刮削" },
      { id: "player", label: "播放器" },
      { id: "subtitle", label: "字幕" },
      { id: "database", label: "数据库" },
      { id: "about", label: "关于" }
    ];
    const schema = [
      // 外观
      {
        key: "theme",
        category: "appearance",
        label: "主题",
        type: "select",
        default: "system",
        options: [
          { value: "light", label: "浅色" },
          { value: "dark", label: "深色" },
          { value: "system", label: "跟随系统" }
        ],
        description: "应用界面主题"
      },
      {
        key: "language",
        category: "appearance",
        label: "语言",
        type: "select",
        default: "zh-CN",
        options: [
          { value: "zh-CN", label: "中文" },
          { value: "en", label: "英文" }
        ],
        description: "界面显示语言"
      },
      // 内容管理
      {
        key: "show_restricted",
        category: "content",
        label: "显示限制内容",
        type: "toggle",
        default: "false",
        description: "打开后显示标记为限制的媒体库（如 AV/成人内容）。关闭时这些库及其媒体、标签在所有页面隐藏。"
      },
      {
        key: "mask_restricted",
        category: "content",
        label: "遮罩限制内容",
        type: "toggle",
        default: "false",
        description: '仅在"显示限制内容"开启时生效。对限制内容的海报和播放画面应用模糊遮罩，避免预览时直接展示。'
      },
      {
        key: "network_allow_adult",
        category: "content",
        label: "允许成人网络源解析",
        type: "toggle",
        default: "false",
        description: '开启后可在网络媒体导入中解析成人聚合站（javgg）的播放源。javgg 存在间歇性访问限制（403 频率限制），遇到时等 1-2 分钟重试即可；3 小时缓存内同一番号不会再请求聚合站。仅在"显示限制内容"开启时显示。'
      },
      {
        key: "network_adult_base_url",
        category: "content",
        label: "成人聚合站地址",
        type: "text",
        default: "https://javgg.net",
        description: '成人网络源的聚合站根地址（此类域名更换频繁，可在此修改）。仅在"显示限制内容"开启时显示。'
      },
      // 外部工具
      {
        key: "ffmpeg_path",
        category: "tools",
        label: "FFmpeg 路径",
        type: "text",
        default: "",
        testable: true,
        pickable: true,
        description: "视频转码与缩略图生成依赖"
      },
      {
        key: "ffprobe_path",
        category: "tools",
        label: "FFprobe 路径",
        type: "text",
        default: "",
        testable: true,
        pickable: true,
        description: "媒体元数据探测依赖"
      },
      {
        key: "ytdlp_path",
        category: "tools",
        label: "yt-dlp 路径",
        type: "text",
        default: "",
        testable: true,
        pickable: true,
        description: "网络资源下载依赖"
      },
      {
        key: "proxy_enabled",
        category: "tools",
        label: "启用 HTTP 代理",
        type: "toggle",
        default: "false",
        description: "所有外部请求（TMDB 刮削、AV 源、聚合站解析、AI 打标、网络流代理）通过代理访问。关闭为直连。"
      },
      {
        key: "proxy_host",
        category: "tools",
        label: "代理地址",
        type: "text",
        default: "",
        testable: true,
        description: "代理主机 IP 或域名（如 127.0.0.1）"
      },
      {
        key: "proxy_port",
        category: "tools",
        label: "代理端口",
        type: "text",
        default: "7890",
        description: "代理端口（如 7890）"
      },
      // 缩略图
      {
        key: "thumbnail_size",
        category: "thumbnail",
        label: "缩略图尺寸",
        type: "range",
        default: "320",
        min: 160,
        max: 640,
        step: 20,
        unit: "px",
        description: "缩略图宽度（像素）"
      },
      {
        key: "thumbnail_quality",
        category: "thumbnail",
        label: "缩略图质量",
        type: "range",
        default: "85",
        min: 50,
        max: 100,
        step: 1,
        unit: "%",
        description: "JPEG 压缩质量"
      },
      {
        key: "thumbnail_offset",
        category: "thumbnail",
        label: "时间偏移",
        type: "number",
        default: "10",
        min: 0,
        max: 600,
        step: 1,
        unit: "秒",
        description: "从视频第几秒截取缩略图"
      },
      {
        key: "thumbnail_smart_frame",
        category: "thumbnail",
        label: "智能选帧",
        type: "toggle",
        default: "true",
        description: "自动跳过黑屏/纯色帧，从多个时间点选择有效画面作为封面"
      },
      // AI 配置
      {
        key: "ai_base_url",
        category: "ai",
        label: "API 地址",
        type: "text",
        default: "https://api.openai.com/v1",
        description: "OpenAI 兼容接口地址，需以 /v1 结尾"
      },
      {
        key: "ai_api_key",
        category: "ai",
        label: "API Token",
        type: "password",
        default: "",
        description: "API 访问令牌，本地存储不上传"
      },
      {
        key: "ai_model",
        category: "ai",
        label: "模型名称",
        type: "text",
        default: "gpt-4o-mini",
        description: "如 gpt-4o-mini、deepseek-chat、moonshot-v1-8k"
      },
      {
        key: "ai_auto_tag",
        category: "ai",
        label: "导入时自动打标",
        type: "toggle",
        default: "false",
        description: "扫描完成后自动调用 AI 生成标签"
      },
      // 刮削（TMDB 元数据：标题 / 年份 / 简介 / 海报）
      {
        key: "tmdb_api_key",
        category: "scrape",
        label: "TMDB API Key",
        type: "password",
        default: "",
        description: "The Movie Database 密钥，支持 v3 Key 或 v4 读取令牌（eyJ 开头），本地存储不上传"
      },
      {
        key: "tmdb_language",
        category: "scrape",
        label: "刮削语言",
        type: "select",
        default: "zh-CN",
        options: [
          { value: "zh-CN", label: "简体中文" },
          { value: "zh-TW", label: "繁体中文" },
          { value: "en-US", label: "English" },
          { value: "ja-JP", label: "日本語" }
        ],
        description: "标题与简介的返回语言"
      },
      {
        key: "tmdb_base_url",
        category: "scrape",
        label: "API Base URL",
        type: "text",
        default: "",
        description: "留空使用默认 https://api.themoviedb.org/3，可填反代地址以改善连通性"
      },
      // 播放器
      {
        key: "step_size",
        category: "player",
        label: "步长",
        type: "number",
        default: "5",
        min: 1,
        max: 60,
        step: 1,
        unit: "",
        description: "快进/快退的步长数值"
      },
      {
        key: "step_unit",
        category: "player",
        label: "步长单位",
        type: "select",
        default: "seconds",
        options: [
          { value: "seconds", label: "秒" },
          { value: "frames", label: "帧" }
        ],
        description: "步长按时间或帧数计算"
      },
      // 字幕
      {
        key: "subtitle_font_size",
        category: "subtitle",
        label: "字体大小",
        type: "number",
        default: "16",
        min: 12,
        max: 48,
        step: 1,
        unit: "px",
        description: "字幕字体大小"
      },
      {
        key: "subtitle_color",
        category: "subtitle",
        label: "颜色",
        type: "color",
        default: "#FFFFFF",
        description: "字幕文字颜色"
      },
      {
        key: "subtitle_stroke",
        category: "subtitle",
        label: "描边宽度",
        type: "number",
        default: "2",
        min: 0,
        max: 6,
        step: 0.5,
        unit: "px",
        description: "字幕描边宽度"
      },
      {
        key: "subtitle_bg_opacity",
        category: "subtitle",
        label: "背景透明度",
        type: "range",
        default: "0.5",
        min: 0,
        max: 1,
        step: 0.05,
        unit: "",
        description: "字幕背景不透明度（0=透明，1=完全不透明）"
      },
      {
        key: "subtitle_position",
        category: "subtitle",
        label: "位置",
        type: "select",
        default: "bottom",
        options: [
          { value: "top", label: "顶部" },
          { value: "center", label: "居中" },
          { value: "bottom", label: "底部" }
        ],
        description: "字幕显示位置"
      },
      // 数据库
      {
        key: "db_path",
        category: "database",
        label: "数据库路径",
        type: "readonly",
        default: "",
        description: "SQLite 数据库文件位置"
      }
    ];
    let activeCategory = "appearance";
    let values = {};
    let saveState = "idle";
    let pendingKeys = /* @__PURE__ */ new Set();
    let saveTimer = null;
    let showKeys = {};
    let testingKey = null;
    let testResult = {};
    const categoryItems = derived(() => schema.filter((s) => {
      if (s.category !== activeCategory) return false;
      if (s.key === "mask_restricted" && (values["show_restricted"] ?? "false") !== "true") return false;
      if ((s.key === "network_allow_adult" || s.key === "network_adult_base_url") && (values["show_restricted"] ?? "false") !== "true") return false;
      return true;
    }));
    function setValue(key, value) {
      values = { ...values, [key]: value };
      pendingKeys = new Set(pendingKeys).add(key);
      scheduleSave();
    }
    function scheduleSave() {
      saveState = "saving";
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(
        () => {
          void flushSave();
        },
        500
      );
    }
    async function flushSave() {
      if (pendingKeys.size === 0) {
        saveState = "idle";
        return;
      }
      const keys = Array.from(pendingKeys);
      pendingKeys = /* @__PURE__ */ new Set();
      try {
        const settings = keys.map((k) => ({ key: k, value: values[k] ?? "" }));
        await client.put("/settings", { settings });
        saveState = "saved";
        settings.forEach((s) => settingsStore.setLocal(s.key, s.value));
        setTimeout(
          () => {
            if (saveState === "saved") saveState = "idle";
          },
          1500
        );
      } catch {
        saveState = "error";
        pendingKeys = /* @__PURE__ */ new Set([...pendingKeys, ...keys]);
      }
    }
    function rangeText(item) {
      const v = values[item.key] ?? item.default;
      return `${v}${item.unit ?? ""}`;
    }
    onDestroy(() => {
      if (saveTimer) {
        clearTimeout(saveTimer);
        saveTimer = null;
        if (pendingKeys.size > 0) void flushSave();
      }
    });
    head("1i19ct2", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>设置 — vitoice</title>`);
      });
    });
    $$renderer2.push(`<div class="settings-page svelte-1i19ct2"><section class="cat-content svelte-1i19ct2">`);
    {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="content-head svelte-1i19ct2"><h2 class="svelte-1i19ct2">${escape_html(categories.find((c) => c.id === activeCategory)?.label ?? "")}</h2> `);
      {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div> `);
      {
        $$renderer2.push("<!--[-1-->");
        {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> <div class="settings-list svelte-1i19ct2">`);
        {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> <!--[-->`);
        const each_array = ensure_array_like(categoryItems());
        for (let $$index_1 = 0, $$length = each_array.length; $$index_1 < $$length; $$index_1++) {
          let item = each_array[$$index_1];
          $$renderer2.push(`<div class="setting-row svelte-1i19ct2"><div class="setting-label svelte-1i19ct2"><span class="label-text svelte-1i19ct2">${escape_html(item.label)}</span> `);
          if (item.description) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<span class="label-desc svelte-1i19ct2">${escape_html(item.description)}</span>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></div> <div class="setting-control svelte-1i19ct2">`);
          if (item.type === "text") {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<div class="input-with-action svelte-1i19ct2"><input type="text" class="text-input svelte-1i19ct2"${attr("value", values[item.key] ?? "")} placeholder=""/> `);
            if (item.pickable) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<button class="action-btn icon-only svelte-1i19ct2" title="选择文件">`);
              folderIcon($$renderer2);
              $$renderer2.push(`<!----></button>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> `);
            if (item.testable) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<button class="action-btn test-btn svelte-1i19ct2"${attr("disabled", testingKey === item.key, true)}>${escape_html(testingKey === item.key ? "测试中…" : "测试")}</button>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></div>`);
          } else if (item.type === "password") {
            $$renderer2.push("<!--[1-->");
            $$renderer2.push(`<div class="input-with-action svelte-1i19ct2"><input${attr("type", showKeys[item.key] ? "text" : "password")} class="text-input svelte-1i19ct2"${attr("value", values[item.key] ?? "")} placeholder="••••••••" autocomplete="off"/> <button class="action-btn icon-only svelte-1i19ct2"${attr("title", showKeys[item.key] ? "隐藏" : "显示")}>`);
            if (showKeys[item.key]) {
              $$renderer2.push("<!--[0-->");
              eyeOffIcon($$renderer2);
            } else {
              $$renderer2.push("<!--[-1-->");
              eyeIcon($$renderer2);
            }
            $$renderer2.push(`<!--]--></button> `);
            if (item.testable) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<button class="action-btn test-btn svelte-1i19ct2"${attr("disabled", testingKey === item.key, true)}>${escape_html(testingKey === item.key ? "测试中…" : "测试")}</button>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></div>`);
          } else if (item.type === "number") {
            $$renderer2.push("<!--[2-->");
            $$renderer2.push(`<div class="number-row svelte-1i19ct2"><input type="number" class="text-input svelte-1i19ct2"${attr("value", values[item.key] ?? item.default)}${attr("min", item.min)}${attr("max", item.max)}${attr("step", item.step)}/> `);
            if (item.unit) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="unit svelte-1i19ct2">${escape_html(item.unit)}</span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></div>`);
          } else if (item.type === "range") {
            $$renderer2.push("<!--[3-->");
            $$renderer2.push(`<div class="range-row svelte-1i19ct2"><input type="range" class="range-input svelte-1i19ct2"${attr("value", values[item.key] ?? item.default)}${attr("min", item.min)}${attr("max", item.max)}${attr("step", item.step)}/> <span class="range-value svelte-1i19ct2">${escape_html(rangeText(item))}</span></div>`);
          } else if (item.type === "select") {
            $$renderer2.push("<!--[4-->");
            $$renderer2.select(
              {
                class: "select-input",
                value: values[item.key] ?? item.default,
                onchange: (e) => setValue(item.key, e.target.value)
              },
              ($$renderer3) => {
                $$renderer3.push(`<!--[-->`);
                const each_array_1 = ensure_array_like(item.options ?? []);
                for (let $$index = 0, $$length2 = each_array_1.length; $$index < $$length2; $$index++) {
                  let opt = each_array_1[$$index];
                  $$renderer3.option({ value: opt.value }, ($$renderer4) => {
                    $$renderer4.push(`${escape_html(opt.label)}`);
                  });
                }
                $$renderer3.push(`<!--]-->`);
              },
              "svelte-1i19ct2"
            );
          } else if (item.type === "toggle") {
            $$renderer2.push("<!--[5-->");
            $$renderer2.push(`<button type="button"${attr_class("toggle svelte-1i19ct2", void 0, { "on": (values[item.key] ?? item.default) === "true" })} role="switch"${attr("aria-checked", (values[item.key] ?? item.default) === "true")}${attr("aria-label", item.label)}><span class="knob svelte-1i19ct2"></span></button>`);
          } else if (item.type === "color") {
            $$renderer2.push("<!--[6-->");
            $$renderer2.push(`<div class="color-row svelte-1i19ct2"><input type="color" class="color-input svelte-1i19ct2"${attr("value", values[item.key] ?? item.default)}/> <span class="color-text svelte-1i19ct2">${escape_html(values[item.key] ?? item.default)}</span></div>`);
          } else if (item.type === "readonly") {
            $$renderer2.push("<!--[7-->");
            $$renderer2.push(`<div class="input-with-action svelte-1i19ct2"><input type="text" class="text-input readonly svelte-1i19ct2"${attr("value", values[item.key] ?? item.default)} readonly=""/> `);
            if (item.key === "db_path") {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<button class="action-btn svelte-1i19ct2">打开数据目录</button>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></div>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--> `);
          if (testResult[item.key]) {
            $$renderer2.push("<!--[0-->");
            testResultDisplay($$renderer2, testResult[item.key]);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></div></div>`);
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
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></section></div> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
export {
  _page as default
};
