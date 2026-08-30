/**
 * Shared store for tag management — bridges Sidebar (type selector) and
 * TagsManageView (card grid) so they can share the currently selected
 * tag type without prop drilling.
 *
 * Sidebar writes `selectedTypeId` when the user clicks a type group;
 * TagsManageView reads it reactively to load the matching tags.
 */
class TagManageStore {
  selectedTypeId = $state<number | null>(null);
  selectedTagId = $state<number | null>(null);

  /** Select a tag type (or deselect with null). */
  selectType(typeId: number | null): void {
    this.selectedTypeId = typeId;
    this.selectedTagId = null;  // clear tag selection on type change
  }

  /** Select a specific tag (or deselect with null). */
  selectTag(tagId: number | null): void {
    this.selectedTagId = tagId;
  }
}

export const tagManageStore = new TagManageStore();
