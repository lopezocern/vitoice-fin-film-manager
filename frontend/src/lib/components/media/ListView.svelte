<script lang="ts">
  import type { Media } from '$lib/api/media';
  import { mediaApi, hasNetworkSource } from '$lib/api/media';
  import { imageFallback, seriesCoverFallback } from '$lib/utils/image-fallback';
  import { seriesApi } from '$lib/api/series';
  import { formatTime, formatSize, formatResolution } from '$lib/utils/format';
  import { getProgress } from './types';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { settingsStore } from '$lib/stores/settings.svelte';

  let {
    items,
    libraryMap = {},
    tagMap = {},
    onSelect,
    onplay
  }: {
    items: Media[];
    libraryMap?: Record<string, string>;
    tagMap?: Record<string, string>;
    onSelect?: (media: Media) => void;
    /** 点击缩略图直接播放（进播放器） */
    onplay?: (media: Media) => void;
  } = $props();

  // 受限媒体库遮罩（与 PosterWall/TimelineView 保持一致）
  const restrictedLibIds = $derived(
    new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id)))
  );

  function shouldMask(media: Media): boolean {
    return settingsStore.maskRestricted && restrictedLibIds.has(String(media.library_id));
  }

  function typeLabel(t: Media['type']): string {
    if (t === 'video') return '视频';
    if (t === 'audio') return '音频';
    if (t === 'image') return '图片';
    return t;
  }

  // 桌面应用（Windows/macOS）：一次性渲染全部 items（见 PosterWall 说明）
</script>

<div class="list-view">
  <div class="list-head">
    <div class="col col-thumb"></div>
    <div class="col col-title">标题</div>
    <div class="col col-lib">库</div>
    <div class="col col-duration">时长</div>
    <div class="col col-res">分辨率</div>
    <div class="col col-size">大小</div>
    <div class="col col-rating">评分</div>
    <div class="col col-tags">标签</div>
  </div>
  <div class="list-body">
    {#each items as media (media.id)}
    {@const p = getProgress(media.metadata)}
      <button class="row" data-id={media.id} onclick={() => onSelect?.(media)}>
        <div class="col col-thumb">
          <div
            class="mini-thumb"
            title={media.type !== 'image' ? '点击封面播放' : '查看详情'}
            onclick={(e) => {
              e.stopPropagation();
              if (media.type !== 'image') onplay?.(media);
            }}
          >
            {#if media.series_id != null}
              <img src={seriesApi.posterUrl(media.series_id)} alt="" loading="lazy" onerror={(e) => seriesCoverFallback(e, media)} />
            {:else if media.poster}
              <img src={mediaApi.posterUrl(media.id, media.updated_at)} alt="" loading="lazy" onerror={(e) => imageFallback(e, media)} />
            {:else if media.thumbnail}
              <img src={mediaApi.thumbnailUrl(media.id, media.updated_at)} alt="" loading="lazy" onerror={(e) => imageFallback(e, media)} />
            {:else}
              <span class="fb">{media.type === 'video' ? '▶' : media.type === 'audio' ? '♪' : '▣'}</span>
            {/if}
            {#if !media.file_missing && (media.source_type === 'network' || media.source_type === 'both')}
              <span class="net-tag">{media.source_type === 'both' ? '本+网' : '网'}</span>
            {/if}
            {#if shouldMask(media)}
              <div class="content-mask" title="限制内容 — 点击查看">
                <span class="mask-icon">🔞</span>
              </div>
            {/if}
          </div>
        </div>
        <div class="col col-title" title={media.filename}>
          <span class="title-text" class:missing={media.file_missing}>{media.filename}</span>
          {#if media.file_missing}<span class="missing-tag" class:has-net={hasNetworkSource(media)}>{hasNetworkSource(media) ? '🔗网络' : '⚠丢失'}</span>{/if}
          {#if media.favorite}<span class="fav">♥</span>{/if}
          {#if p > 0}
            <span class="mini-prog" title="播放进度 {Math.round(p)}%"><span style="width:{p}%"></span></span>
          {/if}
        </div>
        <div class="col col-lib">{libraryMap[media.library_id] ?? '—'}</div>
        <div class="col col-duration">{media.duration ? formatTime(media.duration) : '—'}</div>
        <div class="col col-res">{formatResolution(media.width, media.height)}</div>
        <div class="col col-size">{formatSize(media.size)}</div>
        <div class="col col-rating">
          {#if media.rating > 0}<span class="rating">{'★'.repeat(media.rating)}</span>{:else}—{/if}
        </div>
        <div class="col col-tags">
          {#if media.tags && media.tags.length}
            <div class="tag-list">
              {#each media.tags.slice(0, 3) as tid}
                <span class="tag">{tagMap?.[tid] ?? tid}</span>
              {/each}
              {#if media.tags.length > 3}<span class="tag more">+{media.tags.length - 3}</span>{/if}
            </div>
          {:else}—{/if}
        </div>
      </button>
    {/each}
  </div>
</div>

<style>
  .list-view {
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    overflow: hidden;
    background: var(--bg2);
    width: 100%;
  }

  .list-head,
  .row {
    display: grid;
    /* minmax(0, Xfr) 关键：允许列收缩到 0 而非内容最小宽度，
       防止总宽溢出容器导致右侧内容不可见。
       固定宽度列用合理范围，灵活列用 fr 分配剩余空间。 */
    grid-template-columns: 48px minmax(0, 2fr) minmax(60px, 100px) minmax(50px, 70px) minmax(50px, 80px) minmax(50px, 70px) minmax(40px, 55px) minmax(0, 1.5fr);
    align-items: center;
    gap: 8px;
    padding: 0 12px;
    text-align: left;
    width: 100%;
  }

  .list-head {
    height: 36px;
    background: var(--bg-soft);
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    border-bottom: 1px solid var(--rule);
  }

  .row {
    border: none;
    border-bottom: 1px solid var(--rule);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    padding: 8px 12px;
    transition: background 150ms;
  }

  .row:last-child {
    border-bottom: none;
  }

  .row:hover {
    background: var(--bg-soft);
  }

  .col {
    min-width: 0;
    overflow: hidden;
  }

  .col-title {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .title-text {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--ink);
    font-weight: 500;
  }

  .title-text.missing {
    color: var(--muted);
    text-decoration: line-through;
    text-decoration-color: rgba(239, 68, 68, 0.5);
  }

  .missing-tag {
    font-size: 10px;
    color: #ef4444;
    background: rgba(239, 68, 68, 0.1);
    border-radius: var(--radius-full);
    padding: 0 6px;
    white-space: nowrap;
  }

  .missing-tag.has-net {
    color: var(--accent);
    background: rgba(99, 91, 255, 0.1);
  }

  .col-lib,
  .col-duration,
  .col-res,
  .col-size,
  .col-rating {
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .mini-thumb {
    position: relative;
    width: 40px;
    height: 40px;
    border-radius: 6px;
    overflow: hidden;
    background: var(--bg-soft);
    display: flex;
    align-items: center;
    cursor: pointer;
    justify-content: center;
    color: var(--muted);
    font-size: 16px;
  }

  .net-tag {
    position: absolute;
    bottom: 1px;
    right: 1px;
    background: rgba(37, 99, 235, 0.9);
    color: #fff;
    font-size: 9px;
    font-weight: 600;
    padding: 0 4px;
    border-radius: 3px;
    line-height: 1.5;
  }

  .mini-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
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
    font-size: 16px;
    opacity: 0.8;
  }

  .fav {
    color: var(--accent2);
    font-size: 11px;
  }

  .mini-prog {
    display: block;
    height: 3px;
    background: var(--rule);
    border-radius: var(--radius-full);
    overflow: hidden;
  }

  .mini-prog span {
    display: block;
    height: 100%;
    background: var(--accent);
  }

  .rating {
    color: var(--accent2);
    letter-spacing: 1px;
    font-size: 12px;
  }

  .tag-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .tag {
    font-size: 11px;
    color: var(--muted);
    background: var(--bg-soft);
    border-radius: var(--radius-full);
    padding: 1px 8px;
    white-space: nowrap;
  }

  .tag.more {
    color: var(--accent);
    background: var(--accent-soft);
  }
</style>
