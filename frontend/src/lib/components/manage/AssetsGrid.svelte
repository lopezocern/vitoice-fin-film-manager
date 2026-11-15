<script lang="ts">
  // 资产网格 — 唯一列表层的卡片皮肤。
  // 与表格共用同一份 items / 选中集 / 事件，只换布局（决策 4 后仍然只有一套数据流）。
  import { mediaApi, type Media } from '$lib/api/media';
  import { imageFallback } from '$lib/utils/image-fallback';
  import { formatDuration, formatSize } from '$lib/utils/format';
  import { mediaStateChips } from '$lib/media/status';

  let {
    items = [],
    selected = new Set<number>(),
    loading = false,
    onToggle,
    onOpen,
    onEdit,
    onIgnore
  }: {
    items?: Media[];
    selected?: Set<number>;
    loading?: boolean;
    onToggle: (id: string) => void;
    onOpen: (media: Media) => void;
    onEdit: (media: Media) => void;
    onIgnore: (media: Media) => void;
  } = $props();

  function thumbSrc(media: Media): string | null {
    if (media.poster) return mediaApi.posterUrl(media.id, media.updated_at);
    if (media.thumbnail) return mediaApi.thumbnailUrl(media.id, media.updated_at);
    return null;
  }

  const TYPE_ICON: Record<string, string> = { video: '▶', audio: '♪', image: '▣' };
</script>

<div class="grid" class:busy={loading}>
  {#each items as media (media.id)}
    {@const id = Number(media.id)}
    {@const chips = mediaStateChips(media)}
    {@const src = thumbSrc(media)}
    <article class="card" class:selected={selected.has(id)}>
      <label class="pick" title="选择">
        <input
          type="checkbox"
          checked={selected.has(id)}
          onchange={() => onToggle(media.id)}
          aria-label={`选择 ${media.title ?? media.filename}`}
        />
      </label>

      <button type="button" class="cover" onclick={() => onOpen(media)} title="查看详情">
        {#if src}
          <img {src} alt="" loading="lazy" onerror={(e) => imageFallback(e, media)} />
        {:else}
          <span class="fb">{TYPE_ICON[media.type] ?? '▶'}</span>
        {/if}
        <span class="badge {chips.file.tone}">{chips.file.label}</span>
      </button>

      <div class="body">
        <button type="button" class="title" onclick={() => onOpen(media)} title={media.title}>
          {media.title ?? media.filename}
        </button>
        <div class="meta">
          {#if media.year}<span>{media.year}</span>{/if}
          {#if media.duration}<span>{formatDuration(media.duration)}</span>{/if}
          {#if media.size}<span>{formatSize(media.size)}</span>{/if}
          <span class="state {chips.metadata.tone}">{chips.metadata.label}</span>
        </div>
        <div class="foot">
          {#if media.rating}
            <span class="stars" title={`评分 ${media.rating}`}>
              {'★'.repeat(Math.max(0, Math.min(5, media.rating)))}
            </span>
          {:else}
            <span class="muted">未评分</span>
          {/if}
          <button type="button" class="act" title="编辑标题/年份/简介/封面" onclick={() => onEdit(media)}>
            编辑
          </button>
          <button
            type="button"
            class="act"
            title={media.metadata_ignored ? '恢复刮削' : '忽略刮削'}
            onclick={() => onIgnore(media)}
          >
            {media.metadata_ignored ? '恢复' : '忽略'}
          </button>
        </div>
      </div>
    </article>
  {/each}

  {#if items.length === 0 && !loading}
    <div class="empty">
      <p>这个视图下没有条目</p>
      <p class="hint">换个视图，或清除筛选条件</p>
    </div>
  {/if}
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 12px;
    padding: 12px 16px 20px;
  }
  .card {
    position: relative;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    background: var(--bg-elevated);
    overflow: hidden;
    transition:
      border-color var(--dur-fast) var(--ease-out),
      transform var(--dur-fast) var(--ease-out);
  }
  .card:hover {
    border-color: var(--ink-faint);
    transform: translateY(-1px);
  }
  .card.selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent) inset;
  }
  .pick {
    position: absolute;
    top: 6px;
    left: 6px;
    z-index: 2;
    display: flex;
    padding: 3px;
    border-radius: var(--radius-xs);
    background: color-mix(in srgb, var(--bg) 72%, transparent);
    cursor: pointer;
  }
  .cover {
    position: relative;
    display: block;
    width: 100%;
    aspect-ratio: 2 / 3;
    padding: 0;
    border: none;
    background: var(--bg-surface);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .cover img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .cover .fb {
    color: var(--ink-faint);
    font-size: 22px;
  }
  .badge {
    position: absolute;
    left: 6px;
    bottom: 6px;
    font-size: 10.5px;
    padding: 1px 6px;
    border-radius: var(--radius-full);
    background: color-mix(in srgb, var(--bg) 82%, transparent);
    color: var(--ink-secondary);
    white-space: nowrap;
  }
  .badge.danger {
    color: var(--danger);
  }
  .badge.ok {
    color: var(--ink-tertiary);
  }
  .body {
    padding: 7px 8px 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .title {
    font: inherit;
    font-size: 12.5px;
    text-align: left;
    padding: 0;
    border: none;
    background: none;
    color: var(--ink);
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .title:hover {
    color: var(--accent);
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    font-size: 11px;
    color: var(--ink-tertiary);
  }
  .state.warn {
    color: var(--warn);
  }
  .state.danger {
    color: var(--danger);
  }
  .foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    margin-top: 2px;
  }
  .stars {
    color: var(--warn);
    font-size: 11px;
    letter-spacing: 1px;
  }
  .muted {
    color: var(--ink-faint);
    font-size: 11px;
  }
  .act {
    font: inherit;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--ink-tertiary);
    cursor: pointer;
  }
  .act:hover {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .busy {
    opacity: 0.55;
  }
  .empty {
    grid-column: 1 / -1;
    padding: 48px 0;
    text-align: center;
    color: var(--ink-tertiary);
  }
  .empty p {
    margin: 0;
  }
  .empty .hint {
    margin-top: 6px;
    font-size: 12.5px;
    color: var(--ink-faint);
  }
</style>
