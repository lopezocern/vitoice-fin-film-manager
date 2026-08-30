import { e as escape_html, c as attr, f as ensure_array_like, a as attr_class, h as attr_style, i as stringify, j as bind_props, d as derived } from "./index.js";
import "./client2.js";
import { i as isAvMedia } from "./media.js";
function TagSelector($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let {
      open = false,
      tags = [],
      selected = [],
      multiple = true,
      title = "选择标签",
      onselect,
      oncancel
    } = $$props;
    let query = "";
    let local = [];
    function tagType(t) {
      const ext = t;
      return ext.type ?? ext.category ?? "通用";
    }
    const filtered = derived(() => query.trim() ? tags.filter((t) => t.name.toLowerCase().includes(query.trim().toLowerCase())) : tags);
    const groups = derived(() => {
      const map = /* @__PURE__ */ new Map();
      for (const t of filtered()) {
        const g = tagType(t);
        if (!map.has(g)) map.set(g, []);
        map.get(g).push(t);
      }
      return Array.from(map.entries()).map(([name, items]) => ({ name, items }));
    });
    function isSelected(id) {
      return local.includes(id);
    }
    const totalSelected = derived(() => local.length);
    if (open) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="backdrop svelte-15onj65" role="presentation"><div class="dialog svelte-15onj65" role="dialog" aria-modal="true" aria-labelledby="tag-selector-title" tabindex="-1"><div class="dialog-head svelte-15onj65"><h2 id="tag-selector-title" class="svelte-15onj65">${escape_html(title)}</h2> <button class="close-btn svelte-15onj65" aria-label="关闭">×</button></div> <div class="search-wrap svelte-15onj65"><svg class="search-icon svelte-15onj65" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z" fill="currentColor"></path></svg> <input type="text" class="search-input svelte-15onj65" placeholder="搜索标签..."${attr("value", query)}/> `);
      {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div> <div class="dialog-body svelte-15onj65">`);
      if (groups().length === 0) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="empty svelte-15onj65">`);
        {
          $$renderer2.push("<!--[-1-->");
          $$renderer2.push(`<div class="empty-text svelte-15onj65">暂无可用标签</div>`);
        }
        $$renderer2.push(`<!--]--></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<!--[-->`);
        const each_array = ensure_array_like(groups());
        for (let $$index_1 = 0, $$length = each_array.length; $$index_1 < $$length; $$index_1++) {
          let group = each_array[$$index_1];
          $$renderer2.push(`<div class="group svelte-15onj65"><div class="group-head svelte-15onj65"><span class="group-name svelte-15onj65">${escape_html(group.name)}</span> <span class="group-count svelte-15onj65">${escape_html(group.items.length)}</span></div> <div class="group-items svelte-15onj65"><!--[-->`);
          const each_array_1 = ensure_array_like(group.items);
          for (let $$index = 0, $$length2 = each_array_1.length; $$index < $$length2; $$index++) {
            let tag = each_array_1[$$index];
            $$renderer2.push(`<button type="button"${attr_class("tag-chip svelte-15onj65", void 0, { "active": isSelected(tag.id) })}>`);
            if (tag.color) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="tag-dot svelte-15onj65"${attr_style(`background:${stringify(tag.color)}`)}></span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> <span class="tag-name">${escape_html(tag.name)}</span> `);
            if (tag.count != null) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="tag-count svelte-15onj65">${escape_html(tag.count)}</span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--> `);
            if (isSelected(tag.id)) {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<span class="check svelte-15onj65">✓</span>`);
            } else {
              $$renderer2.push("<!--[-1-->");
            }
            $$renderer2.push(`<!--]--></button>`);
          }
          $$renderer2.push(`<!--]--></div></div>`);
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]--></div> <div class="dialog-foot svelte-15onj65"><div class="selected-info svelte-15onj65">`);
      if (multiple) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`已选 <strong class="svelte-15onj65">${escape_html(totalSelected())}</strong> 个标签`);
      } else {
        $$renderer2.push("<!--[-1-->");
        if (totalSelected() > 0) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`已选 1 个标签`);
        } else {
          $$renderer2.push("<!--[-1-->");
          $$renderer2.push(`未选择`);
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]--></div> <div class="actions svelte-15onj65"><button class="btn btn-cancel svelte-15onj65">取消</button> <button class="btn btn-primary svelte-15onj65"${attr("disabled", totalSelected() === 0, true)}>确认</button></div></div></div></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
    bind_props($$props, { open });
  });
}
function ConfirmDialog($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let {
      open = false,
      title = "确认操作",
      description = "",
      confirmText = "确认",
      cancelText = "取消",
      danger = false,
      disableConfirm = false,
      extraButtonText = "",
      onconfirm,
      oncancel,
      onextra
      /** 可选第三按钮（显示在取消按钮左侧，用于"二次确认时提供另一操作"等场景） */
    } = $$props;
    if (open) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="backdrop svelte-r5cneq" role="presentation"><div${attr_class("dialog svelte-r5cneq", void 0, { "danger": danger })} role="dialog" aria-modal="true" aria-labelledby="confirm-title" tabindex="-1"><div class="dialog-head svelte-r5cneq"><div${attr_class("icon-wrap svelte-r5cneq", void 0, { "danger": danger })} aria-hidden="true">`);
      if (danger) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 2L1 21h22L12 2zm0 6l7.53 13H4.47L12 8zm-1 4v4h2v-4h-2zm0 5v2h2v-2h-2z" fill="currentColor"></path></svg>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" fill="currentColor"></path></svg>`);
      }
      $$renderer2.push(`<!--]--></div> <h2 id="confirm-title" class="svelte-r5cneq">${escape_html(title)}</h2></div> `);
      if (description) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="dialog-body svelte-r5cneq">${escape_html(description)}</div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> <div class="dialog-foot svelte-r5cneq">`);
      if (extraButtonText && onextra) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<button class="btn btn-extra svelte-r5cneq">${escape_html(extraButtonText)}</button>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> <button class="btn btn-cancel svelte-r5cneq">${escape_html(cancelText)}</button> <button${attr_class("btn svelte-r5cneq", void 0, { "btn-danger": danger, "btn-primary": !danger })}${attr("disabled", disableConfirm, true)}>${escape_html(confirmText)}</button></div></div></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
    bind_props($$props, { open });
  });
}
function EditMediaDialog($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { open = false, media, onsuccess } = $$props;
    let title = "";
    let year = "";
    let description = "";
    let uploading = false;
    let saving = false;
    const isAv = derived(() => media ? isAvMedia(media) : false);
    if (open && media) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="modal-overlay svelte-11rm9pw"><div class="modal-card svelte-11rm9pw"><div class="modal-header svelte-11rm9pw"><h2 class="svelte-11rm9pw">编辑媒体</h2> <button class="close-btn svelte-11rm9pw"${attr("disabled", uploading, true)}>✕</button></div> <div class="modal-body svelte-11rm9pw">`);
      {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> <div class="poster-section svelte-11rm9pw"><label class="form-label svelte-11rm9pw" for="poster-file-input">封面图</label> <div${attr_class("poster-preview-area svelte-11rm9pw", void 0, { "av-poster": isAv() })}>`);
      {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<div class="poster-placeholder svelte-11rm9pw"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg> <span>暂无封面</span></div>`);
      }
      $$renderer2.push(`<!--]--></div> <div class="poster-actions svelte-11rm9pw"><button class="btn-secondary svelte-11rm9pw"${attr("disabled", saving, true)}>${escape_html("选择图片")}</button> `);
      {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> <input id="poster-file-input" type="file" accept="image/jpeg,image/png,image/webp,image/gif" style="display:none"/></div> <div class="form-hint svelte-11rm9pw">支持 JPG/PNG/WebP，最大 10MB</div></div> <div class="form-group svelte-11rm9pw"><label class="form-label svelte-11rm9pw" for="edit-title">标题</label> <input id="edit-title" type="text"${attr("value", title)} placeholder="媒体标题"${attr("disabled", saving, true)} class="svelte-11rm9pw"/></div> <div class="form-group svelte-11rm9pw"><label class="form-label svelte-11rm9pw" for="edit-year">年份</label> <input id="edit-year" type="number"${attr("value", year)} placeholder="如 2024" min="1900" max="2099"${attr("disabled", saving, true)} class="svelte-11rm9pw"/></div> <div class="form-group svelte-11rm9pw"><label class="form-label svelte-11rm9pw" for="edit-desc">描述</label> <textarea id="edit-desc" placeholder="媒体描述" rows="3"${attr("disabled", saving, true)} class="svelte-11rm9pw">`);
      const $$body = escape_html(description);
      if ($$body) {
        $$renderer2.push(`${$$body}`);
      }
      $$renderer2.push(`</textarea></div></div> <div class="modal-footer svelte-11rm9pw"><button class="btn-secondary svelte-11rm9pw"${attr("disabled", uploading, true)}>取消</button> <button class="btn-primary svelte-11rm9pw"${attr("disabled", uploading, true)}>${escape_html("保存")}</button></div></div></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]-->`);
    bind_props($$props, { open });
  });
}
export {
  ConfirmDialog as C,
  EditMediaDialog as E,
  TagSelector as T
};
