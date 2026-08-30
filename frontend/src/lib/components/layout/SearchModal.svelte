<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { mediaApi, type Media } from '$lib/api/media';
  import { formatTime } from '$lib/utils/format';

  let { open = $bindable(false), onClose }: { open?: boolean; onClose?: () => void } = $props();

  let query = $state('');
  let results = $state<Media[]>([]);
  let loading = $state(false);
  let activeIndex = $state(0);
  let inputEl = $state<HTMLInputElement | null>(null);
  let abortCtrl: AbortController | null = null;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let searchSeq = 0;

  const hasQuery = $derived(query.trim().length > 0);

  async function runSearch(q: string): Promise<void> {
    const mySeq = ++searchSeq;
    if (abortCtrl) abortCtrl.abort();
    const trimmed = q.trim();
    if (!trimmed) {
      results = [];
      loading = false;
      return;
    }
    loading = true;
    abortCtrl = new AbortController();
    const signal = abortCtrl.signal;
    try {
      const res = await mediaApi.list({ q: trimmed, page: 1, page_size: 12 }, signal);
      if (mySeq !== searchSeq) return;
      results = res.items ?? [];
      activeIndex = 0;
    } catch (e) {
      if ((e as Error)?.name !== 'AbortError' && mySeq === searchSeq) {
        results = [];
      }
    } finally {
      if (mySeq === searchSeq) loading = false;
    }
  }

  function onInput(): void {
    if (debounceTimer) clearTimeout(debounceTimer);
    const q = query;
    debounceTimer = setTimeout(() => runSearch(q), 220);
  }

  function select(media: Media): void {
    goto(`/detail/${media.id}`);
    onClose?.();
  }

  function handleKeydown(e: KeyboardEvent): void {
    if (!open) return;
    if (e.key === 'Escape') {
      onClose?.();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, results.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
    } else if (e.key === 'Enter' && results[activeIndex]) {
      e.preventDefault();
      select(results[activeIndex]);
    }
  }

  $effect(() => {
    if (open) {
      query = '';
      results = [];
      activeIndex = 0;
      // 等待 DOM 渲染后聚焦
      queueMicrotask(() => inputEl?.focus());
    }
  });

  onMount(() => {
    window.addEventListener('keydown', handleKeydown);
  });
  onDestroy(() => {
    window.removeEventListener('keydown', handleKeydown);
    if (debounceTimer) clearTimeout(debounceTimer);
    if (abortCtrl) abortCtrl.abort();
  });
</script>

{#if open}
  <div
    class="overlay"
    role="presentation"
    onclick={() => onClose?.()}
    onkeydown={(e) => { if (e.key === 'Escape') onClose?.(); }}
  >
    <div
      class="modal"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      <div class="modal-head">
        <svg class="search-ico" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6">
          <circle cx="7" cy="7" r="5"></circle>
          <line x1="10.5" y1="10.5" x2="14" y2="14" stroke-linecap="round"></line>
        </svg>
        <input
          bind:this={inputEl}
          bind:value={query}
          oninput={onInput}
          class="modal-input"
          placeholder="搜索媒体"
          autocomplete="off"
          spellcheck="false"
        />
        <button class="esc" onclick={() => onClose?.()}>ESC</button>
      </div>

      <div class="modal-body">
        {#if loading}
          <div class="empty">搜索中…</div>
        {:else if hasQuery && results.length === 0}
          <div class="empty">没有找到匹配的媒体</div>
        {:else if !hasQuery}
          <div class="empty">输入关键词以搜索媒体</div>
        {:else}
          <ul class="result-list">
            {#each results as media, i}
              <li>
                <button
                  class="result"
                  class:active={i === activeIndex}
                  onclick={() => select(media)}
                  onmousemove={() => (activeIndex = i)}
                >
                  <div class="thumb">
                    {#if media.thumbnail}
                      <img src={mediaApi.thumbnailUrl(media.id, media.updated_at)} alt="" loading="lazy" />
                    {:else}
                      <span class="thumb-fallback">{media.type === 'video' ? '▶' : media.type === 'audio' ? '♪' : '▣'}</span>
                    {/if}
                  </div>
                  <div class="info">
                    <div class="title">{media.filename}</div>
                    <div class="meta">
                      <span>{media.type}</span>
                      {#if media.duration}<span>· {formatTime(media.duration)}</span>{/if}
                      {#if media.rating > 0}<span>· ★ {media.rating}</span>{/if}
                    </div>
                  </div>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <div class="modal-foot">
        <span><kbd>↑</kbd><kbd>↓</kbd> 导航</span>
        <span><kbd>↵</kbd> 打开</span>
        <span><kbd>ESC</kbd> 关闭</span>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.32);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 12vh;
    z-index: 1000;
    animation: fade 160ms ease;
  }

  @keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .modal {
    width: 560px;
    max-width: calc(100vw - 32px);
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.18);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    animation: pop 160ms ease;
  }

  @keyframes pop {
    from { transform: translateY(-8px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  .modal-head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
    border-bottom: 1px solid var(--rule);
  }

  .search-ico {
    color: var(--muted);
    flex-shrink: 0;
  }

  .modal-input {
    flex: 1;
    border: none;
    outline: none;
    background: none;
    font-size: 15px;
    color: var(--ink);
  }

  .esc {
    background: var(--bg-soft);
    border: 1px solid var(--rule);
    border-radius: 5px;
    padding: 2px 6px;
    font-size: 11px;
    color: var(--muted);
  }

  .modal-body {
    max-height: 420px;
    overflow-y: auto;
    padding: 6px;
  }

  .empty {
    padding: 36px 12px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }

  .result-list {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .result {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 8px;
    border: none;
    background: none;
    border-radius: var(--radius);
    text-align: left;
    transition: background 120ms;
  }

  .result:hover,
  .result.active {
    background: var(--accent-soft);
  }

  .thumb {
    width: 44px;
    height: 44px;
    border-radius: 6px;
    background: var(--bg-soft);
    overflow: hidden;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 18px;
  }

  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .info {
    flex: 1;
    min-width: 0;
  }

  .title {
    font-size: 13.5px;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .meta {
    display: flex;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
    margin-top: 2px;
  }

  .modal-foot {
    display: flex;
    gap: 16px;
    padding: 8px 14px;
    border-top: 1px solid var(--rule);
    font-size: 11.5px;
    color: var(--muted);
  }

  kbd {
    background: var(--bg-soft);
    border: 1px solid var(--rule);
    border-radius: 4px;
    padding: 0 4px;
    margin-right: 3px;
    font-family: inherit;
    font-size: 11px;
  }
</style>
