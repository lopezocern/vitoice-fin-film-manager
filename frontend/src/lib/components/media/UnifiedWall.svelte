<script lang="ts">
  import type { Media } from '$lib/api/media';
  import { mediaApi, isAvMedia, hasNetworkSource } from '$lib/api/media';
  import { imageFallback, seriesCoverFallback } from '$lib/utils/image-fallback';
  import type { Series } from '$lib/api/series';
  import { seriesApi } from '$lib/api/series';
  import { formatTime } from '$lib/utils/format';
  import { getProgress } from './types';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';

  /** A unified item is either a Series (aggregated TV show) or a standalone Media. */
  export type UnifiedItem =
    | { kind: 'series'; data: Series }
    | { kind: 'media'; data: Media };

  // ---- 图片比例分类（按实际宽高比统一展示，避免高低不齐）----
  // 宽图 → 3/2 横卡、竖图 → 2/3 竖卡、方图 → 1/1 方卡。
  // 无海报只有截图时也按截图自然比例归类（视频截图多为 16:9 横屏）。
  let posterRatio = $state<Record<string, string>>({});
  function onImageLoad(e: Event, m: Media): void {
    const img = e.currentTarget as HTMLImageElement;
    const r = img.naturalWidth / img.naturalHeight;
    if (!Number.isFinite(r) || r <= 0) return;
    let ar = '2 / 3';
    if (r > 1.05) ar = '4 / 3';
    else if (r >= 0.95) ar = '1 / 1';
    posterRatio[String(m.id)] = ar;
  }

  // 清理：items 变化时重置 posterRatio，防止内存泄漏（旧图片 id 累积）
  $effect(() => {
    // 读取 items 以建立依赖
    const _ = items.length;
    posterRatio = {};
  });

  let {
    items,
    onSelectSeries,
    onSelectMedia,
    mode = 'mixed',
    density = 180,
  }: {
    items: UnifiedItem[];
    onSelectSeries?: (s: Series) => void;
    onSelectMedia?: (m: Media) => void;
    mode?: 'mixed' | 'poster' | 'list' | 'timeline';
    density?: number;
  } = $props();

  const restrictedLibIds = $derived(
    new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id)))
  );

  function shouldMask(libraryId: string | number): boolean {
    return settingsStore.maskRestricted && restrictedLibIds.has(String(libraryId));
  }

  // 时间线模式：按年份分组（剧集取 series.year、独立媒体取 media.year，未知归"未知年份"，降序）
  const groups = $derived.by(() => {
    const grouped = new Map<string, UnifiedItem[]>();
    for (const item of items) {
      const year = item.kind === 'series' ? item.data.year : item.data.year;
      const key = year ? String(year) : 'unknown';
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(item);
    }
    return [...grouped.entries()]
      .sort(([a], [b]) => (a === 'unknown' ? 1 : b === 'unknown' ? -1 : Number(b) - Number(a)))
      .map(([key, list]) => ({ key, label: key === 'unknown' ? '未知年份' : `${key}年`, list }));
  });

  function itemKey(item: UnifiedItem): string {
    return item.kind + '-' + (item.kind === 'series' ? item.data.id : item.data.id);
  }
</script>

{#snippet unifiedCard(item: UnifiedItem)}
  {#if item.kind === 'series'}
    {@const s = item.data}
    <button class="card series-card" onclick={() => onSelectSeries?.(s)}>
      <div class="card-thumb">
        {#if s.poster_path}
          <img src={seriesApi.posterUrl(s.id)} alt={s.title} loading="lazy" />
        {:else}
          <div class="thumb-fallback">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <line x1="2" y1="8" x2="22" y2="8" />
              <polyline points="9,14 12,14 12,11" />
            </svg>
          </div>
        {/if}
        <span class="badge ep-count">{s.episode_count} 集</span>
        <span class="badge type-tag">剧集</span>
        {#if shouldMask(s.library_id)}
          <div class="content-mask" title="限制内容 — 点击查看">
            <span class="mask-icon">🔞</span>
          </div>
        {/if}
      </div>
      <div class="card-info">
        <div class="card-title" title={s.title}>{s.title}</div>
        <div class="card-meta">
          {#if s.year}<span class="muted">{s.year}</span>{/if}
          {#if s.total_seasons}<span class="muted">{s.total_seasons} 季</span>{/if}
        </div>
      </div>
    </button>
  {:else}
    {@const m = item.data}
    {@const p = getProgress(m.metadata)}
    {@const filled = Math.max(0, Math.min(5, m.rating))}
    {@const av = isAvMedia(m)}
    {@const usesSeriesCover = m.series_id != null}
    {@const hasImage = usesSeriesCover || !!m.poster || !!m.thumbnail}
    {@const ratioCls = hasImage ? posterRatio[String(m.id)] : undefined}
    {@const defaultRatio = usesSeriesCover || m.poster ? (av && !usesSeriesCover ? '4 / 3' : '2 / 3') : '4 / 3'}
    {@const ratioStr = mode === 'poster' ? '2 / 3' : (ratioCls ?? defaultRatio)}
    {@const isWide = !usesSeriesCover && (ratioCls === '4 / 3' || (!ratioCls && !m.poster && !!m.thumbnail))}
    <button
      class="card media-card"
      class:av-poster={!hasImage && av && mode !== 'poster'}
      class:wide={isWide && mode !== 'poster'}
      onclick={() => onSelectMedia?.(m)}
    >
      <div
        class="card-thumb"
        class:av-poster={av && mode !== 'poster'}
        class:has-poster={!!m.poster}
        style:aspect-ratio={hasImage ? ratioStr : undefined}
      >
        {#if usesSeriesCover}
          <img src={seriesApi.posterUrl(m.series_id!)} alt={m.series_title ?? m.title ?? m.filename} loading="lazy" onerror={(e) => seriesCoverFallback(e, m)} onload={(e) => onImageLoad(e, m)} />
        {:else if m.poster}
          <img src={mediaApi.posterUrl(m.id, m.updated_at)} alt={m.title ?? m.filename} loading="lazy" onerror={(e) => imageFallback(e, m)} onload={(e) => onImageLoad(e, m)} />
        {:else if m.thumbnail}
          <img src={mediaApi.thumbnailUrl(m.id, m.updated_at)} alt={m.filename} loading="lazy" onerror={(e) => imageFallback(e, m)} onload={(e) => onImageLoad(e, m)} />
        {:else}
          <div class="thumb-fallback">
            <span>{m.type === 'video' ? '▶' : m.type === 'audio' ? '♪' : '▣'}</span>
          </div>
        {/if}
        {#if m.duration}
          <span class="badge duration">{formatTime(m.duration)}</span>
        {/if}
        {#if !m.file_missing && (m.source_type === 'network' || m.source_type === 'both')}
          <span class="badge net-badge" title={m.source_type === 'both' ? '本地 + 网络源' : '网络媒体'}>
            {m.source_type === 'both' ? '本+网' : '网'}
          </span>
        {/if}
        {#if m.favorite}
          <span class="badge fav">♥</span>
        {/if}
        {#if m.file_missing}
          <span class="badge missing-badge" class:has-network={hasNetworkSource(m)} title={hasNetworkSource(m) ? '本地文件丢失 — 可从网络源播放' : '本地文件丢失'}>
            {hasNetworkSource(m) ? '🔗' : '⚠'}
          </span>
        {/if}
        {#if p > 0}
          <div class="progress"><div class="progress-fill" style="width:{p}%"></div></div>
        {/if}
        {#if shouldMask(m.library_id)}
          <div class="content-mask" title="限制内容 — 点击查看">
            <span class="mask-icon">🔞</span>
          </div>
        {/if}
      </div>
      <div class="card-info">
        <div class="card-title" title={m.title ?? m.filename}>{m.title ?? m.filename}</div>
        <div class="card-meta">
          {#if m.year}<span class="muted">{m.year}</span>{/if}
          {#if m.rating > 0}
            <span class="rating">{'★'.repeat(filled)}<span class="rating-dim">{'★'.repeat(5 - filled)}</span></span>
          {/if}
        </div>
      </div>
    </button>
  {/if}
{/snippet}

<div
  class="unified-view"
  class:poster-mode={mode === 'poster'}
  class:list-mode={mode === 'list'}
  class:timeline-mode={mode === 'timeline'}
  style={`--media-card-width:${density}px`}
>
  {#if mode === 'timeline'}
    {#each groups as group (group.key)}
      <section class="year-section">
        <div class="year-head"><strong>{group.label}</strong><span>{group.list.length} 项</span></div>
        <div class="unified-wall">
          {#each group.list as item (itemKey(item))}{@render unifiedCard(item)}{/each}
        </div>
      </section>
    {/each}
  {:else}
    <div class="unified-wall">
      {#each items as item (itemKey(item))}{@render unifiedCard(item)}{/each}
    </div>
  {/if}
</div>

<style>
  .unified-view { display: block; }

  .unified-wall {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--media-card-width, 180px), 1fr));
    grid-auto-flow: dense;
    gap: 16px;
    align-items: start;
  }

  .card {
    display: flex;
    flex-direction: column;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    overflow: hidden;
    padding: 0;
    cursor: pointer;
    text-align: left;
    transition: transform 200ms ease, box-shadow 200ms ease, border-color 200ms;
    /* Skip rendering/layout for off-screen cards */
    content-visibility: auto;
    contain-intrinsic-size: 180px 300px;
  }

  .card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    border-color: var(--accent);
  }

  /* AV (landscape) posters span 2 columns */
  .media-card.av-poster {
    grid-column: span 2;
  }

  /* 宽图封面（含非 AV 库的用户上传横图）跨 2 列大图展示，与 AV 海报统一 */
  .media-card.wide {
    grid-column: span 2;
  }

  .card-thumb {
    position: relative;
    aspect-ratio: 2 / 3;
    background: var(--bg-soft);
    overflow: hidden;
  }

  .card-thumb.av-poster {
    aspect-ratio: 4 / 3;
  }

  .card-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  /* Contain only for actual AV posters — video-frame thumbnails keep cover
     (no black bars on screenshots). */
  .card-thumb.av-poster.has-poster img {
    object-fit: contain;
  }

  /* ---- 海报模式：横图（视频截图/横版海报）右侧裁切展示——主体通常在
     画面右侧（与观看中心一致）；竖图/方图无横向裁切空间，不受影响 ---- */
  .unified-view.poster-mode .card-thumb img {
    object-position: right center;
  }

  .content-mask {
    position: absolute;
    inset: 0;
    z-index: 5;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: inherit;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
  }

  .mask-icon {
    font-size: 28px;
    opacity: 0.8;
  }

  .card:hover .content-mask {
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(3px);
    -webkit-backdrop-filter: blur(3px);
  }

  .thumb-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 32px;
    background: linear-gradient(135deg, var(--bg-soft), var(--bg2));
  }

  /* Badges on card thumbnails */
  .badge {
    position: absolute;
    background: rgba(0, 0, 0, 0.75);
    color: #fff;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    font-variant-numeric: tabular-nums;
  }

  .ep-count {
    bottom: 6px;
    right: 6px;
  }

  .type-tag {
    top: 6px;
    left: 6px;
    background: rgba(62, 214, 164, 0.86);
  }

  .net-badge {
    top: 6px;
    left: 6px;
    background: rgba(37, 99, 235, 0.88);
    font-weight: 600;
    font-size: 10.5px;
    padding: 1px 8px;
    border-radius: 999px;
  }

  .duration {
    bottom: 6px;
    right: 6px;
  }

  .fav {
    top: 6px;
    right: 6px;
    color: var(--accent2);
    background: none;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
    font-size: 14px;
  }

  .missing-badge {
    top: 6px;
    left: 6px;
    background: rgba(239, 68, 68, 0.85);
    width: 20px;
    height: 20px;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .missing-badge.has-network {
    background: rgba(62, 214, 164, 0.86);
  }

  .progress {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: rgba(255, 255, 255, 0.25);
  }

  .progress-fill {
    height: 100%;
    background: var(--accent);
  }

  .card-info {
    padding: 8px 10px 10px;
  }

  .card-title {
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    min-height: 2.7em;
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 5px;
    font-size: 11.5px;
  }

  .rating {
    color: var(--accent2);
    letter-spacing: 1px;
    font-size: 11px;
  }

  .rating-dim {
    color: var(--rule);
  }

  .muted {
    color: var(--muted);
  }

  /* ---- 海报模式：全部统一 2/3 竖卡，禁用横卡跨列 ---- */
  .unified-view.poster-mode .media-card.av-poster,
  .unified-view.poster-mode .media-card.wide {
    grid-column: auto;
  }

  /* ---- 列表模式（对齐 SeriesWall.list-mode）---- */
  .unified-view.list-mode .unified-wall {
    grid-template-columns: 1fr;
    gap: 7px;
  }

  .unified-view.list-mode .card {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr);
    min-height: 88px;
  }

  .unified-view.list-mode .media-card.av-poster,
  .unified-view.list-mode .media-card.wide {
    grid-column: auto;
  }

  .unified-view.list-mode .card-thumb { width: 64px; height: 88px; aspect-ratio: auto; }
  .unified-view.list-mode .card-thumb .badge { font-size: 10px; padding: 1px 5px; }
  .unified-view.list-mode .card-info { align-self: center; }
  .unified-view.list-mode .card-title { min-height: 0; -webkit-line-clamp: 1; line-clamp: 1; }

  /* ---- 时间线模式（对齐 SeriesWall.timeline-mode）---- */
  .unified-view.timeline-mode { display: flex; flex-direction: column; gap: 28px; }
  .year-section { display: flex; flex-direction: column; gap: 12px; }
  .year-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--rule);
    color: var(--ink);
  }
  .year-head strong { font-size: 15px; }
  .year-head span { color: var(--muted); font-size: 12px; }

  @media (max-width: 520px) {
    .unified-wall {
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 12px;
    }

    .media-card.av-poster {
      grid-column: span 1;
    }

    .card-thumb.av-poster {
      aspect-ratio: 4 / 3;
    }
  }
</style>
