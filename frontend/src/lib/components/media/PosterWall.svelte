<script lang="ts">
  import type { Media } from '$lib/api/media';
  import { mediaApi, isAvMedia, hasNetworkSource } from '$lib/api/media';
  import { imageFallback, seriesCoverFallback } from '$lib/utils/image-fallback';
  import { seriesApi } from '$lib/api/series';
  import { formatTime } from '$lib/utils/format';
  import { getProgress } from './types';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import ContactSheetLightbox from './ContactSheetLightbox.svelte';

  let {
    items,
    onSelect,
    onplay,
    mode = 'mixed',
    density = 180
  }: {
    items: Media[];
    onSelect?: (media: Media) => void;
    /** 点击封面图直接播放（进播放器） */
    onplay?: (media: Media) => void;
    mode?: 'mixed' | 'poster';
    density?: number;
  } = $props();

  // 受限媒体库 ID 集合
  const restrictedLibIds = $derived(
    new Set(librariesStore.libraries.filter(l => l.is_restricted).map(l => String(l.id)))
  );

  // 缩略图集灯箱
  let csOpen = $state(false);
  let csViewer = $state<{ id: string; title: string; version: string } | null>(null);
  function openContactSheet(media: { id: string; has_contact_sheet?: boolean; title?: string; filename?: string; updated_at?: string }): void {
    if (!media.has_contact_sheet) return;
    csViewer = {
      id: String(media.id),
      title: media.title ?? media.filename ?? '缩略图集',
      version: String(media.updated_at ?? '')
    };
    csOpen = true;
  }

  function shouldMask(media: Media): boolean {
    return settingsStore.maskRestricted && restrictedLibIds.has(String(media.library_id));
  }

  // ---- 图片比例分类（按实际宽高比统一展示，避免高低不齐） ----
  // 宽图 → 3/2 横卡、竖图 → 2/3 竖卡、方图 → 1/1 方卡。
  // 有海报按海报比例；无海报只有截图时也按截图自然比例归类——
  // 视频截图多为 16:9 横屏,加载前默认 3/2 横卡,加载后按实际比例修正
  // (竖屏截图会自动变为 2/3 竖卡)。
  const posterRatio = $state<Record<string, string>>({});
  function onImageLoad(e: Event, media: Media): void {
    const img = e.currentTarget as HTMLImageElement;
    const r = img.naturalWidth / img.naturalHeight;
    if (!Number.isFinite(r) || r <= 0) return;
    let ar = '2 / 3';
    if (r > 1.05) ar = '4 / 3';
    else if (r >= 0.95) ar = '1 / 1';
    posterRatio[String(media.id)] = ar;
  }

  // 桌面应用（Windows/macOS）：一次性渲染全部 items。
  // 之前 200/步的增量渲染会导致：①返回时锚点卡片可能未渲染，滚动位置恢复偏；
  // ②时间轴等分组里 >200 条的组只显示前 200 条（"年份缺媒体"）。
  // 桌面端 DOM 承受能力足够，直接全量渲染最可靠。
</script>

<div class="poster-wall" class:poster-mode={mode === 'poster'} style={`--media-card-width:${density}px`}>
  {#each items as media (media.id)}
  {@const p = getProgress(media.metadata)}
  {@const filled = Math.max(0, Math.min(5, media.rating))}
  {@const av = isAvMedia(media)}
  {@const usesSeriesCover = media.series_id != null}
  {@const hasImage = usesSeriesCover || !!media.poster || !!media.thumbnail}
  {@const ratioCls = hasImage ? posterRatio[String(media.id)] : undefined}
  {@const defaultRatio = usesSeriesCover || media.poster ? (av && !usesSeriesCover ? '4 / 3' : '2 / 3') : '4 / 3'}
  {@const ratioStr = mode === 'poster' ? '2 / 3' : (ratioCls ?? defaultRatio)}
  {@const isWide = !usesSeriesCover && mode === 'mixed' && (ratioCls === '4 / 3' || (!ratioCls && !media.poster && !!media.thumbnail))}
  <button
    class="poster"
    data-id={media.id}
    class:av-poster={!hasImage && av}
    class:wide={isWide}
  >
    <div
      class="poster-thumb"
      class:av-poster={av}
      class:has-poster={!!media.poster}
      style:aspect-ratio={hasImage ? ratioStr : undefined}
      class:playable={onplay && media.type !== 'image'}
      onclick={(e) => {
        e.stopPropagation();
        if (media.type !== 'image') onplay?.(media);
      }}
      title={media.type !== 'image' ? '点击封面播放' : '查看详情'}
    >
      {#if usesSeriesCover}
        <img src={seriesApi.posterUrl(media.series_id!)} alt={media.series_title ?? media.title ?? media.filename} loading="lazy" onerror={(e) => seriesCoverFallback(e, media)} onload={(e) => onImageLoad(e, media)} />
      {:else if media.poster}
        <img src={mediaApi.posterUrl(media.id, media.updated_at)} alt={media.title ?? media.filename} loading="lazy" onerror={(e) => imageFallback(e, media)} onload={(e) => onImageLoad(e, media)} />
      {:else if media.thumbnail}
        <img src={mediaApi.thumbnailUrl(media.id, media.updated_at)} alt={media.filename} loading="lazy" onerror={(e) => imageFallback(e, media)} onload={(e) => onImageLoad(e, media)} />
      {:else}
        <div class="thumb-fallback">
          <span>{media.type === 'video' ? '▶' : media.type === 'audio' ? '♪' : '▣'}</span>
        </div>
      {/if}
      {#if media.duration}
        <span class="duration">{formatTime(media.duration)}</span>
      {/if}
      <span
        class="cs-entry"
        class:disabled={!media.has_contact_sheet}
        title={media.has_contact_sheet ? '查看缩略图集' : '未生成缩略图集'}
        role="button"
        tabindex="-1"
        onclick={(e) => { e.stopPropagation(); openContactSheet(media); }}
      >
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8">
          <rect x="3" y="3" width="8" height="8" rx="1" />
          <rect x="13" y="3" width="8" height="8" rx="1" />
          <rect x="3" y="13" width="8" height="8" rx="1" />
          <rect x="13" y="13" width="8" height="8" rx="1" />
        </svg>
      </span>
      {#if !media.file_missing && (media.source_type === 'network' || media.source_type === 'both')}
        <span class="net-badge" title={media.source_type === 'both' ? '本地 + 网络源' : '网络媒体'}>
          {media.source_type === 'both' ? '本+网' : '网'}
        </span>
      {/if}
      {#if media.favorite}
        <span class="fav">♥</span>
      {/if}
      {#if media.file_missing}
        <span class="missing-badge" class:has-network={hasNetworkSource(media)} title={hasNetworkSource(media) ? '本地文件丢失 — 可从网络源播放' : '本地文件丢失'}>
          {hasNetworkSource(media) ? '🔗' : '⚠'}
        </span>
      {/if}
      {#if p > 0}
        <div class="progress"><div class="progress-fill" style="width:{p}%"></div></div>
      {/if}
      {#if shouldMask(media)}
        <div class="content-mask" title="限制内容 — 点击查看">
          <span class="mask-icon">🔞</span>
        </div>
      {/if}
      {#if onplay && media.type !== 'image'}
        <span class="play-hint" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
        </span>
      {/if}
    </div>
    <div class="poster-info" onclick={() => onSelect?.(media)} title="查看详情">
      <div class="poster-title" title={media.title ?? media.filename}>{media.title ?? media.filename}</div>
      <div class="poster-meta">
        {#if media.year}<span class="muted">{media.year}</span>{/if}
        {#if media.rating > 0}
          <span class="rating">{'★'.repeat(filled)}<span class="rating-dim">{'★'.repeat(5 - filled)}</span></span>
        {/if}
        {#if media.type}<span class="muted">{media.type}</span>{/if}
      </div>
    </div>
  </button>
  {/each}
</div>

<ContactSheetLightbox bind:open={csOpen} mediaId={csViewer?.id ?? null} title={csViewer?.title} version={csViewer?.version} />

<style>
  .poster-wall {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--media-card-width, 180px), 1fr));
    grid-auto-flow: dense;
    gap: 16px;
    align-items: start;
  }

  .poster {
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
    contain-intrinsic-size: 180px 280px;
  }

  .poster:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    border-color: var(--accent);
  }

  /* AV (landscape) posters span 2 columns for a larger, proportional display.
     Only applies when there's NO poster image (thumbnail fallback) — with a
     poster, the span is driven by the actual image ratio (.poster.wide below),
     so a square custom cover doesn't get stretched across two columns and a
     landscape cover in a non-AV library still gets the wide layout. */
  .poster.av-poster {
    grid-column: span 2;
  }

  /* 宽图封面（自然比例 > 1.05，含 AV 刮削横图与用户上传横图）跨 2 列大图展示，
     与 AV 海报统一——避免"同是宽图、一个跨列大图、一个单列小图"的不一致。 */
  .poster.wide {
    grid-column: span 2;
  }

  .poster-wall.poster-mode .poster,
  .poster-wall.poster-mode .poster.av-poster,
  .poster-wall.poster-mode .poster.wide {
    grid-column: span 1;
  }

  .poster-thumb {
    position: relative;
    aspect-ratio: 2 / 3;
    background: var(--bg-soft);
    overflow: hidden;
  }

  /* AV covers from JavBus are landscape (roughly 4:3); use a wider ratio so
     the full cover is visible without excessive cropping. When AV falls back
     to a video-frame thumbnail, the inline aspect-ratio (natural ratio of the
     screenshot) overrides this default. */
  .poster-thumb.av-poster {
    aspect-ratio: 4 / 3;
  }

  .poster-wall.poster-mode .poster-thumb {
    aspect-ratio: 2 / 3 !important;
  }

  .poster-thumb {
    cursor: pointer;
  }

  /* 封面 hover 播放提示 */
  .play-hint {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.45);
    color: #fff;
    opacity: 0;
    transition: opacity 160ms ease;
    pointer-events: none;
  }

  .poster-thumb:hover .play-hint {
    opacity: 1;
  }

  .poster-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  /* For AV posters, use contain so the full landscape cover is visible
     instead of cropping the sides. Only applies when there IS a poster —
     when falling back to a video-frame thumbnail we keep cover (no black
     bars on the screenshot). */
  .poster-thumb.av-poster.has-poster img {
    object-fit: contain;
  }

  /* 海报墙模式：统一 2/3 竖卡，横图（视频截图 / AV 横版海报）一律
     cover + 右侧裁切——主体通常在画面右侧（与观看中心一致），
     竖图/方图不受影响（无横向裁切空间）。 */
  .poster-wall.poster-mode .poster-thumb img {
    object-fit: cover;
    object-position: right center;
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

  .duration {
    position: absolute;
    bottom: 6px;
    right: 30px; /* 左移给右下角缩略图集入口让位 */
    background: rgba(0, 0, 0, 0.7);
    color: #fff;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    font-variant-numeric: tabular-nums;
  }

  /* 右下角缩略图集入口：有缩略图集 → 点击灯箱展示；无 → 置灰 */
  .cs-entry {
    position: absolute;
    bottom: 6px;
    right: 6px;
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.65);
    color: #fff;
    border-radius: 5px;
    cursor: pointer;
    transition: background 140ms ease, color 140ms ease;
    z-index: 4;
  }
  .cs-entry:hover { background: var(--accent); color: #061812; }
  .cs-entry.disabled { opacity: 0.35; cursor: default; }
  .cs-entry.disabled:hover { background: rgba(0, 0, 0, 0.65); color: #fff; }

  .net-badge {
    position: absolute;
    top: 6px;
    left: 6px;
    background: rgba(37, 99, 235, 0.85);
    color: #fff;
    font-size: 10.5px;
    font-weight: 600;
    padding: 1px 7px;
    border-radius: 999px;
    letter-spacing: 0.3px;
  }

  .fav {
    position: absolute;
    top: 6px;
    right: 6px;
    color: var(--accent2);
    font-size: 14px;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
  }

  .missing-badge {
    position: absolute;
    top: 6px;
    left: 6px;
    background: rgba(239, 68, 68, 0.85);
    color: #fff;
    font-size: 11px;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
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

  .poster-info {
    padding: 8px 10px 10px;
    cursor: pointer;
  }

  .poster-title {
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

  .poster-meta {
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

  .content-mask {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 5;
    border-radius: inherit;
  }

  .mask-icon {
    font-size: 28px;
    opacity: 0.8;
  }

  .poster:hover .content-mask {
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(3px);
    -webkit-backdrop-filter: blur(3px);
  }

  @media (max-width: 520px) {
    .poster-wall {
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 12px;
    }

    /* On very narrow screens, AV posters don't span 2 cols (not enough space). */
    .poster.av-poster {
      grid-column: span 1;
    }

    .poster-thumb.av-poster {
      aspect-ratio: 4 / 3;
    }
  }
</style>
