import "clsx";
import { c as client } from "./client2.js";
import { l as librariesStore } from "./libraries.svelte.js";
class TagManageStore {
  selectedTypeId = null;
  selectedTagId = null;
  /** Select a tag type (or deselect with null). */
  selectType(typeId) {
    this.selectedTypeId = typeId;
    this.selectedTagId = null;
  }
  /** Select a specific tag (or deselect with null). */
  selectTag(tagId) {
    this.selectedTagId = tagId;
  }
}
const tagManageStore = new TagManageStore();
const safeColor = (c) => /^#[0-9a-fA-F]{6}$/.test(c ?? "") ? c : "";
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
const TYPE_PALETTE = [
  "#635bff",
  "#f59e0b",
  "#34c759",
  "#ff3b30",
  "#ff2d55",
  "#af52de",
  "#5ac8fa",
  "#ff9500",
  "#8e8e93",
  "#00c7be"
];
class TagOpsStore {
  // ---- 右键菜单 ----
  tagContextMenu = null;
  typeContextMenu = null;
  // ---- 行内重命名 ----
  renamingTagId = null;
  renamingTagName = "";
  renamingTypeId = null;
  renamingTypeName = "";
  // ---- 设置颜色 ----
  colorPickerFor = null;
  // ---- 移动到类型 ----
  moveTypeFor = null;
  // ---- 添加子标签 ----
  addingChildTo = null;
  newChildName = "";
  // ---- 删除标签 ----
  deleteConfirmTag = null;
  // ---- 删除标签类型 ----
  deleteConfirmType = null;
  // ============ 标签右键菜单 ============
  openTagContextMenu(e, tag) {
    e.preventDefault();
    e.stopPropagation();
    this.tagContextMenu = { x: e.clientX, y: e.clientY, tag };
  }
  closeTagContextMenu() {
    this.tagContextMenu = null;
  }
  // ============ 标签行内重命名 ============
  startTagRename(tag) {
    this.renamingTagId = tag.id;
    this.renamingTagName = tag.name;
    this.closeTagContextMenu();
  }
  async saveTagRename(tag) {
    const name = this.renamingTagName.trim();
    if (!name || name === tag.name) {
      this.renamingTagId = null;
      return;
    }
    try {
      await client.put(`/tags/${tag.id}`, { name });
      await librariesStore.reload();
    } catch {
    }
    this.renamingTagId = null;
  }
  // ============ 添加子标签 ============
  startAddChild(tag) {
    this.addingChildTo = tag.id;
    this.newChildName = "";
    this.closeTagContextMenu();
  }
  async confirmAddChild(parent) {
    const name = this.newChildName.trim();
    if (!name) {
      this.addingChildTo = null;
      return;
    }
    try {
      await client.post("/tags", {
        name,
        tag_type_id: parent.tag_type_id,
        parent_id: Number(parent.id)
      });
      await librariesStore.reload();
    } catch {
    }
    this.addingChildTo = null;
    this.newChildName = "";
  }
  // ============ 设置颜色 ============
  startColorPicker(tag) {
    this.colorPickerFor = tag.id;
    this.closeTagContextMenu();
  }
  async setTagColor(tag, color) {
    try {
      await client.put(`/tags/${tag.id}`, { color });
      await librariesStore.reload();
    } catch {
    }
    this.colorPickerFor = null;
  }
  // ============ 移动到类型 ============
  startMoveType(tag) {
    this.moveTypeFor = tag.id;
    this.closeTagContextMenu();
  }
  async confirmMoveType(tag, typeId) {
    try {
      await client.put(`/tags/${tag.id}`, { tag_type_id: typeId, parent_id: null });
      await librariesStore.reload();
    } catch {
    }
    this.moveTypeFor = null;
  }
  // ============ 删除标签 ============
  askDeleteTag(tag) {
    this.deleteConfirmTag = tag;
    this.closeTagContextMenu();
  }
  async confirmDeleteTag() {
    if (!this.deleteConfirmTag) return;
    try {
      await client.delete(`/tags/${this.deleteConfirmTag.id}`);
      await librariesStore.reload();
    } catch {
    }
    this.deleteConfirmTag = null;
  }
  // ============ 标签类型右键菜单 ============
  openTypeContextMenu(e, type) {
    e.preventDefault();
    e.stopPropagation();
    this.typeContextMenu = { x: e.clientX, y: e.clientY, type };
  }
  closeTypeContextMenu() {
    this.typeContextMenu = null;
  }
  // ============ 类型行内重命名 ============
  startTypeRename(type) {
    this.renamingTypeId = type.id;
    this.renamingTypeName = displayTypeName(type.name);
    this.closeTypeContextMenu();
  }
  async saveTypeRename() {
    if (this.renamingTypeId === null) return;
    const id = this.renamingTypeId;
    const name = this.renamingTypeName.trim();
    if (!name) {
      this.renamingTypeId = null;
      return;
    }
    try {
      await client.put(`/tag-types/${id}`, { name });
      await librariesStore.reload();
    } catch {
    }
    this.renamingTypeId = null;
  }
  // ============ 类型改色 ============
  async changeTypeColor(type, color) {
    try {
      await client.put(`/tag-types/${type.id}`, { color });
      await librariesStore.reload();
    } catch {
    }
    this.typeContextMenu = null;
  }
  // ============ 删除标签类型 ============
  askDeleteType(type) {
    this.deleteConfirmType = type;
    this.closeTypeContextMenu();
  }
  async confirmDeleteType() {
    if (!this.deleteConfirmType) return;
    try {
      await client.delete(`/tag-types/${this.deleteConfirmType.id}`);
      if (tagManageStore.selectedTypeId === this.deleteConfirmType.id) {
        tagManageStore.selectType(null);
      }
      await librariesStore.reload();
    } catch {
    }
    this.deleteConfirmType = null;
  }
  // ============ 点击外部关闭所有弹出 ============
  handleWindowClick(e) {
    const target = e.target;
    if (this.tagContextMenu && !target.closest(".tag-ctx-menu")) {
      this.tagContextMenu = null;
    }
    if (this.typeContextMenu && !target.closest(".type-ctx-menu")) {
      this.typeContextMenu = null;
    }
    if (this.colorPickerFor && !target.closest(".color-pop") && !target.closest(".tag-ctx-menu")) {
      this.colorPickerFor = null;
    }
    if (this.moveTypeFor && !target.closest(".move-pop") && !target.closest(".tag-ctx-menu")) {
      this.moveTypeFor = null;
    }
  }
}
const tagOps = new TagOpsStore();
export {
  TYPE_PALETTE as T,
  tagManageStore as a,
  displayTypeName as d,
  safeColor as s,
  tagOps as t
};
