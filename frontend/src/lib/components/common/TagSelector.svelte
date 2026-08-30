<script lang="ts">
  // 标签选择器弹窗
  // - 按类型分组显示标签（Tag 接口无 type 字段时归入"通用"组；若 tag 上存在 metadata.type 或自定义 type 字段，则按其分组）
  // - 支持搜索
  // - 多选/单选模式
  // - 确认后 onselect 回调返回 tagIds

  import type { Tag } from '$lib/api/tags';

  let {
    open = $bindable(false),
    tags = [],
    selected = [],
    multiple = true,
    title = '选择标签',
    onselect,
    oncancel
  }: {
    open?: boolean;
    tags?: Tag[];
    selected?: string[];
    multiple?: boolean;
    title?: string;
    onselect?: (tagIds: string[]) => void;
    oncancel?: () => void;
  } = $props();

  let query = $state('');
  let local = $state<string[]>([]);

  // 当弹窗打开时同步外部 selected
  $effect(() => {
    if (open) {
      local = [...selected];
      query = '';
    }
  });

  // 读取标签的分组类型。Tag 接口没有 type 字段，这里允许从 (tag as any).type 读取扩展信息，
  // 没有则归入 "通用" 组。
  function tagType(t: Tag): string {
    const ext = t as Tag & { type?: string; category?: string };
    return ext.type ?? ext.category ?? '通用';
  }

  const filtered = $derived(
    query.trim()
      ? tags.filter((t) => t.name.toLowerCase().includes(query.trim().toLowerCase()))
      : tags
  );

  // 按 type 分组
  const groups = $derived.by(() => {
    const map = new Map<string, Tag[]>();
    for (const t of filtered) {
      const g = tagType(t);
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(t);
    }
    return Array.from(map.entries()).map(([name, items]) => ({ name, items }));
  });

  function toggle(id: string): void {
    if (multiple) {
      local = local.includes(id) ? local.filter((x) => x !== id) : [...local, id];
    } else {
      local = local.includes(id) ? [] : [id];
    }
  }

  function isSelected(id: string): boolean {
    return local.includes(id);
  }

  function handleConfirm(): void {
    onselect?.(local);
  }

  function handleCancel(): void {
    oncancel?.();
  }

  function handleBackdrop(e: MouseEvent): void {
    if (e.target === e.currentTarget) handleCancel();
  }

  function handleKeydown(e: KeyboardEvent): void {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleConfirm();
    }
  }

  const totalSelected = $derived(local.length);
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
  <div class="backdrop" onclick={handleBackdrop} onkeydown={(e) => { if (e.key === 'Escape') handleCancel(); }} role="presentation">
    <div
      class="dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tag-selector-title"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
    >
      <div class="dialog-head">
        <h2 id="tag-selector-title">{title}</h2>
        <button class="close-btn" onclick={handleCancel} aria-label="关闭">×</button>
      </div>

      <div class="search-wrap">
        <svg class="search-icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
          <path d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z" fill="currentColor" />
        </svg>
        <input
          type="text"
          class="search-input"
          placeholder="搜索标签..."
          bind:value={query}
        />
        {#if query}
          <button class="clear-search" onclick={() => (query = '')} aria-label="清除搜索">×</button>
        {/if}
      </div>

      <div class="dialog-body">
        {#if groups.length === 0}
          <div class="empty">
            {#if query}
              <div class="empty-text">没有匹配 "{query}" 的标签</div>
            {:else}
              <div class="empty-text">暂无可用标签</div>
            {/if}
          </div>
        {:else}
          {#each groups as group (group.name)}
            <div class="group">
              <div class="group-head">
                <span class="group-name">{group.name}</span>
                <span class="group-count">{group.items.length}</span>
              </div>
              <div class="group-items">
                {#each group.items as tag (tag.id)}
                  <button
                    type="button"
                    class="tag-chip"
                    class:active={isSelected(tag.id)}
                    onclick={() => toggle(tag.id)}
                  >
                    {#if tag.color}
                      <span class="tag-dot" style="background:{tag.color}"></span>
                    {/if}
                    <span class="tag-name">{tag.name}</span>
                    {#if tag.count != null}
                      <span class="tag-count">{tag.count}</span>
                    {/if}
                    {#if isSelected(tag.id)}
                      <span class="check">✓</span>
                    {/if}
                  </button>
                {/each}
              </div>
            </div>
          {/each}
        {/if}
      </div>

      <div class="dialog-foot">
        <div class="selected-info">
          {#if multiple}
            已选 <strong>{totalSelected}</strong> 个标签
          {:else}
            {#if totalSelected > 0}已选 1 个标签{:else}未选择{/if}
          {/if}
        </div>
        <div class="actions">
          <button class="btn btn-cancel" onclick={handleCancel}>取消</button>
          <button class="btn btn-primary" onclick={handleConfirm} disabled={totalSelected === 0}>
            确认
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.32);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fade 200ms ease;
  }

  @keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .dialog {
    width: 100%;
    max-width: 560px;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    background: var(--bg2);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
    overflow: hidden;
    animation: pop 200ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  @keyframes pop {
    from { opacity: 0; transform: translateY(-8px) scale(0.96); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .dialog-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 20px 12px;
  }

  .dialog-head h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
  }

  .close-btn {
    width: 26px;
    height: 26px;
    border: none;
    background: none;
    border-radius: var(--radius-full);
    color: var(--muted);
    font-size: 20px;
    line-height: 1;
    transition: background 200ms;
  }

  .close-btn:hover {
    background: var(--bg-soft);
    color: var(--ink);
  }

  .search-wrap {
    position: relative;
    padding: 0 20px 12px;
    display: flex;
    align-items: center;
  }

  .search-icon {
    position: absolute;
    left: 32px;
    color: var(--muted);
    pointer-events: none;
  }

  .search-input {
    width: 100%;
    height: 34px;
    padding: 0 32px 0 32px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 200ms;
  }

  .search-input:focus {
    outline: none;
    border-color: var(--accent);
  }

  .clear-search {
    position: absolute;
    right: 28px;
    width: 18px;
    height: 18px;
    border: none;
    background: var(--bg-soft);
    border-radius: var(--radius-full);
    color: var(--muted);
    font-size: 13px;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .clear-search:hover {
    background: var(--rule);
    color: var(--ink);
  }

  .dialog-body {
    flex: 1;
    overflow-y: auto;
    padding: 0 20px 12px;
  }

  .empty {
    padding: 48px 0;
    text-align: center;
  }

  .empty-text {
    color: var(--muted);
    font-size: 13px;
  }

  .group {
    margin-bottom: 16px;
  }

  .group:last-child {
    margin-bottom: 0;
  }

  .group-head {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 0 8px;
  }

  .group-name {
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .group-count {
    font-size: 11px;
    color: var(--neutral);
    background: var(--bg-soft);
    padding: 0 6px;
    border-radius: var(--radius-full);
  }

  .group-items {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .tag-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    background: var(--bg2);
    border-radius: var(--radius-full);
    color: var(--ink);
    font-size: 12.5px;
    transition: all 200ms ease;
  }

  .tag-chip:hover {
    border-color: var(--muted);
    background: var(--bg-soft);
  }

  .tag-chip.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
  }

  .tag-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background: var(--neutral);
  }

  .tag-count {
    color: var(--muted);
    font-size: 11px;
  }

  .tag-chip.active .tag-count {
    color: var(--accent);
  }

  .check {
    color: var(--accent);
    font-size: 12px;
    font-weight: bold;
  }

  .dialog-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px 16px;
    border-top: 1px solid var(--rule);
  }

  .selected-info {
    font-size: 12.5px;
    color: var(--muted);
  }

  .selected-info strong {
    color: var(--accent);
    font-weight: 600;
  }

  .actions {
    display: flex;
    gap: 8px;
  }

  .btn {
    height: 32px;
    padding: 0 14px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .btn:hover:not(:disabled) {
    border-color: var(--muted);
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-cancel {
    background: var(--bg-soft);
  }

  .btn-primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .btn-primary:hover:not(:disabled) {
    filter: brightness(1.08);
  }
</style>
