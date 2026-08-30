// Tag operations store — encapsulates all tag/type context menu, inline rename,
// color picker, move-to-type, add-child, and delete-confirmation state and logic.
//
// This state is shared between MediaSidebar and ManageSidebar (both can trigger
// the context menus), so it lives in a singleton store rather than component-
// local state. The overlay UI (context menus, dialogs) is rendered by
// TagOverlays.svelte; inline popovers (color, move, add-child) are rendered
// by ManageSidebar.svelte.

import { client } from '$lib/api/client';
import type { Tag } from '$lib/api/tags';
import { librariesStore, type TagType } from '$lib/stores/libraries.svelte';
import { tagManageStore } from '$lib/stores/tagManage.svelte';
import { displayTypeName } from '$lib/components/layout/sidebarShared';

class TagOpsStore {
  // ---- 右键菜单 ----
  tagContextMenu = $state<{ x: number; y: number; tag: Tag } | null>(null);
  typeContextMenu = $state<{ x: number; y: number; type: TagType } | null>(null);

  // ---- 行内重命名 ----
  renamingTagId = $state<string | null>(null);
  renamingTagName = $state('');
  renamingTypeId = $state<number | null>(null);
  renamingTypeName = $state('');

  // ---- 设置颜色 ----
  colorPickerFor = $state<string | null>(null);

  // ---- 移动到类型 ----
  moveTypeFor = $state<string | null>(null);

  // ---- 添加子标签 ----
  addingChildTo = $state<string | null>(null);
  newChildName = $state('');

  // ---- 删除标签 ----
  deleteConfirmTag = $state<Tag | null>(null);

  // ---- 删除标签类型 ----
  deleteConfirmType = $state<TagType | null>(null);

  // ============ 标签右键菜单 ============
  openTagContextMenu(e: MouseEvent, tag: Tag): void {
    e.preventDefault();
    e.stopPropagation();
    this.tagContextMenu = { x: e.clientX, y: e.clientY, tag };
  }

  closeTagContextMenu(): void {
    this.tagContextMenu = null;
  }

  // ============ 标签行内重命名 ============
  startTagRename(tag: Tag): void {
    this.renamingTagId = tag.id;
    this.renamingTagName = tag.name;
    this.closeTagContextMenu();
  }

  async saveTagRename(tag: Tag): Promise<void> {
    const name = this.renamingTagName.trim();
    if (!name || name === tag.name) {
      this.renamingTagId = null;
      return;
    }
    try {
      await client.put(`/tags/${tag.id}`, { name });
      await librariesStore.reload();
    } catch {
      // silent
    }
    this.renamingTagId = null;
  }

  // ============ 添加子标签 ============
  startAddChild(tag: Tag): void {
    this.addingChildTo = tag.id;
    this.newChildName = '';
    this.closeTagContextMenu();
    // Note: expanding the parent tag in the manage tree is handled by
    // ManageSidebar via an $effect that watches `addingChildTo`.
  }

  async confirmAddChild(parent: Tag): Promise<void> {
    const name = this.newChildName.trim();
    if (!name) {
      this.addingChildTo = null;
      return;
    }
    try {
      await client.post('/tags', {
        name,
        tag_type_id: parent.tag_type_id,
        parent_id: Number(parent.id),
      });
      await librariesStore.reload();
    } catch {
      // silent
    }
    this.addingChildTo = null;
    this.newChildName = '';
  }

  // ============ 设置颜色 ============
  startColorPicker(tag: Tag): void {
    this.colorPickerFor = tag.id;
    this.closeTagContextMenu();
  }

  async setTagColor(tag: Tag, color: string | null): Promise<void> {
    try {
      await client.put(`/tags/${tag.id}`, { color });
      await librariesStore.reload();
    } catch {
      // silent
    }
    this.colorPickerFor = null;
  }

  // ============ 移动到类型 ============
  startMoveType(tag: Tag): void {
    this.moveTypeFor = tag.id;
    this.closeTagContextMenu();
  }

  async confirmMoveType(tag: Tag, typeId: number): Promise<void> {
    try {
      await client.put(`/tags/${tag.id}`, { tag_type_id: typeId, parent_id: null });
      await librariesStore.reload();
    } catch {
      // silent
    }
    this.moveTypeFor = null;
  }

  // ============ 删除标签 ============
  askDeleteTag(tag: Tag): void {
    this.deleteConfirmTag = tag;
    this.closeTagContextMenu();
  }

  async confirmDeleteTag(): Promise<void> {
    if (!this.deleteConfirmTag) return;
    try {
      await client.delete(`/tags/${this.deleteConfirmTag.id}`);
      await librariesStore.reload();
    } catch {
      // silent
    }
    this.deleteConfirmTag = null;
  }

  // ============ 标签类型右键菜单 ============
  openTypeContextMenu(e: MouseEvent, type: TagType): void {
    e.preventDefault();
    e.stopPropagation();
    this.typeContextMenu = { x: e.clientX, y: e.clientY, type };
  }

  closeTypeContextMenu(): void {
    this.typeContextMenu = null;
  }

  // ============ 类型行内重命名 ============
  startTypeRename(type: TagType): void {
    this.renamingTypeId = type.id;
    this.renamingTypeName = displayTypeName(type.name);
    this.closeTypeContextMenu();
  }

  async saveTypeRename(): Promise<void> {
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
      // silent
    }
    this.renamingTypeId = null;
  }

  // ============ 类型改色 ============
  async changeTypeColor(type: TagType, color: string): Promise<void> {
    try {
      await client.put(`/tag-types/${type.id}`, { color });
      await librariesStore.reload();
    } catch {
      // silent
    }
    this.typeContextMenu = null;
  }

  // ============ 删除标签类型 ============
  askDeleteType(type: TagType): void {
    this.deleteConfirmType = type;
    this.closeTypeContextMenu();
  }

  async confirmDeleteType(): Promise<void> {
    if (!this.deleteConfirmType) return;
    try {
      await client.delete(`/tag-types/${this.deleteConfirmType.id}`);
      // 如果删除的是当前选中的类型，清除选择
      if (tagManageStore.selectedTypeId === this.deleteConfirmType.id) {
        tagManageStore.selectType(null);
      }
      await librariesStore.reload();
    } catch {
      // silent
    }
    this.deleteConfirmType = null;
  }

  // ============ 点击外部关闭所有弹出 ============
  handleWindowClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    if (this.tagContextMenu && !target.closest('.tag-ctx-menu')) {
      this.tagContextMenu = null;
    }
    if (this.typeContextMenu && !target.closest('.type-ctx-menu')) {
      this.typeContextMenu = null;
    }
    if (this.colorPickerFor && !target.closest('.color-pop') && !target.closest('.tag-ctx-menu')) {
      this.colorPickerFor = null;
    }
    if (this.moveTypeFor && !target.closest('.move-pop') && !target.closest('.tag-ctx-menu')) {
      this.moveTypeFor = null;
    }
  }
}

export const tagOps = new TagOpsStore();
