import { k as head, a as attr_class, e as escape_html, d as derived } from "../../../chunks/index.js";
import { o as onDestroy } from "../../../chunks/index-server.js";
import "@sveltejs/kit/internal";
import "../../../chunks/exports.js";
import "../../../chunks/utils2.js";
import "@sveltejs/kit/internal/server";
import "../../../chunks/root.js";
import "../../../chunks/state.svelte.js";
import "../../../chunks/client2.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    loadPref("vitoice:volume", 1);
    loadPref("vitoice:muted", false);
    loadPref("vitoice:lastVolume", 1);
    loadPref("vitoice:captions", false);
    let isFullscreen = false;
    const title = derived(() => "播放器");
    function loadPref(key, fallback) {
      try {
        const v = localStorage.getItem(key);
        if (v === null) return fallback;
        return JSON.parse(v);
      } catch {
        return fallback;
      }
    }
    async function saveProgress() {
      return;
    }
    onDestroy(() => {
      void saveProgress();
    });
    head("nefmhu", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>${escape_html(title())} — 播放器</title>`);
      });
    });
    $$renderer2.push(`<div${attr_class("player-root svelte-nefmhu", void 0, { "fs": isFullscreen })}>`);
    {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="state-screen svelte-nefmhu"><div class="spinner svelte-nefmhu"></div> <div class="state-text svelte-nefmhu">加载中…</div></div>`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
export {
  _page as default
};
