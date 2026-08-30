<script lang="ts">
  // 剧详情页 — 展示电视剧聚合信息，季Tab + 集列表
  // 左固定海报 + 右滚动内容

  import { onMount, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { seriesApi, type SeriesDetail, type Episode } from '$lib/api/series';
  import { mediaApi, type Media } from '$lib/api/media';
  import { librariesApi, type Library } from '$lib/api/libraries';
  import { player } from '$lib/stores/player.svelte';
  import { formatTime, formatSize } from '$lib/utils/format';

  let { params } = $props();
  const id = $derived(params.id);

  let series = $state<SeriesDetail | null>(null);
  let library = $state<Library | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);

  // 季选择状态
  let activeSeason = $state<number | 'unseasoned' | null>(null);

  // 海报放大
  let posterZoomed = $state(false);

  // Toast
  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  function showToast(msg: string, type: 'ok' | 'err' = 'ok'): void {
    toast = { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2500);
  }

  // 刮削数据
  const sd = $derived(
    series?.scrape_data as Record<string, unknown> | null
  );
  const hasScrapeData = $derived(!!sd && Object.keys(sd).length > 0);
  const overview = $derived(series?.overview ?? '');
  const hasPoster = $derived(!!series?.poster_path);

  // 季列表（含无季分组）
  const seasonTabs = $derived.by(() => {
    if (!series) return [];
    const tabs: { label: string; value: number | 'unseasoned'; count: number }[] = [];
    for (const s of series.seasons) {
      tabs.push({ label: `第 ${s.season_number} 季`, value: s.season_number, count: s.episode_count });
    }
    if (series.unseasoned_episodes.length > 0) {
      tabs.push({ label: '未分季', value: 'unseasoned', count: series.unseasoned_episodes.length });
    }
    return tabs;
  });

  // 当前展示的集列表
  const currentEpisodes = $derived.by(() => {
    if (!series) return [];
    if (activeSeason === 'unseasoned') return series.unseasoned_episodes;
    if (activeSeason !== null) {
      const s = series.seasons.find((sg) => sg.season_number === activeSeason);
      return s?.episodes ?? [];
    }
    // 默认：第一季或无季
    if (series.seasons.length > 0) return series.seasons[0].episodes;
    return series.unseasoned_episodes;
  });

  // 默认选季
  $effect(() => {
    if (series && activeSeason === null) {
      if (series.seasons.length > 0) {
        activeSeason = series.seasons[0].season_number;
      } else if (series.unseasoned_episodes.length > 0) {
        activeSeason = 'unseasoned';
      }
    }
  });

  // 第一个未观看的集（用于"继续观看"）
  const firstUnwatched = $derived.by(() => {
    const all = [
      ...series?.seasons.flatMap((s) => s.episodes) ?? [],
      ...(series?.unseasoned_episodes ?? []),
    ];
    return all.find((e) => !e.is_watched) ?? all[0] ?? null;
  });

  // ---- 数据加载 ----
  async function loadSeries(): Promise<void> {
    const myId = ++loadReqId;
    loading = true;
    error = null;
    try {
      const result = await seriesApi.get(id);
      if (myId !== loadReqId) return; // stale response — drop it
      series = result;
      // 加载库信息
      if (series) {
        try {
          const lib = await librariesApi.get(String(series.library_id));
          if (myId !== loadReqId) return;
          library = lib;
        } catch {
          if (myId === loadReqId) library = null;
        }
      }
    } catch {
      if (myId !== loadReqId) return;
      error = '加载剧详情失败，请检查后端服务是否运行';
      series = null;
    } finally {
      if (myId === loadReqId) loading = false;
    }
  }

  onMount(() => {
    // loadSeries 由下方 $effect 统一触发（含首帧），避免重复请求
  });

  // id 变化时重新加载（含首次挂载）
  // F3 fix: request-id guard — rapid series switches must not let a stale
  // response overwrite the current series.
  let loadReqId = 0;
  let lastId = '';
  $effect(() => {
    if (id !== lastId) {
      lastId = id;
      activeSeason = null;
      untrack(() => loadSeries());
    }
  });

  // ---- 播放 ----
  function episodeToMedia(ep: Episode): Media {
    return {
      id: String(ep.id),
      library_id: String(series?.library_id ?? ''),
      path: '',
      filename: ep.file_name,
      title: ep.title,
      type: 'video',
      source_type: 'local',
      file_missing: false,
      size: ep.file_size ?? 0,
      duration: ep.duration ?? undefined,
      rating: ep.rating ?? 0,
      favorite: ep.is_favorite,
      tags: [],
      created_at: '',
      updated_at: '',
    };
  }

  function playEpisode(ep: Episode): void {
    const media = episodeToMedia(ep);
    player.load(media);
    if (ep.playback_position > 0) {
      player.seek(ep.playback_position);
    }
    player.play();
    goto(`/player?id=${ep.id}&from=${encodeURIComponent(`/series/${id}`)}`).catch(() => {
      player.toggleFullscreen();
    });
  }

  function playFirstUnwatched(): void {
    if (firstUnwatched) {
      playEpisode(firstUnwatched);
    } else {
      showToast('暂无可播放的集', 'err');
    }
  }

  function goToEpisode(ep: Episode): void {
    goto(`/detail/${ep.id}`);
  }

  // 进度百分比
  function progressPercent(ep: Episode): number {
    if (!ep.duration || ep.duration <= 0) return 0;
    return Math.min(100, (ep.playback_position / ep.duration) * 100);
  }
</script>

<svelte:head><title>{series ? series.title : '加载中'} — vitoice</title></svelte:head>

{#if loading}
  <div class="state">加载中…</div>
{:else if error}
  <div class="state error">{error}</div>
{:else if series}
  <div class="series-page">
    <!-- 顶部栏 -->
    <div class="topbar">
      <button class="icon-btn" onclick={() => history.back()} title="返回">
        <svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" fill="currentColor"/></svg>
      </button>
      <div class="title-area">
        <div class="title">{series.title}</div>
        {#if series.year}
          <span class="year">{series.year}</span>
        {/if}
      </div>
      <div class="actions">
        <button class="action-btn primary" onclick={playFirstUnwatched}>
          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
          {firstUnwatched?.is_watched ? '重新观看' : '继续观看'}
        </button>
      </div>
    </div>

    <!-- 主体 -->
    <div class="series-body">
      <!-- 左栏 -->
      <aside class="left-col">
        <div
          class="poster-wrap"
          onclick={() => (posterZoomed = true)}
          role="button"
          tabindex="0"
          title="点击放大"
          onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); posterZoomed = true; } }}
        >
          {#if hasPoster}
            <img src={seriesApi.posterUrl(series.id)} alt={series.title} class="poster" />
          {:else}
            <div class="poster-fallback">
              <span>▶</span>
            </div>
          {/if}
        </div>

        <button class="play-btn" onclick={playFirstUnwatched}>
          <svg viewBox="0 0 24 24" width="16" height="16"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
          {firstUnwatched?.is_watched ? '重新观看' : '继续观看'}
        </button>

        <!-- 元数据 -->
        <div class="meta-list">
          {#if series.year}
            <div class="meta-row">
              <span class="meta-label">年份</span>
              <span class="meta-value">{series.year}</span>
            </div>
          {/if}
          <div class="meta-row">
            <span class="meta-label">总集数</span>
            <span class="meta-value">{series.episode_count}</span>
          </div>
          {#if series.total_seasons}
            <div class="meta-row">
              <span class="meta-label">总季数</span>
              <span class="meta-value">{series.total_seasons}</span>
            </div>
          {/if}
          {#if series.total_episodes}
            <div class="meta-row">
              <span class="meta-label">TMDB 集数</span>
              <span class="meta-value">{series.total_episodes}</span>
            </div>
          {/if}
          {#if library}
            <div class="meta-row">
              <span class="meta-label">所属库</span>
              <span class="meta-value">{library.name}</span>
            </div>
          {/if}
          {#if sd?.tmdb_rating != null}
            <div class="meta-row">
              <span class="meta-label">TMDB 评分</span>
              <span class="meta-value">★ {(sd.tmdb_rating as number).toFixed(1)}</span>
            </div>
          {/if}
          {#if sd?.number_of_seasons}
            <div class="meta-row">
              <span class="meta-label">TMDB 季数</span>
              <span class="meta-value">{sd.number_of_seasons}</span>
            </div>
          {/if}
          {#if sd?.status}
            <div class="meta-row">
              <span class="meta-label">状态</span>
              <span class="meta-value">{sd.status}</span>
            </div>
          {/if}
        </div>

        <!-- 刮削信息 -->
        {#if hasScrapeData}
          <div class="scrape-info">
            {#if sd?.genres && Array.isArray(sd.genres) && (sd.genres as string[]).length > 0}
              <div class="scrape-genres">
                {#each (sd.genres as string[]) as g}
                  <span class="genre-tag">{g}</span>
                {/each}
              </div>
            {/if}
            {#if sd?.created_by && Array.isArray(sd.created_by) && (sd.created_by as string[]).length > 0}
              <div class="scrape-row">
                <span class="scrape-label">主创</span>
                <span class="scrape-value">{(sd.created_by as string[]).join('、')}</span>
              </div>
            {/if}
            {#if sd?.networks && Array.isArray(sd.networks) && (sd.networks as string[]).length > 0}
              <div class="scrape-row">
                <span class="scrape-label">电视网</span>
                <span class="scrape-value">{(sd.networks as string[]).join('、')}</span>
              </div>
            {/if}
          </div>
        {/if}
      </aside>

      <!-- 右栏 -->
      <div class="right-col">
        <!-- 简介 -->
        {#if overview}
          <section class="section">
            <div class="section-head">
              <h2 class="section-title">简介</h2>
            </div>
            <div class="overview-text">{overview}</div>
          </section>
        {/if}

        <!-- 季 Tab + 集列表 -->
        <section class="section">
          <div class="section-head">
            <h2 class="section-title">剧集</h2>
            <span class="section-count">{series.episode_count} 集</span>
          </div>

          {#if seasonTabs.length > 1}
            <div class="season-tabs">
              {#each seasonTabs as tab (tab.value)}
                <button
                  class="season-tab"
                  class:active={activeSeason === tab.value}
                  onclick={() => (activeSeason = tab.value)}
                >
                  {tab.label}
                  <span class="tab-count">{tab.count}</span>
                </button>
              {/each}
            </div>
          {/if}

          <!-- 集列表 -->
          <div class="episode-list">
            {#each currentEpisodes as ep (ep.id)}
              <div class="episode-card" class:watched={ep.is_watched}>
                <div class="ep-thumb" onclick={() => goToEpisode(ep)} role="button" tabindex="0" onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goToEpisode(ep); } }}>
                  {#if ep.poster_path}
                    <img src={mediaApi.posterUrl(String(ep.id), ep.updated_at)} alt={ep.title} loading="lazy" />
                  {:else if ep.thumbnail_path}
                    <img src={mediaApi.thumbnailUrl(String(ep.id), ep.updated_at)} alt={ep.title} loading="lazy" />
                  {:else}
                    <div class="ep-thumb-fallback">▶</div>
                  {/if}
                  {#if ep.episode_number != null}
                    <span class="ep-num-badge">E{ep.episode_number}</span>
                  {/if}
                  {#if ep.is_watched}
                    <span class="ep-watched-badge">✓</span>
                  {/if}
                  {#if progressPercent(ep) > 0 && !ep.is_watched}
                    <div class="ep-progress"><div class="ep-progress-fill" style="width:{progressPercent(ep)}%"></div></div>
                  {/if}
                </div>
                <div class="ep-info">
                  <div class="ep-title-row">
                    {#if ep.episode_number != null}
                      <span class="ep-number">{ep.episode_number}</span>
                    {/if}
                    <span class="ep-title" onclick={() => goToEpisode(ep)} role="button" tabindex="0" onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); goToEpisode(ep); } }} title={ep.title}>{ep.title}</span>
                  </div>
                  <div class="ep-meta">
                    {#if ep.duration}<span class="muted">{formatTime(ep.duration)}</span>{/if}
                    {#if ep.file_size}<span class="muted">{formatSize(ep.file_size)}</span>{/if}
                    {#if ep.rating && ep.rating > 0}<span class="ep-rating">★ {ep.rating}</span>{/if}
                  </div>
                  <div class="ep-actions">
                    <button class="ep-play-btn" onclick={() => playEpisode(ep)} title="播放此集">
                      <svg viewBox="0 0 24 24" width="12" height="12"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
                      播放
                    </button>
                    <button class="ep-detail-btn" onclick={() => goToEpisode(ep)} title="查看详情">
                      详情
                    </button>
                  </div>
                </div>
              </div>
            {:else}
              <div class="section-empty">暂无剧集</div>
            {/each}
          </div>
        </section>
      </div>
    </div>
  </div>
{/if}

<!-- 海报放大 -->
{#if posterZoomed && series}
  <div
    class="poster-lightbox"
    onclick={() => (posterZoomed = false)}
    role="button"
    tabindex="0"
    onkeydown={(e) => { if (e.key === 'Escape') { e.preventDefault(); posterZoomed = false; } }}
  >
    {#if hasPoster}
      <img src={seriesApi.posterUrl(series.id)} alt={series.title} />
    {:else}
      <div class="lightbox-fallback">▶</div>
    {/if}
    <button class="lightbox-close" onclick={() => (posterZoomed = false)} aria-label="关闭">✕</button>
  </div>
{/if}

<!-- Toast -->
{#if toast}
  <div class="toast" class:ok={toast.type === 'ok'} class:err={toast.type === 'err'}>{toast.msg}</div>
{/if}

<style>
  .state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 14px;
  }

  .state.error { color: #ff3b30; }

  .series-page {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }

  /* ---- 顶部栏 ---- */
  .topbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 24px;
    border-bottom: 1px solid var(--rule);
    background: var(--bg);
    flex-shrink: 0;
  }

  .icon-btn {
    width: 34px;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--muted);
    transition: all 200ms ease;
    flex-shrink: 0;
    cursor: pointer;
  }

  .icon-btn:hover { color: var(--ink); border-color: var(--muted); }

  .title-area {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 10px;
  }

  .title {
    font-size: 18px;
    font-weight: 600;
    color: var(--ink);
    line-height: 1.4;
  }

  .year {
    font-size: 13px;
    color: var(--muted);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .action-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 32px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 12.5px;
    font-weight: 500;
    transition: all 200ms ease;
    cursor: pointer;
  }

  .action-btn:hover { border-color: var(--muted); }

  .action-btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .action-btn.primary:hover { filter: brightness(1.08); }

  /* ---- 主体布局 ---- */
  .series-body {
    flex: 1;
    display: flex;
    min-height: 0;
  }

  /* ---- 左栏 ---- */
  .left-col {
    width: 200px;
    flex-shrink: 0;
    padding: 20px;
    border-right: 1px solid var(--rule);
    background: var(--bg);
    overflow-y: auto;
  }

  .poster-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 2 / 3;
    border-radius: var(--radius-card);
    overflow: hidden;
    background: var(--bg-soft);
    margin-bottom: 12px;
    cursor: zoom-in;
  }

  .poster {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
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

  .play-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: 100%;
    height: 36px;
    border: none;
    border-radius: var(--radius);
    background: var(--accent);
    color: #fff;
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
    margin-bottom: 16px;
    cursor: pointer;
  }

  .play-btn:hover { filter: brightness(1.08); }

  .meta-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .meta-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }

  .meta-label { color: var(--muted); flex-shrink: 0; }
  .meta-value { color: var(--ink); text-align: right; }

  .scrape-info {
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .scrape-genres {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .genre-tag {
    font-size: 11px;
    color: var(--accent);
    background: var(--accent-soft, rgba(99, 102, 241, 0.1));
    padding: 2px 8px;
    border-radius: var(--radius-full, 999px);
  }

  .scrape-row {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 11.5px;
  }

  .scrape-label { color: var(--muted); }
  .scrape-value { color: var(--ink); }

  /* ---- 右栏 ---- */
  .right-col {
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px;
    min-width: 0;
  }

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
    margin-bottom: 14px;
  }

  .section-title {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
  }

  .section-count {
    font-size: 11px;
    color: var(--muted);
    background: var(--bg-soft);
    padding: 1px 8px;
    border-radius: 999px;
  }

  .overview-text {
    font-size: 13.5px;
    line-height: 1.7;
    color: var(--ink);
  }

  /* ---- 季 Tab ---- */
  .season-tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }

  .season-tab {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 14px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--muted);
    font-size: 12.5px;
    font-weight: 500;
    transition: all 200ms ease;
    cursor: pointer;
  }

  .season-tab:hover { border-color: var(--muted); color: var(--ink); }

  .season-tab.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .tab-count {
    font-size: 10.5px;
    opacity: 0.7;
  }

  /* ---- 集列表 ---- */
  .episode-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .episode-card {
    display: flex;
    gap: 12px;
    padding: 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    transition: border-color 200ms ease, box-shadow 200ms ease;
  }

  .episode-card:hover {
    border-color: var(--accent);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .episode-card.watched { opacity: 0.65; }

  .ep-thumb {
    position: relative;
    width: 120px;
    height: 68px;
    flex-shrink: 0;
    border-radius: var(--radius);
    overflow: hidden;
    background: var(--bg-soft);
    cursor: pointer;
  }

  .ep-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .ep-thumb-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 20px;
  }

  .ep-num-badge {
    position: absolute;
    bottom: 4px;
    left: 4px;
    background: rgba(0, 0, 0, 0.75);
    color: #fff;
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 3px;
    font-variant-numeric: tabular-nums;
  }

  .ep-watched-badge {
    position: absolute;
    top: 4px;
    right: 4px;
    background: var(--accent);
    color: #fff;
    font-size: 10px;
    width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
  }

  .ep-progress {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: rgba(255, 255, 255, 0.25);
  }

  .ep-progress-fill {
    height: 100%;
    background: var(--accent);
  }

  .ep-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 4px;
  }

  .ep-title-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }

  .ep-number {
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }

  .ep-title {
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }

  .ep-title:hover { color: var(--accent); }

  .ep-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 11.5px;
  }

  .muted { color: var(--muted); }
  .ep-rating { color: var(--accent2, #f59e0b); }

  .ep-actions {
    display: flex;
    gap: 6px;
  }

  .ep-play-btn,
  .ep-detail-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 26px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg);
    color: var(--ink);
    font-size: 11.5px;
    transition: all 200ms ease;
    cursor: pointer;
  }

  .ep-play-btn:hover,
  .ep-detail-btn:hover { border-color: var(--accent); color: var(--accent); }

  .section-empty {
    color: var(--muted);
    font-size: 13px;
    padding: 16px 0;
  }

  /* ---- 海报放大 ---- */
  .poster-lightbox {
    position: fixed;
    inset: 0;
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.85);
    cursor: zoom-out;
  }

  .poster-lightbox img {
    max-width: 90vw;
    max-height: 90vh;
    border-radius: var(--radius-card);
    object-fit: contain;
  }

  .lightbox-fallback {
    font-size: 64px;
    color: var(--muted);
  }

  .lightbox-close {
    position: absolute;
    top: 20px;
    right: 20px;
    width: 36px;
    height: 36px;
    border: none;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .lightbox-close:hover { background: rgba(255, 255, 255, 0.25); }

  /* ---- Toast ---- */
  .toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 10000;
    padding: 10px 20px;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 500;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  }

  .toast.ok { background: var(--accent); color: #fff; }
  .toast.err { background: #ff3b30; color: #fff; }

  @media (max-width: 768px) {
    .series-body { flex-direction: column; }
    .left-col { width: 100%; border-right: none; border-bottom: 1px solid var(--rule); }
    .ep-thumb { width: 100px; height: 56px; }
  }
</style>
