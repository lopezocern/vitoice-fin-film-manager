<script lang="ts">
  // 详情页顶部 Hero 区块：沉浸式氛围背景 + 海报 + 大标题 + 关键元数据 + 简介 + 操作
  import { mediaApi, type Media, type ScrapeData, hasNetworkSource } from '$lib/api/media';
  import { formatTime, formatSize, formatResolution, formatDate, formatBitrate } from '$lib/utils/format';
  import RatingStars from '$lib/components/common/RatingStars.svelte';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';

  let {
    media,
    displayTitle,
    subtitle,
    synopsis,
    genreText,
    companyText,
    hasPoster,
    isAv,
    libraryName,
    codec,
    fps,
    bitrate,
    sd,
    tmdbRatingText,
    runtimeText,
    saving = false,
    onplay,
    ontoggleFavorite,
    onsetRating,
    oneditcover,
    showRefreshSource = false,
    onrefreshsource,
    backdropUrl = ''
  }: {
    media: Media;
    displayTitle: string;
    subtitle?: string;
    synopsis?: string;
    genreText?: string;
    companyText?: string;
    hasPoster: boolean;
    isAv: boolean;
    libraryName: string;
    codec: string;
    fps: number;
    bitrate: number;
    sd: ScrapeData | undefined;
    tmdbRatingText: string | null;
    runtimeText: string | null;
    saving?: boolean;
    onplay?: () => void;
    ontoggleFavorite?: () => void;
    onsetRating?: (v: number) => void;
    oneditcover?: () => void;
    showRefreshSource?: boolean;
    onrefreshsource?: () => void;
    backdropUrl?: string;
  } = $props();

  // 海报点击放大（lightbox）
  let posterZoomed = $state(false);

  // ---- 受限内容遮罩（与媒体墙 content-mask 同一套门控语义）----
  // mask_restricted 开启且媒体属于受限库时，海报/背景打码、禁用放大。
  const restrictedLibIds = $derived(
    new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id)))
  );
  const maskActive = $derived(
    settingsStore.maskRestricted && restrictedLibIds.has(String(media.library_id))
  );

  // ---- 海报比例分类（按图片实际宽高比统一展示）----
  // 宽图 → 3/2 横框、竖图 → 2/3 竖框、方图 → 1/1 方框。
  // 加载前用默认比例（AV 横图 3/2、其余 2/3），加载后按自然比例归类。
  let posterRatio = $state<string | null>(null);
  function onPosterLoad(e: Event): void {
    const img = e.currentTarget as HTMLImageElement;
    const r = img.naturalWidth / img.naturalHeight;
    if (!Number.isFinite(r) || r <= 0) return;
    if (r > 1.05) posterRatio = '3 / 2';
    else if (r >= 0.95) posterRatio = '1 / 1';
    else posterRatio = '2 / 3';
  }

  function typeLabel(t: Media['type']): string {
    if (t === 'video') return '视频';
    if (t === 'audio') return '音频';
    if (t === 'image') return '图片';
    return t;
  }
</script>

<div class="hero-block">
  <div class="hero-bg" aria-hidden="true">
    {#if backdropUrl && !maskActive}
      <div class="hero-bg-img" style={`background-image:url('${backdropUrl}')`}></div>
    {/if}
  </div>
  <div class="hero-inner">
    <div class="poster-col">
      <div
        class="poster-wrap"
        class:av-poster={isAv}
        style:aspect-ratio={hasPoster ? (posterRatio ?? undefined) : undefined}
        onclick={() => { if (!maskActive) posterZoomed = true; }}
        role="button"
        tabindex="0"
        title={maskActive ? '限制内容已遮蔽' : '点击放大查看'}
        onkeydown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !maskActive) { e.preventDefault(); posterZoomed = true; } }}
      >
        {#if hasPoster}
          <img src={mediaApi.posterUrl(media.id, media.updated_at)} alt={displayTitle} class="poster" onload={onPosterLoad} />
        {:else if media.thumbnail}
          <img src={mediaApi.thumbnailUrl(media.id, media.updated_at)} alt={media.filename} class="poster" />
        {:else}
          <div class="poster-fallback">
            <span>{media.type === 'video' ? '▶' : media.type === 'audio' ? '♪' : '▣'}</span>
          </div>
        {/if}
        {#if media.duration}
          <span class="duration-badge">{formatTime(media.duration)}</span>
        {/if}
        {#if maskActive}
          <div class="content-mask" title="限制内容 — 已遮蔽">
            <span class="mask-icon">🔞</span>
          </div>
        {/if}
      </div>
    </div>

    <div class="hero-info">
      <div class="hero-title">{displayTitle}</div>
      {#if subtitle}
        <div class="hero-subtitle">{subtitle}</div>
      {/if}

      <div class="hero-meta">
        {#if tmdbRatingText}
          <div class="hm"><b class="rating">★ {tmdbRatingText}</b><span>TMDB 评分</span></div>
        {/if}
        {#if media.year}
          <div class="hm"><b>{media.year}</b><span>年份</span></div>
        {/if}
        {#if runtimeText}
          <div class="hm"><b>{runtimeText}</b><span>片长</span></div>
        {/if}
        {#if genreText}
          <div class="hm"><b>{genreText}</b><span>类型</span></div>
        {/if}
        {#if companyText}
          <div class="hm"><b>{companyText}</b><span>制作</span></div>
        {/if}
      </div>

      {#if synopsis}
        <p class="hero-synopsis">{synopsis}</p>
      {/if}

      <div class="hero-actions">
        <button class="play-btn" class:missing={media.file_missing} onclick={() => onplay?.()}>
          {#if media.file_missing}
            {#if hasNetworkSource(media)}
              <svg viewBox="0 0 24 24" width="16" height="16"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z" fill="currentColor"/></svg>
              网络播放
            {:else}
              <svg viewBox="0 0 24 24" width="16" height="16"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" fill="currentColor"/></svg>
              文件丢失
            {/if}
          {:else}
            <svg viewBox="0 0 24 24" width="16" height="16"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
            立即播放
          {/if}
        </button>

        <button class="fav-btn" class:active={media.favorite} onclick={() => ontoggleFavorite?.()} disabled={saving}>
          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" fill="currentColor"/></svg>
          {media.favorite ? '已收藏' : '收藏'}
        </button>

        <button class="fav-btn" onclick={() => oneditcover?.()} disabled={saving} title="上传/更换自定义封面">
          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z" fill="currentColor"/></svg>
          更换封面
        </button>

        {#if showRefreshSource}
          <button class="fav-btn" onclick={() => onrefreshsource?.()} disabled={saving} title="重新解析聚合站，刷新可能已过期的 36 小时签名直链">
            <svg viewBox="0 0 24 24" width="14" height="14"><path d="M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" fill="currentColor"/></svg>
            刷新源
          </button>
        {/if}
      </div>

      <!-- 技术元数据（次级 chips） -->
      <div class="meta-grid">
        <div class="meta-chip"><span class="meta-label">评分</span><span class="meta-value"><RatingStars value={media.rating} size={14} onrate={(v) => onsetRating?.(v)} /></span></div>
        {#if media.duration}
          <div class="meta-chip"><span class="meta-label">时长</span><span class="meta-value">{formatTime(media.duration)}</span></div>
        {/if}
        <div class="meta-chip"><span class="meta-label">分辨率</span><span class="meta-value">{formatResolution(media.width, media.height)}</span></div>
        <div class="meta-chip"><span class="meta-label">大小</span><span class="meta-value">{formatSize(media.size)}</span></div>
        {#if codec}
          <div class="meta-chip"><span class="meta-label">编码</span><span class="meta-value">{codec}</span></div>
        {/if}
        {#if fps > 0}
          <div class="meta-chip"><span class="meta-label">帧率</span><span class="meta-value">{fps.toFixed(2)} fps</span></div>
        {/if}
        {#if bitrate > 0}
          <div class="meta-chip"><span class="meta-label">码率</span><span class="meta-value">{formatBitrate(bitrate)}</span></div>
        {/if}
        <div class="meta-chip"><span class="meta-label">类型</span><span class="meta-value">{typeLabel(media.type)}</span></div>
        {#if sd?.tmdb_vote_count}
          <div class="meta-chip"><span class="meta-label">投票</span><span class="meta-value">{sd.tmdb_vote_count}</span></div>
        {/if}
        {#if media.season_number != null}
          <div class="meta-chip"><span class="meta-label">季 / 集</span><span class="meta-value">S{media.season_number}{media.episode_number != null ? `E${media.episode_number}` : ''}</span></div>
        {/if}
        {#if media.series_id}
          <div class="meta-chip"><span class="meta-label">所属剧</span><a class="meta-link" href="/series/{media.series_id}" title={media.series_title ?? '查看剧集详情'}>{media.series_title ?? '查看剧集'} →</a></div>
        {/if}
        <div class="meta-chip"><span class="meta-label">库</span><span class="meta-value">{libraryName}</span></div>
        <div class="meta-chip"><span class="meta-label">{media.release_date ? '上映日期' : '添加日期'}</span><span class="meta-value">{media.release_date ? media.release_date : formatDate(media.created_at)}</span></div>
      </div>
    </div>
  </div>
</div>

<!-- 海报放大遮罩 -->
{#if posterZoomed}
  <div
    class="poster-lightbox"
    onclick={() => (posterZoomed = false)}
    role="button"
    tabindex="0"
    onkeydown={(e) => { if (e.key === 'Escape') { e.preventDefault(); posterZoomed = false; } }}
  >
    <img src={hasPoster ? mediaApi.posterUrl(media.id, media.updated_at) : mediaApi.thumbnailUrl(media.id, media.updated_at)} alt={displayTitle} />
    <button class="lightbox-close" onclick={() => (posterZoomed = false)} aria-label="关闭">✕</button>
  </div>
{/if}

<style>
  /* ---- 沉浸式 Hero 区块 ---- */
  .hero-block {
    position: relative;
    overflow: hidden;
    border-bottom: 1px solid var(--rule);
    background: #0e1011;
  }

  /* 氛围背景：树影 + 光斑（无 backdrop 数据时的降级方案，对齐设计稿森林氛围） */
  .hero-bg {
    position: absolute;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    filter: blur(1px);
    background:
      radial-gradient(ellipse at 80% 40%, rgba(83, 110, 101, 0.35) 0 4%, transparent 4.5%),
      radial-gradient(ellipse at 88% 22%, rgba(44, 81, 75, 0.30) 0 9%, transparent 9.5%),
      radial-gradient(ellipse at 71% 30%, rgba(29, 59, 54, 0.26) 0 12%, transparent 12.5%),
      radial-gradient(circle at 82% 26%, rgba(100, 140, 140, 0.20), transparent 30%),
      radial-gradient(circle at 60% 88%, rgba(90, 70, 130, 0.16), transparent 32%),
      linear-gradient(120deg, transparent 25%, rgba(91, 128, 111, 0.22) 50%, transparent 72%);
  }

  /* TMDB backdrop：叠加在渐变氛围上，左侧压暗保证标题/海报可读 */
  .hero-bg-img {
    position: absolute;
    inset: 0;
    background-size: cover;
    background-position: center 20%;
    opacity: 0.52;
  }

  .hero-bg-img::after {
    content: '';
    position: absolute;
    inset: 0;
    background:
      linear-gradient(90deg, rgba(11, 11, 14, 0.88) 0%, rgba(11, 11, 14, 0.42) 48%, rgba(11, 11, 14, 0.8) 100%),
      linear-gradient(0deg, rgba(11, 11, 14, 0.92) 0%, transparent 55%);
  }

  /* 右侧深色渐隐：让文字聚焦、海报突出 */
  .hero-block::after {
    content: '';
    position: absolute;
    inset: 0;
    z-index: 1;
    pointer-events: none;
    background: linear-gradient(90deg, transparent 45%, rgba(11, 11, 14, 0.5) 88%);
  }

  .hero-inner {
    position: relative;
    z-index: 2;
    display: flex;
    gap: 34px;
    padding: 30px 28px 36px;
    max-width: 1280px;
    margin: 0 auto;
  }

  .poster-col {
    width: 260px;
    flex-shrink: 0;
  }

  .hero-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .hero-title {
    font-size: 42px;
    line-height: 1.05;
    font-weight: 800;
    letter-spacing: 0;
    color: #f4f4f7;
  }

  .hero-subtitle {
    font-size: 13.5px;
    color: rgba(244, 244, 247, 0.72);
    margin-top: 6px;
  }

  .hero-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 26px;
    margin: 18px 0 14px;
  }

  .hm {
    display: flex;
    align-items: baseline;
    gap: 6px;
  }

  .hm b {
    font-size: 20px;
    color: #f4f4f7;
    font-weight: 600;
  }

  .hm b.rating {
    color: var(--amber, #ffd45c);
  }

  .hm span {
    font-size: 13px;
    color: rgba(244, 244, 247, 0.72);
  }

  .hero-synopsis {
    margin: 0 0 16px;
    font-size: 13px;
    line-height: 1.7;
    color: rgba(244, 244, 247, 0.82);
    max-width: 860px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .hero-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }

  /* ---- 海报 ---- */
  .poster-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 2 / 3;
    border-radius: var(--radius-card);
    overflow: hidden;
    background: var(--bg-soft);
    margin-bottom: 12px;
    cursor: zoom-in;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.45);
  }

  .poster-wrap.av-poster {
    aspect-ratio: 3 / 2;
  }

  .poster {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .poster-wrap.av-poster .poster {
    object-fit: contain;
  }

  .poster-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 36px;
    background: linear-gradient(135deg, var(--bg-soft), var(--bg2));
  }

  .duration-badge {
    position: absolute;
    bottom: 8px;
    right: 8px;
    background: rgba(0, 0, 0, 0.7);
    color: #fff;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    font-variant-numeric: tabular-nums;
  }

  /* ---- 受限内容遮罩（与媒体墙 content-mask 对齐）---- */
  .poster-wrap:has(.content-mask) {
    cursor: default;
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
    font-size: 40px;
    opacity: 0.85;
  }

  /* ---- 按钮 ---- */
  .play-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    height: 36px;
    padding: 0 18px;
    border: none;
    border-radius: var(--radius);
    background: var(--accent);
    color: #fff;
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .play-btn:hover {
    filter: brightness(1.08);
  }

  .play-btn.missing {
    opacity: 0.85;
  }

  .fav-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    height: 32px;
    padding: 0 14px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--muted);
    font-size: 12.5px;
    transition: all 200ms ease;
  }

  .fav-btn:hover:not(:disabled) {
    border-color: var(--accent2);
    color: var(--accent2);
  }

  .fav-btn.active {
    background: var(--accent2-soft);
    border-color: var(--accent2);
    color: var(--accent2);
  }

  .fav-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* ---- 技术元数据 chips ---- */
  .meta-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 22px;
    align-items: center;
    padding-top: 14px;
    border-top: 1px solid var(--rule-light);
  }

  .meta-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
  }

  .meta-label {
    color: rgba(244, 244, 247, 0.64);
    flex-shrink: 0;
  }

  .meta-value {
    color: rgba(244, 244, 247, 0.88);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .meta-link {
    color: #5de0b4;
    font-size: 12px;
    text-decoration: none;
    transition: opacity 200ms;
  }

  .meta-link:hover { opacity: 0.8; }

  /* ---- 海报放大遮罩 ---- */
  .poster-lightbox {
    position: fixed;
    inset: 0;
    z-index: 3000;
    background: rgba(0, 0, 0, 0.92);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: zoom-out;
    animation: fade-in 200ms ease;
  }

  @keyframes fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .poster-lightbox img {
    max-width: 90vw;
    max-height: 90vh;
    object-fit: contain;
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  }

  .lightbox-close {
    position: absolute;
    top: 20px;
    right: 20px;
    width: 40px;
    height: 40px;
    border: none;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 200ms;
  }

  .lightbox-close:hover {
    background: rgba(255, 255, 255, 0.3);
  }

  @media (max-width: 900px) {
    .hero-inner {
      flex-direction: column;
      padding: 20px 16px;
    }
    .poster-col {
      width: 160px;
    }
    .hero-title {
      font-size: 30px;
    }
  }

  /* 浅色主题下 Hero 仍使用深色氛围背景，因此文字固定为浅色，避免深色文字看不清。 */
  :global([data-theme='light']) .hero-title,
  :global([data-theme='light']) .hm b {
    color: #f4f4f7;
  }
  :global([data-theme='light']) .hero-subtitle,
  :global([data-theme='light']) .hm span,
  :global([data-theme='light']) .meta-label {
    color: rgba(244, 244, 247, 0.72);
  }
  :global([data-theme='light']) .hero-synopsis,
  :global([data-theme='light']) .meta-value {
    color: rgba(244, 244, 247, 0.88);
  }
  :global([data-theme='light']) .meta-link {
    color: #5de0b4;
  }
</style>
