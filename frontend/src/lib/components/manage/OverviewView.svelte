<script lang="ts">
  // 资产概览工作台 — 管理页概览 Tab（设计稿：健康条 → 问题卡 → 运行工作 → 库健康 → 媒体资产治理表）
  import { onMount } from 'svelte';
  import { client } from '$lib/api/client';
  import { formatSize, formatDate } from '$lib/utils/format';
  import { goto } from '$app/navigation';
  import { tasksApi, type Task } from '$lib/api/tasks';
  import { mediaApi, type Media } from '$lib/api/media';
  import { imageFallback } from '$lib/utils/image-fallback';

  interface Summary {
    media_count: number;
    library_count: number;
    total_size: number;
    unorganized_count: number;
    running_tasks: number;
    deleted_count: number;
    missing_count: number;
    no_poster_count: number;
    no_metadata_count: number;
  }

  interface LibraryHealth {
    library_id: number;
    name: string;
    media_count: number;
    missing_count: number;
    total_size: number;
  }

  let summary = $state<Summary | null>(null);
  let libraryHealth = $state<LibraryHealth[]>([]);
  let activeTasks = $state<Task[]>([]);
  let recentTasks = $state<Task[]>([]);
  let assets = $state<Media[]>([]);
  let assetTotal = $state(0);
  let assetFilter = $state<'all' | 'problem' | 'missing' | 'unmatched'>('all');
  let loading = $state(true);
  let loadError = $state('');

  const apiBase = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8765';

  // 可播放率 / 元数据完整 / 封面完整（0-1），media_count 为 0 时视为 100%
  const playableRate = $derived(summary && summary.media_count > 0 ? 1 - summary.missing_count / summary.media_count : 1);
  const metadataRate = $derived(summary && summary.media_count > 0 ? 1 - summary.no_metadata_count / summary.media_count : 1);
  const posterRate = $derived(summary && summary.media_count > 0 ? 1 - summary.no_poster_count / summary.media_count : 1);
  const healthScore = $derived(Math.floor(((playableRate + metadataRate + posterRate) / 3) * 100));
  const healthRing = $derived(`${Math.round(healthScore * 3.6)}deg`);
  const healthTone = $derived(healthScore >= 90 ? 'good' : healthScore >= 75 ? 'warn' : 'bad');

  // 资产治理表：chips 过滤（与设计稿 filter-chip 语义一致）
  const isProblem = (m: Media): boolean => m.file_missing || !m.poster || !m.scrape_data;
  const filteredAssets = $derived(assets.filter((m) => {
    if (assetFilter === 'missing') return m.file_missing;
    if (assetFilter === 'unmatched') return !m.poster && !m.scrape_data;
    if (assetFilter === 'problem') return isProblem(m);
    return true;
  }));
  const problemCount = $derived(assets.filter(isProblem).length);
  const missingCount = $derived(assets.filter((m) => m.file_missing).length);
  const unmatchedCount = $derived(assets.filter((m) => !m.poster && !m.scrape_data).length);

  async function load(): Promise<void> {
    loading = true;
    try {
      const [statsResp, tasks, mediaResp] = await Promise.all([
        client.get<{ summary: Summary; recent_media: unknown[]; library_health?: LibraryHealth[] }>('/stats/summary'),
        tasksApi.list(),
        mediaApi.list({ sort: 'updated_at', order: 'desc', page: 1, page_size: 8 }),
      ]);
      summary = statsResp.summary;
      libraryHealth = statsResp.library_health ?? [];
      activeTasks = tasks.filter((t) => t.status === 'pending' || t.status === 'running');
      recentTasks = tasks
        .filter((t) => t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled')
        .slice(0, 4);
      assets = mediaResp.items ?? [];
      assetTotal = mediaResp.total ?? 0;
    } catch (err) {
      loadError = err instanceof Error ? err.message : '加载概览失败，请检查后端服务';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    load();
  });

  function taskLabel(task: Task): string {
    return task.title || task.type || '任务';
  }

  function taskSubtitle(task: Task): string {
    if (task.status === 'running' && task.total > 0) return `${task.current} / ${task.total} 项`;
    if (task.message) return task.message;
    if (task.status === 'pending') return '等待执行';
    if (task.status === 'failed') return task.error || '执行失败';
    return task.status === 'running' ? '执行中' : '已完成';
  }

  function assetPoster(m: Media): string {
    return m.poster
      ? mediaApi.posterUrl(m.id, m.updated_at)
      : mediaApi.thumbnailUrl(m.id, m.updated_at);
  }

  function assetKindLabel(m: Media): string {
    if (m.type === 'video') return '视频';
    if (m.type === 'audio') return '音频';
    return '图片';
  }

  function assetLibraryLabel(m: Media): string {
    return libraryHealth.find((l) => String(l.library_id) === m.library_id)?.name ?? '';
  }

  function assetStatus(m: Media): { local: string; localTone: '' | 'warn' | 'bad'; meta: string; metaTone: '' | 'warn' | 'bad' } {
    const local = m.file_missing ? '本地文件缺失' : '本地文件正常';
    const localTone: '' | 'warn' | 'bad' = m.file_missing ? 'bad' : '';
    const meta = m.scrape_data ? (m.poster ? '已匹配 · 封面完整' : '已匹配 · 缺封面') : '待刮削';
    const metaTone: '' | 'warn' | 'bad' = m.scrape_data ? (m.poster ? '' : 'warn') : 'warn';
    return { local, localTone, meta, metaTone };
  }
</script>

<div class="overview-view">
  {#if loading}
    <div class="loading-state">加载中...</div>
  {:else if loadError}
    <div class="error-state">
      <p>{loadError}</p>
      <button onclick={() => load()}>重试</button>
    </div>
  {:else if summary}
    <!-- ── 1. 健康条（设计稿 health-strip）── -->
    <section class="health-strip">
      <div class="health-main">
        <div class="health-ring" class:warn={healthTone === 'warn'} class:bad={healthTone === 'bad'} style={`--ring:${healthRing}`}>
          <strong>{healthScore}%</strong>
        </div>
        <div class="health-copy">
          <strong>媒体库状态{healthScore >= 90 ? '良好' : healthScore >= 75 ? '一般' : '需要处理'}</strong>
          <p>{summary.media_count} 个媒体 · {summary.library_count} 个资源库 · 共 {formatSize(summary.total_size)}</p>
        </div>
      </div>
      <div class="health-stat" onclick={() => goto('/manage?section=files&asset=1')}>
        <span class="label">媒体资产</span><strong>{summary.media_count}</strong>
        <small>{summary.library_count} 个资源库</small>
      </div>
      <div class="health-stat" onclick={() => goto('/manage?section=files&source=missing')}>
        <span class="label">可播放率</span><strong class:good={playableRate >= 0.98} class:warn={playableRate < 0.98 && playableRate >= 0.9} class:bad={playableRate < 0.9}>{(playableRate * 100).toFixed(1)}%</strong>
        <small>{summary.missing_count} 个本地文件缺失</small>
      </div>
      <div class="health-stat" onclick={() => goto('/manage?section=metadata')}>
        <span class="label">元数据完整</span><strong class:good={metadataRate >= 0.95} class:warn={metadataRate < 0.95 && metadataRate >= 0.85} class:bad={metadataRate < 0.85}>{(metadataRate * 100).toFixed(1)}%</strong>
        <small>{summary.no_metadata_count} 个待刮削</small>
      </div>
      <div class="health-stat" onclick={() => goto('/manage?section=metadata')}>
        <span class="label">封面完整</span><strong class:good={posterRate >= 0.95} class:warn={posterRate < 0.95 && posterRate >= 0.85} class:bad={posterRate < 0.85}>{(posterRate * 100).toFixed(1)}%</strong>
        <small>{summary.no_poster_count} 个待补齐</small>
      </div>
    </section>

    <!-- ── 2. 待处理问题（设计稿 issue-grid）── -->
    <div class="section-head"><h2>待处理问题</h2><span class="muted">按影响观看和管理的优先级排列</span><button class="more" onclick={() => goto('/manage?section=issues')}>查看全部问题 <span>→</span></button></div>
    <section class="issue-grid">
      <button class="issue-card danger" onclick={() => goto('/manage?section=files&source=missing')}>
        <span class="issue-icon">!</span><strong>{summary.missing_count}</strong>
        <span class="issue-name">文件缺失</span><span class="issue-note">影响播放</span>
      </button>
      <button class="issue-card" onclick={() => goto('/manage?section=metadata')}>
        <span class="issue-icon">▢</span><strong>{summary.no_poster_count}</strong>
        <span class="issue-name">缺少海报或缩略图</span><span class="issue-note">影响识别</span>
      </button>
      <button class="issue-card blue" onclick={() => goto('/manage?section=metadata')}>
        <span class="issue-icon">✦</span><strong>{summary.no_metadata_count}</strong>
        <span class="issue-name">元数据待刮削</span><span class="issue-note">可批量处理</span>
      </button>
      <button class="issue-card" onclick={() => goto('/manage?section=files&asset=1')}>
        <span class="issue-icon">◇</span><strong>{summary.unorganized_count}</strong>
        <span class="issue-name">未整理媒体</span><span class="issue-note">未观看 · 无标签</span>
      </button>
    </section>

    <!-- ── 3. 运行中的工作（设计稿 work-grid）── -->
    <div class="section-head"><h2>运行中的工作</h2><span class="muted">长任务可观察、可取消、可追溯</span><button class="more" onclick={() => goto('/manage?section=tasks')}>打开任务队列 <span>→</span></button></div>
    <section class="work-grid">
      <article class="panel">
        <div class="panel-head"><h3>当前任务</h3><span class="panel-meta">{activeTasks.length} 个运行中 · {Math.max(summary.running_tasks - activeTasks.length, 0)} 个等待</span></div>
        <div class="job-list">
          {#if activeTasks.length === 0}
            <div class="job-empty">当前没有运行中的任务</div>
          {:else}
            {#each activeTasks as task (task.id)}
              <div class="job">
                <span class="job-icon">{task.type === 'scan' ? '⌕' : task.type === 'scrape' ? '✦' : '▣'}</span>
                <div class="job-copy"><strong>{taskLabel(task)}</strong><small>{taskSubtitle(task)}</small></div>
                <div class="job-progress">
                  <div class="line"><i style={`width:${task.progress || 0}%`}></i></div>
                  <small><span>{task.progress || 0}%</span><span>—</span></small>
                </div>
              </div>
            {/each}
          {/if}
        </div>
      </article>
      <article class="panel">
        <div class="panel-head"><h3>最近活动</h3><button class="panel-action" onclick={() => goto('/manage?section=tasks')}>查看记录 <span>→</span></button></div>
        <div class="activity-list">
          {#if recentTasks.length === 0}
            <div class="job-empty">暂无操作记录</div>
          {:else}
            {#each recentTasks as task (task.id)}
              <div class="activity">
                <span class="activity-icon">{task.status === 'failed' ? '✕' : '✓'}</span>
                <div class="activity-copy"><strong>{taskLabel(task)}</strong><small>{taskSubtitle(task)}</small></div>
                <time>{task.completed_at ? formatDate(task.completed_at) : ''}</time>
              </div>
            {/each}
          {/if}
        </div>
      </article>
    </section>

    <!-- ── 4. 资源库健康（设计稿 library-health）── -->
    <div class="section-head"><h2>资源库健康</h2><span class="muted">配置仍在设置页，这里只处理运行状态和异常</span><button class="more" onclick={() => goto('/manage?section=libraries')}>前往资源库设置 <span>→</span></button></div>
    <section class="library-health">
      {#if libraryHealth.length === 0}
        <div class="library-card"><div class="library-card-head"><i class="status"></i><h3>暂无资源库</h3></div><p class="library-note">添加资源库后这里会显示每库的媒体、缺失和占用情况</p></div>
      {:else}
        {#each libraryHealth as lib (lib.library_id)}
          <article class="library-card" class:warn={lib.missing_count > 0} onclick={() => goto(`/manage?section=files&lib=${lib.library_id}`)}>
            <div class="library-card-head"><i class="status"></i><h3>{lib.name}</h3><span class="library-kind">{lib.media_count} 项</span></div>
            <div class="library-card-stats">
              <div><span>媒体</span><strong>{lib.media_count}</strong></div>
              <div><span>缺失</span><strong style={lib.missing_count > 0 ? 'color:var(--accent2)' : ''}>{lib.missing_count}</strong></div>
              <div><span>占用</span><strong>{formatSize(lib.total_size)}</strong></div>
            </div>
            <div class="library-foot"><span>{lib.missing_count > 0 ? `${lib.missing_count} 个文件缺失` : '状态正常'}</span><span class="foot-link">查看文件 <span>→</span></span></div>
          </article>
        {/each}
      {/if}
    </section>

    <!-- ── 5. 媒体资产治理表（设计稿 assetView）── -->
    <div class="section-head"><h2>媒体资产治理</h2><span class="muted">{assetTotal} 项媒体 · 当前显示 {filteredAssets.length} 项</span><button class="more" onclick={() => goto('/manage?section=files&asset=1')}>进入完整资产工作台 <span>→</span></button></div>
    <section class="media-panel">
      <div class="media-toolbar">
        <button class="filter-chip" class:active={assetFilter === 'all'} onclick={() => (assetFilter = 'all')}>全部资产</button>
        <button class="filter-chip" class:active={assetFilter === 'problem'} onclick={() => (assetFilter = 'problem')}>存在问题 <b>{problemCount}</b></button>
        <button class="filter-chip" class:active={assetFilter === 'missing'} onclick={() => (assetFilter = 'missing')}>文件缺失 <b>{missingCount}</b></button>
        <button class="filter-chip" class:active={assetFilter === 'unmatched'} onclick={() => (assetFilter = 'unmatched')}>待处理 <b>{unmatchedCount}</b></button>
        <span class="toolbar-spacer"></span>
        <button class="filter-chip" onclick={() => goto('/manage?section=files&asset=1')}>最近更新 <span>→</span></button>
      </div>
      <div class="media-table-wrap">
        <table class="media-table">
          <thead><tr><th class="asset">资产</th><th class="source">类型 / 资源库</th><th class="metadata">元数据</th><th class="playback">文件与播放</th><th class="actions">操作</th></tr></thead>
          <tbody>
            {#each filteredAssets as m (m.id)}
              {@const st = assetStatus(m)}
              <tr class:problem={isProblem(m)}>
                <td class="asset"><div class="asset-cell">
                  <div class="thumb">{#if m.poster || m.thumbnail}<img src={assetPoster(m)} alt="" loading="lazy" onerror={(e) => imageFallback(e, m)} />{:else}<span>—</span>{/if}</div>
                  <div class="asset-copy"><strong title={m.title ?? m.filename}>{m.title ?? m.filename}</strong><small>{m.filename}</small></div>
                </div></td>
                <td><span class="type-label">{assetKindLabel(m)}</span><small class="lib-name">{assetLibraryLabel(m)}</small></td>
                <td><div class="status-stack"><span class="status-line" class:bad={st.metaTone === 'bad'} class:warn={st.metaTone === 'warn'}>{st.meta}</span></div></td>
                <td><div class="status-stack"><span class="status-line" class:bad={st.localTone === 'bad'} class:warn={st.localTone === 'warn'}>{st.local}</span></div></td>
                <td><div class="action-row">
                  <button title="查看详情" onclick={() => goto(`/detail/${m.id}`)}>详情</button>
                  <button title="编辑元数据" onclick={() => goto(`/manage?section=metadata`)}>编辑</button>
                </div></td>
              </tr>
            {/each}
            {#if filteredAssets.length === 0}
              <tr><td colspan="5" class="empty-cell">没有符合条件的资产</td></tr>
            {/if}
          </tbody>
        </table>
      </div>
    </section>
  {/if}
</div>

<style>
  .overview-view {
    padding: 24px;
    height: 100%;
    overflow-y: auto;
  }
  .loading-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 80px 0;
    color: var(--ink-faint, #888);
  }
  .error-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 80px 0;
    color: var(--ink-faint, #888);
  }
  .error-state button {
    padding: 6px 18px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--bg-elevated);
    color: var(--accent);
    font-family: inherit;
    font-size: 13px;
    cursor: pointer;
  }
  .error-state button:hover { border-color: var(--accent); }

  /* ---- 1. 健康条 ---- */
  .health-strip {
    display: grid;
    grid-template-columns: 1.6fr repeat(4, 1fr);
    gap: 1px;
    min-height: 104px;
    margin-bottom: 10px;
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: var(--rule);
    overflow: hidden;
  }
  .health-main, .health-stat {
    padding: 16px 17px;
    background: var(--bg-elevated);
  }
  .health-main { display: flex; align-items: center; gap: 14px; }
  .health-ring {
    position: relative;
    width: 64px;
    height: 64px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: conic-gradient(var(--accent) 0deg var(--ring), var(--rule-light) var(--ring) 360deg);
  }
  .health-ring::after {
    content: "";
    position: absolute;
    inset: 7px;
    border-radius: 50%;
    background: var(--bg-elevated);
  }
  .health-ring strong {
    position: relative;
    z-index: 1;
    font-size: 17px;
    color: var(--ink);
  }
  .health-ring.warn { background: conic-gradient(var(--accent2) 0deg var(--ring), var(--rule-light) var(--ring) 360deg); }
  .health-ring.bad { background: conic-gradient(#e26d78 0deg var(--ring), var(--rule-light) var(--ring) 360deg); }
  .health-copy strong { display: block; font-size: 14px; color: var(--ink); }
  .health-copy p { margin: 4px 0 0; color: var(--ink-faint); font-size: 12px; }
  .health-stat { display: flex; flex-direction: column; justify-content: center; cursor: pointer; }
  .health-stat:hover { background: color-mix(in srgb, var(--bg-elevated) 90%, var(--accent)); }
  .health-stat .label { color: var(--ink-faint); font-size: 12px; }
  .health-stat strong { margin-top: 4px; font-size: 22px; line-height: 1; color: var(--ink); }
  .health-stat strong.good { color: var(--accent); }
  .health-stat strong.warn { color: var(--accent2); }
  .health-stat strong.bad { color: #e26d78; }
  .health-stat small { margin-top: 6px; color: var(--ink-faint); font-size: 11px; }

  /* ---- 2. 问题卡 / 3. 工作区通用头 ---- */
  .section-head {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 22px 0 10px;
  }
  .section-head h2 { margin: 0; font-size: 15px; color: var(--ink); }
  .section-head .muted { color: var(--ink-faint); font-size: 12px; }
  .section-head .more {
    margin-left: auto;
    background: none;
    border: 0;
    color: var(--accent);
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
  }
  .issue-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
  }
  .issue-card {
    position: relative;
    min-height: 118px;
    padding: 14px;
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: var(--bg-elevated);
    text-align: left;
    font-family: inherit;
    color: var(--ink);
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }
  .issue-card:hover { border-color: var(--accent); background: color-mix(in srgb, var(--bg-elevated) 92%, var(--accent)); }
  .issue-card .issue-icon {
    width: 28px;
    height: 28px;
    display: grid;
    place-items: center;
    border-radius: 6px;
    background: var(--accent2-soft);
    color: var(--accent2);
    font-size: 13px;
    font-weight: 800;
  }
  .issue-card.danger .issue-icon { background: rgba(226, 109, 120, 0.13); color: #e26d78; }
  .issue-card.blue .issue-icon { background: rgba(134, 181, 255, 0.13); color: #86b5ff; }
  .issue-card strong { display: block; margin-top: 12px; font-size: 23px; line-height: 1; }
  .issue-card .issue-name { display: block; margin-top: 5px; color: var(--ink-secondary, #aab5b0); font-size: 13px; }
  .issue-card .issue-note { position: absolute; right: 13px; bottom: 14px; color: var(--ink-faint); font-size: 11px; }

  /* ---- 3. 运行工作 ---- */
  .work-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.9fr);
    gap: 12px;
    align-items: start;
  }
  .panel {
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: var(--bg-elevated);
    overflow: hidden;
  }
  .panel-head {
    min-height: 51px;
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 0 14px;
    border-bottom: 1px solid var(--rule);
  }
  .panel-head h3 { margin: 0; font-size: 13px; color: var(--ink); }
  .panel-head .panel-meta { color: var(--ink-faint); font-size: 12px; }
  .panel-head .panel-action { margin-left: auto; background: none; border: 0; color: var(--accent); font-size: 12px; font-family: inherit; cursor: pointer; }
  .job-list { padding: 3px 13px 8px; }
  .job {
    display: grid;
    grid-template-columns: 27px minmax(0, 1fr) 105px;
    gap: 10px;
    align-items: center;
    min-height: 62px;
    border-bottom: 1px solid var(--rule-light);
  }
  .job:last-child { border-bottom: 0; }
  .job-icon {
    width: 27px;
    height: 27px;
    display: grid;
    place-items: center;
    border-radius: 6px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 12px;
  }
  .job-copy { min-width: 0; }
  .job-copy strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; color: var(--ink); }
  .job-copy small { display: block; margin-top: 3px; color: var(--ink-faint); font-size: 11px; }
  .job-progress { justify-self: end; width: 105px; }
  .job-progress .line { height: 4px; overflow: hidden; border-radius: 3px; background: var(--rule); }
  .job-progress .line i { display: block; height: 100%; background: var(--accent); }
  .job-progress small { display: flex; justify-content: space-between; margin-top: 4px; color: var(--ink-faint); font-size: 11px; }
  .job-empty { padding: 26px 4px; color: var(--ink-faint); font-size: 12px; }
  .activity-list { padding: 3px 14px 8px; }
  .activity {
    display: grid;
    grid-template-columns: 24px minmax(0, 1fr) auto;
    gap: 9px;
    align-items: center;
    min-height: 52px;
    border-bottom: 1px solid var(--rule-light);
  }
  .activity:last-child { border-bottom: 0; }
  .activity-icon { color: var(--accent); font-size: 13px; }
  .activity-copy { min-width: 0; }
  .activity-copy strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 600; color: var(--ink); }
  .activity-copy small, .activity time { color: var(--ink-faint); font-size: 11px; }

  /* ---- 4. 库健康 ---- */
  .library-health { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
  .library-card {
    padding: 13px;
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: var(--bg-elevated);
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .library-card:hover { border-color: var(--accent); }
  .library-card-head { display: flex; align-items: center; gap: 8px; }
  .library-card-head .status { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
  .library-card.warn .status { background: var(--accent2); }
  .library-card h3 { margin: 0; font-size: 14px; color: var(--ink); }
  .library-card .library-kind { margin-left: auto; color: var(--ink-faint); font-size: 11px; }
  .library-card-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 5px;
    padding-top: 9px;
    border-top: 1px solid var(--rule-light);
  }
  .library-card-stats span { display: block; color: var(--ink-faint); font-size: 11px; }
  .library-card-stats strong { display: block; margin-top: 2px; font-size: 15px; color: var(--ink); }
  .library-card .library-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 12px;
    color: var(--ink-faint);
    font-size: 9px;
  }
  .library-card .foot-link { color: var(--accent); }
  .library-note { margin: 10px 0 0; color: var(--ink-faint); font-size: 11px; }

  /* ---- 5. 媒体资产治理表 ---- */
  .media-panel {
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: var(--bg-elevated);
    overflow: hidden;
  }
  .media-toolbar {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 9px 12px;
    border-bottom: 1px solid var(--rule);
    background: var(--bg-elevated);
  }
  .filter-chip {
    height: 27px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 0 9px;
    border: 1px solid var(--rule);
    border-radius: 5px;
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
  }
  .filter-chip.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
  .filter-chip b { font-weight: 700; }
  .toolbar-spacer { flex: 1; }
  .media-table-wrap { overflow: auto; }
  .media-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
  .media-table th {
    height: 35px;
    padding: 0 10px;
    border-bottom: 1px solid var(--rule);
    color: var(--ink-faint);
    font-size: 9px;
    font-weight: 600;
    text-align: left;
  }
  .media-table td {
    height: 67px;
    padding: 7px 10px;
    border-bottom: 1px solid var(--rule-light);
    vertical-align: middle;
    color: var(--ink-secondary);
    font-size: 11px;
  }
  .media-table tr:hover td { background: color-mix(in srgb, var(--bg-elevated) 92%, var(--accent)); }
  .media-table tr.problem td { background: rgba(226, 109, 120, 0.05); }
  .media-table .asset { width: 34%; }
  .media-table .source { width: 16%; }
  .media-table .metadata { width: 18%; }
  .media-table .playback { width: 18%; }
  .media-table .actions { width: 100px; }
  .asset-cell { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .thumb {
    width: 34px;
    height: 48px;
    flex: 0 0 auto;
    overflow: hidden;
    border-radius: 4px;
    background: var(--bg-surface, var(--rule-light));
    display: grid;
    place-items: center;
    color: var(--ink-faint);
    font-size: 11px;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; }
  .asset-copy { min-width: 0; }
  .asset-copy strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; color: var(--ink); }
  .asset-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 3px; color: var(--ink-faint); font-size: 11px; }
  .type-label {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 6px;
    border-radius: 4px;
    background: rgba(134, 181, 255, 0.13);
    color: #86b5ff;
    font-size: 9px;
  }
  .lib-name { display: block; margin-top: 4px; color: var(--ink-faint); font-size: 11px; }
  .status-stack { display: grid; gap: 4px; }
  .status-line { display: flex; align-items: center; gap: 5px; color: var(--ink-secondary); font-size: 11px; }
  .status-line::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
  .status-line.warn::before { background: var(--accent2); }
  .status-line.bad::before { background: #e26d78; }
  .action-row { display: flex; justify-content: flex-end; gap: 3px; }
  .action-row button {
    min-height: 26px;
    padding: 0 8px;
    border: 1px solid var(--rule);
    border-radius: 5px;
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
  }
  .action-row button:hover { border-color: var(--accent); color: var(--accent); }
  .empty-cell { text-align: center; color: var(--ink-faint); font-size: 12px; }

  @media (max-width: 1180px) {
    .health-strip { grid-template-columns: 1.5fr repeat(2, 1fr); }
    .health-stat:nth-child(n+5) { display: none; }
    .issue-grid { grid-template-columns: repeat(2, 1fr); }
    .library-health { grid-template-columns: 1fr; }
  }
  @media (max-width: 900px) {
    .media-table .metadata, .media-table .playback { display: none; }
    .media-table .source { width: 22%; }
  }
  @media (max-width: 760px) {
    .work-grid { grid-template-columns: 1fr; }
    .health-strip { grid-template-columns: repeat(2, 1fr); }
    .health-main { grid-column: 1 / -1; }
    .issue-grid { grid-template-columns: repeat(2, 1fr); }
  }
</style>
