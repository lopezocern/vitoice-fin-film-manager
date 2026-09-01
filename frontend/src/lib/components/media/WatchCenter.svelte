<script lang="ts">
  import { mediaApi, type Media, type MediaHomeItem, type MediaHomeResponse } from '$lib/api/media';
  import { seriesApi, type Series } from '$lib/api/series';
  import { formatTime } from '$lib/utils/format';
  import { imageFallback, seriesCoverFallback } from '$lib/utils/image-fallback';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';

  let {
    data,
    loading = false,
    error = null,
    onPlay,
    onOpenMedia,
    onOpenSeries,
    onRefreshRecommendations
  }: {
    data: MediaHomeResponse | null;
    loading?: boolean;
    error?: string | null;
    onPlay: (media: Media) => void;
    onOpenMedia: (media: Media) => void;
    onOpenSeries: (series: Series) => void;
    onRefreshRecommendations: () => void;
  } = $props();

  function openItem(item: MediaHomeItem): void {
    if (item.kind === 'series') onOpenSeries(item.data);
    else onOpenMedia(item.data);
  }

  function imageUrl(item: MediaHomeItem): string | null {
    if (item.kind === 'series') {
      return item.data.poster_path ? seriesApi.posterUrl(item.data.id) : null;
    }
    const media = item.data;
    if (media.series_id != null) return seriesApi.posterUrl(media.series_id);
    if (media.poster) return mediaApi.posterUrl(media.id, media.updated_at);
    if (media.thumbnail) return mediaApi.thumbnailUrl(media.id, media.updated_at);
    return null;
  }

  function handleImageError(event: Event, item: MediaHomeItem): void {
    if (item.kind === 'series') {
      (event.currentTarget as HTMLImageElement).style.display = 'none';
      return;
    }
    if (item.data.series_id != null) seriesCoverFallback(event, item.data);
    else imageFallback(event, item.data);
  }

  // 竖版卡片里的横版海报（宽>高）：cover 居中裁切会把封面主体截掉，
  // AV/横版封面的视觉主体多在右侧——改为显示右半部分。
  function onArtworkLoad(event: Event): void {
    const img = event.currentTarget as HTMLImageElement;
    if (img.naturalWidth > img.naturalHeight) {
      img.style.objectPosition = 'right center';
    }
  }

  // 受限媒体库 ID 集合（与各媒体墙组件保持一致）
  const restrictedLibIds = $derived(
    new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id)))
  );
  function isRestricted(item: MediaHomeItem): boolean {
    return settingsStore.maskRestricted && restrictedLibIds.has(String(item.data.library_id));
  }

  function progress(media: Media): number {
    const position = Number(media.metadata?.playback_position ?? media.metadata?.progress ?? 0);
    return media.duration ? Math.max(0, Math.min(100, (position / media.duration) * 100)) : 0;
  }

  function position(media: Media): number {
    return Number(media.metadata?.playback_position ?? media.metadata?.progress ?? 0);
  }

  function remaining(media: Media): string {
    if (!media.duration) return '';
    const seconds = Math.max(0, media.duration - position(media));
    return seconds >= 3600
      ? `还剩 ${Math.ceil(seconds / 3600)} 小时`
      : `还剩 ${Math.max(1, Math.ceil(seconds / 60))} 分钟`;
  }

  function episodeLabel(media: Media): string {
    const parts: string[] = [];
    if (media.season_number) parts.push(`第 ${media.season_number} 季`);
    if (media.episode_number) parts.push(`第 ${media.episode_number} 集`);
    return parts.join(' · ');
  }

  function meta(item: MediaHomeItem): string {
    if (item.kind === 'series') {
      const parts = ['电视剧'];
      if (item.data.year) parts.push(String(item.data.year));
      if (item.data.total_seasons) parts.push(`${item.data.total_seasons} 季`);
      return parts.join(' · ');
    }
    const media = item.data;
    const parts = [media.series_id ? '单集' : media.type === 'video' ? '电影' : media.type === 'audio' ? '音频' : '图片'];
    if (media.year) parts.push(String(media.year));
    if (media.duration) parts.push(formatTime(media.duration));
    return parts.join(' · ');
  }
</script>

{#snippet artwork(item: MediaHomeItem, eager = false)}
  {@const src = imageUrl(item)}
  {#if src}
    <img
      src={src}
      alt={item.data.title}
      loading={eager ? 'eager' : 'lazy'}
      onload={onArtworkLoad}
      onerror={(event) => handleImageError(event, item)}
    />
  {:else}
    <div class="art-fallback" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="3" y="4" width="18" height="16" rx="2"></rect>
        <path d="m10 9 5 3-5 3z"></path>
      </svg>
    </div>
  {/if}
{/snippet}

{#snippet shelf(title: string, items: MediaHomeItem[], refresh = false)}
  {#if items.length > 0}
    <section class="shelf">
      <header class="shelf-head">
        <h2>{title}</h2>
        {#if refresh}
          <button class="icon-button" onclick={onRefreshRecommendations} title="换一批" aria-label="换一批推荐">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 7h-5V2"></path><path d="M20 7a8 8 0 1 0 1 8"></path>
            </svg>
          </button>
        {/if}
      </header>
      <div class="shelf-grid">
        {#each items as item (item.kind + '-' + item.data.id)}
          <button class="media-card" onclick={() => openItem(item)}>
            <div class="poster" class:masked={isRestricted(item)}>
              {@render artwork(item)}
              {#if item.kind === 'media' && !item.data.file_missing && (item.data.source_type === 'network' || item.data.source_type === 'both')}
                <span class="net-badge" title={item.data.source_type === 'both' ? '本地 + 网络源' : '网络媒体'}>
                  {item.data.source_type === 'both' ? '本+网' : '网'}
                </span>
              {/if}
              {#if isRestricted(item)}
                <div class="content-mask" title="限制内容 — 点击查看"><span class="mask-icon">🔞</span></div>
              {/if}
            </div>
            <div class="card-copy">
              <strong title={item.data.title}>{item.data.title}</strong>
              <span>{meta(item)}</span>
            </div>
          </button>
        {/each}
      </div>
    </section>
  {/if}
{/snippet}

<div class="watch-center">
  {#if loading && !data}
    <div class="loading-grid" aria-label="正在加载观看中心">
      {#each Array(6) as _}<div class="loading-card"></div>{/each}
    </div>
  {:else if error && !data}
    <div class="home-state"><strong>观看中心暂时无法加载</strong><span>{error}</span></div>
  {:else if data}
    {#if data.continue_watching.length > 0}
      {@const primary = data.continue_watching[0]}
      <section class="resume-section">
        <header class="shelf-head"><h2>继续观看</h2></header>
        <div class="resume-layout">
          {#if primary.kind === 'media'}
            <button class="resume-feature" onclick={() => onPlay(primary.data)}>
              <div class="resume-feature-art" class:masked-right={isRestricted(primary)}>
                {@render artwork(primary, true)}
                {#if !primary.data.file_missing && (primary.data.source_type === 'network' || primary.data.source_type === 'both')}
                  <span class="net-badge" title={primary.data.source_type === 'both' ? '本地 + 网络源' : '网络媒体'}>
                    {primary.data.source_type === 'both' ? '本+网' : '网'}
                  </span>
                {/if}
                {#if isRestricted(primary)}
                  <div class="content-mask"><span class="mask-icon">🔞</span></div>
                {/if}
              </div>
              <div class="resume-feature-shade"></div>
              <div class="resume-feature-copy">
                <span class="resume-kicker">{primary.data.series_id ? '继续追剧' : '继续观看'}</span>
                <strong>{primary.data.series_title || primary.data.title}</strong>
                {#if episodeLabel(primary.data)}<span class="resume-episode">{episodeLabel(primary.data)}</span>{/if}
                {#if primary.data.series_title}<span class="resume-item-title">{primary.data.title}</span>{/if}
                <span class="resume-meta">上次播放至 {formatTime(position(primary.data))}</span>
                <div class="progress-line"><span style={`width:${progress(primary.data)}%`}></span></div>
                <div class="resume-footer">
                  <b>继续播放</b><span>{remaining(primary.data)}</span>
                  <span class="play-icon" aria-hidden="true"><svg viewBox="0 0 20 20" width="18" height="18" fill="currentColor"><path d="m7 5 8 5-8 5z"></path></svg></span>
                </div>
              </div>
            </button>
          {/if}
          <div class="resume-stack">
            {#each data.continue_watching.slice(1, 3) as item (item.kind + '-' + item.data.id)}
              {#if item.kind === 'media'}
                <button class="resume-row" onclick={() => onPlay(item.data)}>
                  <div class="resume-row-art" class:masked-right={isRestricted(item)}>
                    {@render artwork(item)}
                    {#if !item.data.file_missing && (item.data.source_type === 'network' || item.data.source_type === 'both')}
                      <span class="net-badge" title={item.data.source_type === 'both' ? '本地 + 网络源' : '网络媒体'}>
                        {item.data.source_type === 'both' ? '本+网' : '网'}
                      </span>
                    {/if}
                    {#if isRestricted(item)}
                      <div class="content-mask"><span class="mask-icon">🔞</span></div>
                    {/if}
                  </div>
                  <div class="resume-row-copy">
                    <strong>{item.data.series_title || item.data.title}</strong>
                    <span>{episodeLabel(item.data) || meta(item)}</span>
                    <div class="mini-progress"><i style={`width:${progress(item.data)}%`}></i></div>
                    <div class="row-bottom"><b>继续播放 · {formatTime(position(item.data))}</b><span>{remaining(item.data)}</span></div>
                  </div>
                </button>
              {/if}
            {/each}
          </div>
        </div>
      </section>
    {/if}

    {@render shelf('最近添加', data.recently_added)}
    {@render shelf('猜你喜欢', data.recommendations, true)}
    {@render shelf('最近播放', data.recently_played)}

    {#if data.continue_watching.length === 0 && data.recently_added.length === 0 && data.recommendations.length === 0 && data.recently_played.length === 0}
      <div class="home-state"><strong>媒体库还是空的</strong><span>导入媒体后，这里会自动整理你的观看现场。</span></div>
    {/if}
  {/if}
</div>

<style>
  .watch-center { flex: 1; min-height: 0; overflow-y: auto; padding: 26px 32px 48px; }
  .shelf, .resume-section { margin-bottom: 34px; }
  .shelf-head { display: flex; align-items: center; justify-content: space-between; min-height: 32px; margin-bottom: 13px; }
  .shelf-head h2 { margin: 0; color: var(--ink); font-size: 17px; font-weight: 650; letter-spacing: 0; }
  .icon-button { width: 30px; height: 30px; display: grid; place-items: center; padding: 0; color: var(--muted); background: transparent; border: 1px solid var(--rule); border-radius: 6px; cursor: pointer; }
  .icon-button:hover { color: var(--ink); border-color: var(--accent); background: var(--bg-soft); }

  .resume-layout { height: 268px; display: grid; grid-template-columns: minmax(420px, 1.6fr) minmax(310px, 1fr); gap: 12px; overflow: hidden; }
  .resume-feature { position: relative; min-width: 0; min-height: 0; overflow: hidden; padding: 0; text-align: left; color: var(--ink); background: var(--bg2); border: 1px solid var(--rule); border-radius: 7px; cursor: pointer; }
  .resume-feature-art { position: absolute; inset: 0 0 0 auto; width: 58%; height: 100%; overflow: hidden; background: var(--bg-soft); }
  .resume-feature-art :global(img) { width: 100%; height: 100%; display: block; object-fit: contain; object-position: right center; }
  .resume-feature-shade { position: absolute; inset: 0; background: linear-gradient(90deg, color-mix(in srgb, var(--bg2) 98%, transparent) 0%, color-mix(in srgb, var(--bg2) 92%, transparent) 42%, transparent 76%), linear-gradient(0deg, rgba(0,0,0,.42), transparent 58%); }
  .resume-feature-copy { position: relative; z-index: 1; width: 64%; height: 100%; display: flex; flex-direction: column; align-items: flex-start; padding: 25px 23px; }
  .resume-feature-copy > strong { margin-top: 8px; font-size: 24px; line-height: 1.2; }
  .resume-kicker { color: var(--accent); font-size: 11px; font-weight: 700; }
  .resume-episode { margin-top: 5px; color: var(--muted); font-size: 12px; }
  .resume-item-title { margin-top: 16px; font-size: 13px; font-weight: 600; }
  .resume-meta { margin-top: 3px; color: var(--muted); font-size: 11px; }
  .progress-line, .mini-progress { width: 100%; height: 3px; margin-top: auto; overflow: hidden; background: var(--rule); }
  .progress-line span, .mini-progress i { display: block; height: 100%; background: var(--accent); }
  .resume-footer { width: 100%; display: flex; align-items: center; gap: 10px; margin-top: 9px; color: var(--muted); font-size: 11px; }
  .resume-footer b { color: var(--ink); }
  .play-icon { margin-left: auto; width: 32px; height: 32px; display: grid; place-items: center; flex: 0 0 auto; color: #07110d; background: var(--accent); border-radius: 50%; }
  .resume-stack { min-width: 0; min-height: 0; display: grid; grid-template-rows: minmax(0, 1fr) minmax(0, 1fr); gap: 10px; }
  .resume-row { min-width: 0; min-height: 0; display: grid; grid-template-columns: 136px minmax(0, 1fr); overflow: hidden; padding: 0; text-align: left; color: var(--ink); background: var(--bg2); border: 1px solid var(--rule); border-radius: 7px; cursor: pointer; }
  .resume-row-art { min-width: 0; min-height: 0; overflow: hidden; background: var(--bg-soft); }
  .resume-row-art :global(img), .poster :global(img) { width: 100%; height: 100%; display: block; object-fit: cover; }
  .resume-row-copy { min-width: 0; min-height: 0; display: flex; flex-direction: column; padding: 14px; overflow: hidden; }
  .resume-row-copy strong, .resume-row-copy > span { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .resume-row-copy strong { font-size: 13px; }
  .resume-row-copy > span { margin-top: 3px; color: var(--muted); font-size: 11px; }
  .row-bottom { display: flex; justify-content: space-between; gap: 8px; margin-top: 7px; color: var(--muted); font-size: 10px; white-space: nowrap; }
  .row-bottom b { overflow: hidden; color: var(--ink); text-overflow: ellipsis; }

  .shelf-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; }
  .media-card { min-width: 0; padding: 0; overflow: hidden; text-align: left; color: var(--ink); background: var(--bg2); border: 1px solid var(--rule); border-radius: 7px; cursor: pointer; transition: transform 160ms ease, border-color 160ms ease; }
  .media-card:hover { transform: translateY(-2px); border-color: var(--accent); }
  .poster { position: relative; width: 100%; aspect-ratio: 2 / 3; overflow: hidden; background: var(--bg-soft); }
  .card-copy { min-width: 0; padding: 9px 10px 11px; }
  .card-copy strong { display: block; overflow: hidden; color: var(--ink); font-size: 13px; line-height: 1.35; white-space: nowrap; text-overflow: ellipsis; }
  .card-copy span { display: block; margin-top: 5px; overflow: hidden; color: var(--muted); font-size: 11px; white-space: nowrap; text-overflow: ellipsis; }
  .art-fallback { width: 100%; height: 100%; display: grid; place-items: center; color: var(--muted); background: var(--bg-soft); }
  .content-mask {
    position: absolute; inset: 0;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    display: flex; align-items: center; justify-content: center;
    z-index: 5; border-radius: inherit;
  }
  .mask-icon { font-size: 28px; opacity: 0.8; }
  .media-card:hover .content-mask {
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(3px); -webkit-backdrop-filter: blur(3px);
  }
  .net-badge {
    position: absolute; top: 6px; left: 6px; z-index: 4;
    padding: 1px 8px;
    background: rgba(37, 99, 235, 0.88);
    color: #fff;
    font-size: 10.5px; font-weight: 600;
    border-radius: 999px;
  }
  .resume-row-art { position: relative; }
  /* 受限横图海报：默认只展示海报右边一半作为遮蔽 */
  .resume-feature-art.masked-right :global(img),
  .resume-row-art.masked-right :global(img) {
    object-fit: cover;
    object-position: center;
    transform: translateX(-50%);
  }
  .home-state { min-height: 280px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--muted); }
  .home-state strong { color: var(--ink); font-size: 16px; }
  .loading-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 14px; }
  .loading-card { aspect-ratio: 2 / 3; border-radius: 7px; background: var(--bg-soft); animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .55; } }

  @media (max-width: 1180px) {
    .resume-layout { grid-template-columns: minmax(400px, 1.4fr) minmax(290px, 1fr); }
    .shelf-grid, .loading-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
    .media-card:nth-child(6) { display: none; }
  }
  @media (max-width: 820px) {
    .watch-center { padding: 20px; }
    .resume-layout { height: auto; grid-template-columns: 1fr; overflow: visible; }
    .resume-feature { height: 235px; }
    .resume-stack { grid-template-columns: 1fr 1fr; grid-template-rows: 126px; }
    .shelf-grid, .loading-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .media-card:nth-child(n+4) { display: none; }
  }
  @media (max-width: 520px) {
    .watch-center { padding: 16px; }
    .resume-feature-copy { width: 82%; padding: 20px 17px; }
    .resume-feature-copy > strong { font-size: 20px; }
    .resume-stack { display: none; }
    .shelf-grid, .loading-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .media-card:nth-child(3) { display: none; }
  }
</style>
