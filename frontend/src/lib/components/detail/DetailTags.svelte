<script lang="ts">
  // 详情页标签区：分组展示、右键删除、添加入口
  import type { Tag } from '$lib/api/tags';

  let {
    mediaTagObjects,
    groupedTags,
    onadd,
    onremove
  }: {
    mediaTagObjects: Tag[];
    groupedTags: { name: string; items: Tag[] }[];
    onadd?: () => void;
    onremove?: (tagId: string) => void;
  } = $props();

  // 右键菜单状态（内部管理）
  let contextMenuTag = $state<string | null>(null);

  function onTagContext(e: MouseEvent, tagId: string): void {
    e.preventDefault();
    contextMenuTag = tagId;
  }

  function handleRemove(tagId: string): void {
    contextMenuTag = null;
    onremove?.(tagId);
  }

  // 关闭右键菜单
  $effect(() => {
    if (contextMenuTag) {
      const close = () => (contextMenuTag = null);
      window.addEventListener('click', close);
      return () => window.removeEventListener('click', close);
    }
  });
</script>

<section class="section">
  <div class="section-head">
    <h2 class="section-title">标签</h2>
    <button class="section-add" onclick={() => onadd?.()}>
      <svg viewBox="0 0 24 24" width="12" height="12"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" fill="currentColor"/></svg>
      添加
    </button>
  </div>
  {#if mediaTagObjects.length > 0}
    {#each groupedTags as group (group.name)}
      <div class="tag-group">
        <div class="tag-group-head">{group.name}</div>
        <div class="tag-group-items">
          {#each group.items as tag (tag.id)}
            <div class="tag-pill-wrap">
              <div
                class="tag-pill"
                style={tag.color ? `--tag-color:${tag.color}` : ''}
                oncontextmenu={(e) => onTagContext(e, tag.id)}
                role="button"
                tabindex="0"
              >
                {#if tag.color}<span class="tag-color-dot"></span>{/if}
                <span class="tag-name">{tag.name}</span>
                <button
                  class="tag-remove"
                  title="移除标签"
                  aria-label={`移除标签 ${tag.name}`}
                  onclick={() => handleRemove(tag.id)}
                  oncontextmenu={(e) => e.stopPropagation()}
                >
                  <svg viewBox="0 0 24 24" width="11" height="11" aria-hidden="true">
                    <path d="M18.3 5.71L12 12l6.3 6.29L16.88 20 10.59 13.71 4.3 20 3 18.71 9.29 12.41 3 6.12 4.3 4.88 10.59 11.17 16.88 4.88z" fill="currentColor" />
                  </svg>
                </button>
              </div>
              {#if contextMenuTag === tag.id}
                <div class="ctx-menu" role="menu" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
                  <button class="ctx-item danger" onclick={() => handleRemove(tag.id)}>
                    <svg viewBox="0 0 24 24" width="12" height="12"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/></svg>
                    删除标签
                  </button>
                </div>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/each}
    <div class="tag-hint">点击 × 移除标签 · 右键删除标签</div>
  {:else}
    <div class="section-empty">
      暂无标签
      <button class="link-btn" onclick={() => onadd?.()}>添加标签</button>
    </div>
  {/if}
</section>

<style>
  /* ---- 共享 section 样式 ---- */
  .section {
    margin-bottom: 28px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--rule);
  }

  .section:last-child {
    border-bottom: none;
    margin-bottom: 0;
  }

  .section-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }

  .section-title {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
  }

  .section-add {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: none;
    background: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: var(--radius);
    transition: background 200ms;
  }

  .section-add:hover {
    background: var(--accent-soft);
  }

  .section-empty {
    padding: 16px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    background: var(--bg-soft);
    border-radius: var(--radius);
  }

  .link-btn {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
    margin-left: 8px;
    text-decoration: underline;
  }

  /* ---- 标签 ---- */
  .tag-group {
    margin-bottom: 12px;
  }

  .tag-group-head {
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 6px;
  }

  .tag-group-items {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .tag-pill-wrap {
    position: relative;
  }

  .tag-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    height: 26px;
    padding: 0 6px 0 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius-full);
    background: var(--bg2);
    color: var(--ink);
    font-size: 12px;
    transition: all 200ms ease;
    --tag-color: var(--neutral);
  }

  .tag-pill:hover {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .tag-color-dot {
    width: 7px;
    height: 7px;
    border-radius: var(--radius-full);
    background: var(--tag-color);
  }

  .tag-name {
    white-space: nowrap;
  }

  .tag-remove {
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: var(--radius-full);
    background: none;
    color: var(--muted);
    cursor: pointer;
    transition: color 120ms ease, background 120ms ease;
  }

  .tag-remove:hover {
    color: #ff3b30;
    background: rgba(255, 59, 48, 0.12);
  }

  .tag-hint {
    margin-top: 8px;
    font-size: 11px;
    color: var(--muted);
    font-style: italic;
  }

  .ctx-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    z-index: 50;
    min-width: 120px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.14);
    padding: 4px;
    animation: pop 120ms ease;
  }

  @keyframes pop {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .ctx-item {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding: 6px 8px;
    border: none;
    background: none;
    border-radius: var(--radius);
    color: var(--ink);
    font-size: 12px;
    text-align: left;
    transition: background 200ms;
  }

  .ctx-item:hover {
    background: var(--bg-soft);
  }

  .ctx-item.danger {
    color: #ff3b30;
  }

  .ctx-item.danger:hover {
    background: rgba(255, 59, 48, 0.1);
  }
</style>
