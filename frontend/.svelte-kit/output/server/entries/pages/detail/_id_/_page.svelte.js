import { k as head, d as derived, e as escape_html, a as attr_class } from "../../../../chunks/index.js";
import { g as goto } from "../../../../chunks/client.js";
import { m as mediaApi } from "../../../../chunks/media.js";
import "../../../../chunks/client2.js";
import { T as TagSelector, C as ConfirmDialog, E as EditMediaDialog } from "../../../../chunks/EditMediaDialog.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { params } = $$props;
    const id = derived(() => params.id);
    let media = null;
    let allTags = [];
    let tagSelectorOpen = false;
    let editDialogOpen = false;
    let editMediaTarget = null;
    let toast = null;
    let toastTimer = null;
    function showToast(msg, type = "ok") {
      toast = { msg, type };
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast = null, 2500);
    }
    function readMeta(key, fallback) {
      if (!media?.metadata) return fallback;
      const v = media.metadata[key];
      return v ?? fallback;
    }
    const displayTitle = derived(() => media?.title ?? readMeta("title", media?.filename ?? ""));
    async function addTags(tagIds) {
      if (!media || tagIds.length === 0) return;
      tagSelectorOpen = false;
      const existing = media.tags ?? [];
      const merged = Array.from(/* @__PURE__ */ new Set([...existing, ...tagIds]));
      try {
        const updated = await mediaApi.update(media.id, { tags: merged });
        media = updated;
        showToast(`已添加 ${tagIds.length} 个标签`);
      } catch {
        showToast("添加标签失败", "err");
      } finally {
      }
    }
    let deleteDialogOpen = false;
    async function deleteMedia() {
      if (!media) return;
      deleteDialogOpen = false;
      try {
        await mediaApi.delete(media.id);
        showToast("已移入回收站");
        setTimeout(() => goto("/manage"), 800);
      } catch {
        showToast("删除失败", "err");
      }
    }
    async function reloadMedia() {
      try {
        media = await mediaApi.get(id());
      } catch {
        showToast("刷新数据失败", "err");
      }
    }
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      head("9y3fua", $$renderer3, ($$renderer4) => {
        $$renderer4.title(($$renderer5) => {
          $$renderer5.push(`<title>${escape_html(media ? displayTitle() : "加载中")} — vitoice</title>`);
        });
      });
      {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div class="state svelte-9y3fua">加载中…</div>`);
      }
      $$renderer3.push(`<!--]--> `);
      TagSelector($$renderer3, {
        tags: allTags,
        multiple: true,
        title: "添加标签",
        selected: media?.tags ?? [],
        onselect: (ids) => addTags(ids),
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
      ConfirmDialog($$renderer3, {
        title: "删除媒体",
        description: `将"${displayTitle()}"移入回收站。

磁盘文件不会删除，可在回收站中恢复或彻底删除（无自动清理期限）。`,
        confirmText: "删除",
        danger: true,
        onconfirm: deleteMedia,
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
      EditMediaDialog($$renderer3, {
        media: editMediaTarget,
        onsuccess: reloadMedia,
        get open() {
          return editDialogOpen;
        },
        set open($$value) {
          editDialogOpen = $$value;
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
        $$renderer3.push(`<div${attr_class("toast svelte-9y3fua", void 0, { "ok": toast.type === "ok", "err": toast.type === "err" })}>${escape_html(toast.msg)}</div>`);
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
export {
  _page as default
};
