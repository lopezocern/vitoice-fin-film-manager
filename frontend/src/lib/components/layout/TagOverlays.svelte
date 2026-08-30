<script lang="ts">
  // TagOverlays — renders the tag/type context menus and delete-confirmation
  // dialogs. All state and logic live in the `tagOps` store; this component
  // is purely the overlay UI.
  import { tagOps } from '$lib/stores/tagOps.svelte';
  import { displayTypeName, TYPE_PALETTE } from './sidebarShared';
</script>

<!-- 标签类型右键菜单 -->
{#if tagOps.typeContextMenu}
  <!-- svelte-ignore a11y_click_events_have_keyevents -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="ctx-backdrop" role="button" tabindex="-1" aria-label="关闭菜单" onclick={tagOps.closeTypeContextMenu} onkeydown={(e) => e.key === 'Escape' && tagOps.closeTypeContextMenu()}></div>
  <div
    class="tag-ctx-menu type-ctx-menu"
    style={`left: ${Math.min(tagOps.typeContextMenu.x, window.innerWidth - 180)}px; top: ${Math.min(tagOps.typeContextMenu.y, window.innerHeight - 240)}px`}
  >
    <button class="ctx-item" onclick={() => tagOps.startTypeRename(tagOps.typeContextMenu!.type)}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4">
        <path d="M11 2l3 3-8 8H3v-3l8-8z" stroke-linejoin="round"></path>
      </svg>
      重命名
    </button>
    <div class="ctx-sub-section">
      <div class="ctx-sub-label">颜色</div>
      <div class="ctx-palette">
        {#each TYPE_PALETTE as c (c)}
          <button
            class="ctx-color"
            class:active={tagOps.typeContextMenu!.type.color === c}
            style={`background:${c}`}
            onclick={() => tagOps.changeTypeColor(tagOps.typeContextMenu!.type, c)}
          ></button>
        {/each}
      </div>
    </div>
    <div class="ctx-sep"></div>
    <button class="ctx-item ctx-danger" onclick={() => tagOps.askDeleteType(tagOps.typeContextMenu!.type)}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4">
        <path d="M3 4h10M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4"></path>
      </svg>
      删除类型
    </button>
  </div>
{/if}

<!-- 标签类型删除确认 -->
{#if tagOps.deleteConfirmType}
  <!-- svelte-ignore a11y_click_events_have_keyevents -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="del-backdrop" role="button" tabindex="-1" aria-label="关闭弹窗" onclick={() => (tagOps.deleteConfirmType = null)} onkeydown={(e) => e.key === 'Escape' && (tagOps.deleteConfirmType = null)}>
    <!-- svelte-ignore a11y_click_events_have_keyevents -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="del-dialog" role="dialog" aria-label="删除确认" onclick={(e) => e.stopPropagation()}>
      <div class="del-title">确认删除标签类型？</div>
      <div class="del-desc">
        「{displayTypeName(tagOps.deleteConfirmType.name)}」及其所有标签将被永久删除，关联媒体将解除这些标签。
      </div>
      <div class="del-actions">
        <button class="del-btn del-cancel" onclick={() => (tagOps.deleteConfirmType = null)}>取消</button>
        <button class="del-btn del-ok" onclick={tagOps.confirmDeleteType}>删除</button>
      </div>
    </div>
  </div>
{/if}

<!-- 右键上下文菜单 -->
{#if tagOps.tagContextMenu}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="ctx-backdrop" role="button" tabindex="-1" aria-label="关闭菜单" onclick={tagOps.closeTagContextMenu} onkeydown={(e) => e.key === 'Escape' && tagOps.closeTagContextMenu()}></div>
  <div
    class="tag-ctx-menu"
    style={`left: ${Math.min(tagOps.tagContextMenu.x, window.innerWidth - 180)}px; top: ${Math.min(tagOps.tagContextMenu.y, window.innerHeight - 220)}px`}
  >
    <button class="ctx-item" onclick={() => tagOps.startTagRename(tagOps.tagContextMenu!.tag)}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4">
        <path d="M11 2l3 3-8 8H3v-3l8-8z" stroke-linejoin="round"></path>
      </svg>
      重命名
    </button>
    <button class="ctx-item" onclick={() => tagOps.startAddChild(tagOps.tagContextMenu!.tag)}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4">
        <line x1="8" y1="3" x2="8" y2="13" stroke-linecap="round"></line>
        <line x1="3" y1="8" x2="13" y2="8" stroke-linecap="round"></line>
      </svg>
      添加子标签
    </button>
    <button class="ctx-item" onclick={() => tagOps.startColorPicker(tagOps.tagContextMenu!.tag)}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4">
        <circle cx="8" cy="8" r="6"></circle>
        <circle cx="5.5" cy="6" r="0.8" fill="currentColor" stroke="none"></circle>
        <circle cx="10.5" cy="6" r="0.8" fill="currentColor" stroke="none"></circle>
        <circle cx="8" cy="10.5" r="0.8" fill="currentColor" stroke="none"></circle>
      </svg>
      设置颜色
    </button>
    <button class="ctx-item" onclick={() => tagOps.startMoveType(tagOps.tagContextMenu!.tag)}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4">
        <path d="M3 6h7M3 6l2.5-2.5M3 6l2.5 2.5M13 10H6M13 10l-2.5-2.5M13 10l-2.5 2.5" stroke-linecap="round" stroke-linejoin="round"></path>
      </svg>
      移动到类型
    </button>
    <div class="ctx-sep"></div>
    <button class="ctx-item ctx-danger" onclick={() => tagOps.askDeleteTag(tagOps.tagContextMenu!.tag)}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4">
        <path d="M3 4h10M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4"></path>
      </svg>
      删除
    </button>
  </div>
{/if}

<!-- 删除确认弹窗 -->
{#if tagOps.deleteConfirmTag}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="del-backdrop" role="button" tabindex="-1" aria-label="关闭弹窗" onclick={() => (tagOps.deleteConfirmTag = null)} onkeydown={(e) => e.key === 'Escape' && (tagOps.deleteConfirmTag = null)}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="del-dialog" role="dialog" aria-label="删除确认" onclick={(e) => e.stopPropagation()}>
      <div class="del-title">确认删除标签？</div>
      <div class="del-desc">
        「{tagOps.deleteConfirmTag.name}」及其子标签将被永久删除，关联媒体将解除此标签。
      </div>
      <div class="del-actions">
        <button class="del-btn del-cancel" onclick={() => (tagOps.deleteConfirmTag = null)}>取消</button>
        <button class="del-btn del-ok" onclick={tagOps.confirmDeleteTag}>删除</button>
      </div>
    </div>
  </div>
{/if}

<style>
  /* ---- 右键上下文菜单 ---- */
  .ctx-backdrop {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: transparent;
  }
  .tag-ctx-menu {
    position: fixed;
    z-index: 201;
    min-width: 160px;
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    box-shadow: var(--shadow-md);
    padding: 4px;
  }
  .ctx-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 6px 10px;
    border: none;
    background: none;
    color: var(--ink-secondary);
    font-size: 12.5px;
    text-align: left;
    cursor: pointer;
    border-radius: var(--radius-xs);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
  }
  .ctx-item:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }
  .ctx-item svg {
    flex-shrink: 0;
    opacity: 0.7;
  }
  .ctx-danger {
    color: var(--danger, #ff3b30);
  }
  .ctx-danger:hover {
    background: color-mix(in srgb, var(--danger, #ff3b30) 12%, transparent);
    color: var(--danger, #ff3b30);
  }
  .ctx-sep {
    height: 1px;
    background: var(--rule-light);
    margin: 4px 6px;
  }

  /* ---- 删除确认弹窗 ---- */
  .del-backdrop {
    position: fixed;
    inset: 0;
    z-index: 300;
    background: color-mix(in srgb, #000 50%, transparent);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .del-dialog {
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg, 12px);
    box-shadow: var(--shadow-lg);
    padding: 20px 24px;
    min-width: 320px;
    max-width: 400px;
  }
  .del-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 8px;
  }
  .del-desc {
    font-size: 13px;
    color: var(--ink-tertiary);
    line-height: 1.5;
    margin-bottom: 16px;
  }
  .del-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
  .del-btn {
    padding: 6px 16px;
    border: none;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: background var(--dur) var(--ease-out);
  }
  .del-cancel {
    background: var(--bg-surface);
    color: var(--ink-secondary);
  }
  .del-cancel:hover {
    background: var(--bg-hover);
  }
  .del-ok {
    background: var(--danger, #ff3b30);
    color: #fff;
  }
  .del-ok:hover {
    background: color-mix(in srgb, var(--danger, #ff3b30) 85%, #000);
  }
</style>
