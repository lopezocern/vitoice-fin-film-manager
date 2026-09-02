<script lang="ts">
  // 快速打标弹窗：从 tagsApi.list() 加载标签（含 tag_type_id 与 children），
  // 扁平化后按类型分组、支持搜索与多选；确认后对每个标签调用
  // POST /media/{mediaId}/tags { tag_id }（409 重复自动跳过）。
  import { onDestroy, untrack } from 'svelte';
  import { client } from '$lib/api/client';
  import { tagsApi } from '$lib/api/tags';

  interface TagNode {
    id: number;
    name: string;
    tag_type_id: number;
    color?: string | null;
    parent_id?: number | null;
    children?: TagNode[];
  }
  interface TagType {
    id: number;
    name: string;
    color: string;
    is_builtin?: boolean;
    sort_order?: number;
  }

  let {
    open = false,
    mediaId = '',
    preselectIds = [],
    onClose,
    onDone
  }: {
    open?: boolean;
    mediaId?: string;
    preselectIds?: number[];
    onClose?: () => void;
    onDone?: (addedCount: number) => void;
  } = $props();

  let tagTypes = $state<TagType[]>([]);
  let tags = $state<TagNode[]>([]);
  let loading = $state(false);
  let query = $state('');
  let selected = $state<Set<number>>(new Set());
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let resultMsg = $state<string | null>(null);
  let searchInput = $state<HTMLInputElement | null>(null);

  // 扁平化标签树
  const flatTags = $derived.by(() => {
    const out: TagNode[] = [];
    const walk = (nodes: TagNode[]) => {
      for (const n of nodes) {
        out.push(n);
        if (n.children?.length) walk(n.children);
      }
    };
    walk(tags);
    return out;
  });

  const filtered = $derived.by(() => {
    const q = query.trim().toLowerCase();
    if (!q) return flatTags;
    return flatTags.filter((t) => t.name.toLowerCase().includes(q));
  });

  // 按类型分组（保留过滤后的顺序）
  const grouped = $derived.by(() => {
    const map = new Map<number, TagNode[]>();
    for (const t of filtered) {
      const arr = map.get(t.tag_type_id) ?? [];
      arr.push(t);
      map.set(t.tag_type_id, arr);
    }
    return map;
  });

  const sortedTypeIds = $derived.by(() => {
    const ids = Array.from(grouped.keys());
    return ids.sort((a, b) => {
      const oa = tagTypes.find((t) => t.id === a)?.sort_order ?? 0;
      const ob = tagTypes.find((t) => t.id === b)?.sort_order ?? 0;
      return oa - ob;
    });
  });

  function typeName(id: number): string {
    return tagTypes.find((t) => t.id === id)?.name ?? '其他';
  }
  function typeColor(id: number): string {
    return tagTypes.find((t) => t.id === id)?.color ?? 'var(--neutral)';
  }

  async function load(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [types, tgs] = await Promise.all([
        client.get<TagType[]>('/tag-types').catch(() => [] as TagType[]),
        tagsApi.list() as unknown as Promise<TagNode[]>
      ]);
      tagTypes = (types as TagType[]) ?? [];
      tags = (tgs as TagNode[]) ?? [];
    } catch {
      error = '加载标签失败，请检查后端服务';
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    if (open) {
      query = '';
      selected = new Set(preselectIds);
      resultMsg = null;
      error = null;
      // untrack：load 的同步部分可能读写 $state，避免被追踪进 effect 依赖面
      untrack(() => void load());
      queueMicrotask(() => searchInput?.focus());
    }
  });

  // 提交成功后延迟 900ms 自动关闭。若在窗口期内组件已卸载（用户按 ESC 或
  // 退出播放器），回调仍会触发 onClose —— 持句柄并在 onDestroy 清理。
  let closeTimer: ReturnType<typeof setTimeout> | null = null;

  /** 统一关闭入口：清掉待触发的自动关闭，避免二次回调 */
  function close(): void {
    if (closeTimer) {
      clearTimeout(closeTimer);
      closeTimer = null;
    }
    onClose?.();
  }

  onDestroy(() => {
    if (closeTimer) {
      clearTimeout(closeTimer);
      closeTimer = null;
    }
  });

  function toggle(id: number): void {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
  }

  async function confirm(): Promise<void> {
    if (!selected.size || submitting) return;
    submitting = true;
    error = null;
    let added = 0;
    let skipped = 0;
    const ids = Array.from(selected);
    await Promise.all(
      ids.map(async (tagId) => {
        try {
          await client.post(`/media/${mediaId}/tags`, { tag_id: tagId });
          added++;
        } catch {
          // 409 = 已存在，计入跳过
          skipped++;
        }
      })
    );
    submitting = false;
    resultMsg = `已添加 ${added} 个标签${skipped ? `（${skipped} 个已存在）` : ''}`;
    onDone?.(added);
    if (closeTimer) clearTimeout(closeTimer);
    closeTimer = setTimeout(() => {
      closeTimer = null;
      onClose?.();
    }, 900);
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  }
</script>

<svelte:window onkeydown={open ? onKeydown : undefined} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="overlay" onclick={close} role="presentation">
    <!-- svelte-ignore a11y_interactive_supports_focus a11y_click_events_have_key_events -->
    <div
      class="dialog"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label="快速打标"
    >
      <div class="head">
        <h3>快速打标</h3>
        <button class="x" onclick={close} aria-label="关闭">×</button>
      </div>

      <div class="search">
        <input
          bind:this={searchInput}
          type="text"
          bind:value={query}
          placeholder="搜索标签…"
        />
        {#if selected.size > 0}
          <span class="count">{selected.size} 已选</span>
        {/if}
      </div>

      <div class="list">
        {#if loading}
          <div class="state">加载中…</div>
        {:else if error}
          <div class="state err">{error}</div>
        {:else if flatTags.length === 0}
          <div class="state">暂无标签，请先在设置中创建</div>
        {:else if filtered.length === 0}
          <div class="state">没有匹配 “{query}” 的标签</div>
        {:else}
          {#each sortedTypeIds as tid (tid)}
            <div class="group">
              <div class="group-head">
                <span class="dot" style={`background:${typeColor(tid)}`}></span>
                <span>{typeName(tid)}</span>
                <span class="muted">{grouped.get(tid)?.length ?? 0}</span>
              </div>
              <div class="chips">
                {#each grouped.get(tid) ?? [] as tag (tag.id)}
                  <button
                    class="tag-chip"
                    class:active={selected.has(tag.id)}
                    style={tag.color && !selected.has(tag.id) ? `--c:${tag.color}` : ''}
                    onclick={() => toggle(tag.id)}
                    type="button"
                  >
                    <span class="dot" style={`background:${tag.color ?? typeColor(tid)}`}></span>
                    <span class="name">{tag.name}</span>
                    {#if selected.has(tag.id)}<span class="check">✓</span>{/if}
                  </button>
                {/each}
              </div>
            </div>
          {/each}
        {/if}
      </div>

      {#if resultMsg}
        <div class="result">{resultMsg}</div>
      {/if}

      <div class="actions">
        <button class="btn ghost" onclick={close} disabled={submitting} type="button">取消</button>
        <button class="btn primary" onclick={confirm} disabled={!selected.size || submitting} type="button">
          {submitting ? '添加中…' : `添加 ${selected.size || ''} 个标签`.trim()}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    animation: fade 150ms ease;
  }
  @keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .dialog {
    width: min(520px, 92vw);
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    background: var(--bg2);
    color: var(--ink);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
    overflow: hidden;
    animation: pop 160ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  @keyframes pop {
    from { opacity: 0; transform: translateY(8px) scale(0.98); }
    to { opacity: 1; transform: none; }
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px 10px;
  }
  .head h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 700;
  }
  .x {
    border: none;
    background: none;
    font-size: 20px;
    line-height: 1;
    color: var(--muted);
    width: 28px;
    height: 28px;
    border-radius: var(--radius);
    transition: background 150ms, color 150ms;
  }
  .x:hover {
    background: var(--bg-soft);
    color: var(--ink);
  }

  .search {
    position: relative;
    padding: 0 20px 12px;
  }
  .search input {
    width: 100%;
    height: 36px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 150ms;
  }
  .search input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }
  .count {
    position: absolute;
    right: 30px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 11.5px;
    color: var(--accent);
    background: var(--accent-soft);
    padding: 2px 8px;
    border-radius: var(--radius-full);
    pointer-events: none;
  }

  .list {
    flex: 1;
    overflow-y: auto;
    padding: 4px 20px 12px;
  }
  .state {
    padding: 40px 0;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }
  .state.err {
    color: #ff3b30;
  }

  .group {
    margin-bottom: 14px;
  }
  .group-head {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 8px;
  }
  .group-head .muted {
    color: var(--neutral);
    font-weight: 400;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .chips {
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
    border-radius: var(--radius-full);
    background: var(--bg2);
    color: var(--ink);
    font-size: 12.5px;
    transition: all 150ms;
    cursor: pointer;
  }
  .tag-chip:hover {
    border-color: var(--muted);
  }
  .tag-chip.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }
  .tag-chip .name {
    white-space: nowrap;
  }
  .tag-chip .check {
    font-size: 11px;
  }

  .result {
    padding: 8px 20px;
    font-size: 12.5px;
    color: var(--ok);
    background: var(--ok-soft);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 12px 20px 16px;
    border-top: 1px solid var(--rule);
  }
  .btn {
    height: 34px;
    padding: 0 16px;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 500;
    transition: all 150ms;
  }
  .btn.ghost {
    background: var(--bg-soft);
    color: var(--ink);
    border: 1px solid var(--rule);
  }
  .btn.ghost:hover {
    background: var(--bg);
  }
  .btn.primary {
    background: var(--accent);
    color: #fff;
    border: none;
  }
  .btn.primary:hover:not(:disabled) {
    filter: brightness(1.06);
  }
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
