import { k as head, e as escape_html } from "../../../../chunks/index.js";
import "@sveltejs/kit/internal";
import "../../../../chunks/exports.js";
import "../../../../chunks/utils2.js";
import "@sveltejs/kit/internal/server";
import "../../../../chunks/root.js";
import "../../../../chunks/state.svelte.js";
import "../../../../chunks/client2.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { params } = $$props;
    head("14a2q9u", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>${escape_html("加载中")} — vitoice</title>`);
      });
    });
    {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="state svelte-14a2q9u">加载中…</div>`);
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
