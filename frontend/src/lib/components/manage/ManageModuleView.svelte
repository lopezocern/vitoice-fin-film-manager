<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { client, ApiError } from '$lib/api/client';
  import { mediaApi, type Media } from '$lib/api/media';
  import { librariesApi, type Library } from '$lib/api/libraries';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { tasksApi, type Task, type TaskStatus } from '$lib/api/tasks';
  import { formatDate, formatSize } from '$lib/utils/format';
  import { imageFallback } from '$lib/utils/image-fallback';

  type ModuleKind = 'issues' | 'metadata' | 'tasks' | 'history' | 'libraries';
  let { kind }: { kind: ModuleKind } = $props();

  let loading = $state(false);
  let error = $state('');
  let media = $state<Media[]>([]);
  let mediaTotal = $state(0);
  let tasks = $state<Task[]>([]);
  let libraries = $state<Library[]>([]);
  let query = $state('');
  let status = $state<'all' | TaskStatus>('all');
  let showIgnored = $state(false);
  let busyIds = $state<Set<string>>(new Set());
  let notice = $state('');
  let requestVersion = 0;

  const title = $derived({
    issues: '问题中心',
    metadata: '元数据与刮削',
    tasks: '任务队列',
    history: '操作记录',
    libraries: '资源库状态'
  }[kind]);

  const subtitle = $derived({
    issues: '集中处理文件丢失、标签缺失和元数据不完整的媒体',
    metadata: '检查匹配质量、补齐封面，并跟踪批量刮削任务',
    tasks: '查看扫描、刮削和缩略图任务的实时状态',
    history: '基于系统任务记录回溯已执行的后台操作',
    libraries: '监控资源库容量、刮削模式与扫描状态'
  }[kind]);

  const missingFiles = $derived(media.filter((item) => item.file_missing));
  const untagged = $derived(media.filter((item) => item.tags.length === 0));
  // Episode artwork and metadata are governed by the parent series. Do not
  // report every episode as incomplete just because it has no own poster.
  const incompleteMetadata = $derived(media.filter((item) => !item.series_id && !item.metadata_ignored && (!item.poster || !item.scrape_data)));
  const activeTasks = $derived(tasks.filter((task) => task.status === 'running' || task.status === 'pending'));
  const filteredTasks = $derived(tasks.filter((task) => {
    const matchStatus = status === 'all' || task.status === status;
    const text = `${task.title} ${task.message ?? ''} ${task.type}`.toLowerCase();
    return matchStatus && text.includes(query.trim().toLowerCase());
  }));
  const metadataItems = $derived(incompleteMetadata.filter((item) =>
    `${item.title ?? ''} ${item.filename}`.toLowerCase().includes(query.trim().toLowerCase())
  ));
  // 已忽略项：用户显式放弃刮削的记录（仍元数据不完整，可批量恢复）
  const ignoredItems = $derived(
    media
      .filter((item) => item.metadata_ignored && !item.series_id && (!item.poster || !item.scrape_data))
      .filter((item) =>
        `${item.title ?? ''} ${item.filename}`.toLowerCase().includes(query.trim().toLowerCase())
      )
  );
  // 已忽略总数（不随搜索过滤，用于 tab 徽标）
  const ignoredPending = $derived(
    media.filter((item) => item.metadata_ignored && !item.series_id && (!item.poster || !item.scrape_data)).length
  );
  // 操作记录 = 已结束任务的活动时间线（与任务队列的运行中视角区分）
  const historyTasks = $derived(
    tasks
      .filter((t) => ['completed', 'failed', 'cancelled'].includes(t.status))
      .sort((a, b) => (b.completed_at ?? b.updated_at).localeCompare(a.completed_at ?? a.updated_at))
  );
  const filteredHistory = $derived(historyTasks.filter((task) => {
    const text = `${task.title} ${task.message ?? ''} ${task.type}`.toLowerCase();
    return text.includes(query.trim().toLowerCase());
  }));

  async function load(): Promise<void> {
    const version = ++requestVersion;
    loading = true;
    error = '';
    try {
      if (kind === 'issues' || kind === 'metadata') {
        const collected: Media[] = [];
        let page = 1;
        let total = 0;
        do {
          const response = await mediaApi.list({ page, page_size: 200, sort: 'updated_at', order: 'desc' });
          if (version !== requestVersion) return;
          collected.push(...response.items);
          total = response.total;
          if (response.items.length === 0) break;
          page += 1;
        } while (collected.length < total && page <= 20);
        media = collected;
        mediaTotal = total;
      } else if (kind === 'tasks' || kind === 'history') {
        const result = await tasksApi.list();
        if (version !== requestVersion) return;
        tasks = result;
      } else {
        const [result, taskResult] = await Promise.all([librariesApi.list(true), tasksApi.list()]);
        if (version !== requestVersion) return;
        libraries = result;
        tasks = taskResult;
      }
    } catch (e) {
      if (version === requestVersion) error = e instanceof ApiError ? e.message : '数据加载失败，请检查后端服务';
    } finally {
      if (version === requestVersion) loading = false;
    }
  }

  async function run(id: string, action: () => Promise<unknown>, success: string): Promise<void> {
    busyIds = new Set(busyIds).add(id);
    notice = '';
    try {
      await action();
      notice = success;
      await load();
      // 触发全局数据通知：让侧边栏（/stats/summary 徽标）、媒体页等
      // 监听 librariesStore.revision 的视图同步刷新处理后的计数。
      librariesStore.notifyChanged();
    } catch (e) {
      notice = e instanceof ApiError ? e.message : '操作失败';
    } finally {
      const next = new Set(busyIds);
      next.delete(id);
      busyIds = next;
    }
  }

  async function scrapeOne(item: Media): Promise<void> {
    await run(`media-${item.id}`, () => mediaApi.scrape(item.id), `已完成「${item.title ?? item.filename}」的刮削`);
  }

  async function scrapeAll(): Promise<void> {
    const ids = metadataItems.map((item) => Number(item.id)).filter(Number.isFinite);
    if (!ids.length) return;
    await run('batch-scrape', () => client.post('/media/batch', {
      action: 'scrape', media_ids: ids, params: {}
    }), `已创建 ${ids.length} 项媒体的批量刮削任务`);
  }

  function sendIgnore(items: Media[], ignored: boolean): Promise<unknown> {
    const ids = items.map((item) => Number(item.id)).filter(Number.isFinite);
    if (!ids.length) return Promise.resolve();
    return client.post('/media/batch', {
      action: 'metadata_ignore', media_ids: ids, params: { ignored }
    });
  }

  async function ignoreOne(item: Media): Promise<void> {
    await run(`meta-${item.id}`, () => sendIgnore([item], true), `已忽略「${item.title ?? item.filename}」`);
  }

  async function restoreOne(item: Media): Promise<void> {
    await run(`meta-${item.id}`, () => sendIgnore([item], false), `已恢复「${item.title ?? item.filename}」`);
  }

  async function ignoreAll(): Promise<void> {
    await run('batch-ignore', () => sendIgnore(metadataItems, true), `已忽略 ${metadataItems.length} 项媒体元数据`);
  }

  async function restoreAll(): Promise<void> {
    await run('batch-restore', () => sendIgnore(ignoredItems, false), `已恢复 ${ignoredItems.length} 项媒体元数据`);
  }

  async function cancelTask(task: Task): Promise<void> {
    await run(`task-${task.id}`, () => tasksApi.cancel(task.id), `已取消任务「${task.title}」`);
  }

  async function clearTasks(): Promise<void> {
    await run('clear-tasks', () => tasksApi.clear(), '已清理超过保留期的已结束任务');
  }

  async function scanLibrary(library: Library): Promise<void> {
    await run(`scan-${library.id}`, () => librariesApi.scan(library.id), `已创建「${library.name}」的扫描任务`);
  }

  async function scrapeLibrary(library: Library): Promise<void> {
    await run(`scrape-${library.id}`, () => client.post(`/libraries/${library.id}/scrape`, {}), `已创建「${library.name}」的刮削任务`);
  }

  function taskLabel(task: Task): string {
    return ({ scan: '扫描', scrape: '刮削', thumbnail: '缩略图', metadata: '元数据', ai_tag: 'AI 标签', subtitle: '字幕', hash: '校验' } as Record<string, string>)[task.type] ?? task.type;
  }

  function statusLabel(value: TaskStatus): string {
    return ({ pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' } as Record<TaskStatus, string>)[value];
  }

  $effect(() => {
    kind;
    query = '';
    status = 'all';
    // untrack：load 的同步部分写 loading/error（$state），避免被追踪进 effect 依赖面
    untrack(() => void load());
  });

  onMount(() => {
    const timer = setInterval(() => {
      if (kind === 'tasks' || kind === 'history' || kind === 'libraries') {
        void tasksApi.list().then((result) => (tasks = result)).catch(() => undefined);
      }
    }, 3000);
    return () => clearInterval(timer);
  });
</script>

<div class="module-view">
  <header class="module-head">
    <div>
      <div class="eyebrow">管理 / {title}</div>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
    <div class="head-actions">
      {#if kind === 'metadata' && !showIgnored}
        <button class="btn primary" disabled={busyIds.has('batch-scrape') || metadataItems.length === 0} onclick={scrapeAll}>批量刮削</button>
      {:else if kind === 'tasks'}
        <button class="btn" disabled={busyIds.has('clear-tasks')} onclick={clearTasks}>清理已结束</button>
      {:else if kind === 'libraries'}
        <button class="btn primary" onclick={() => goto('/import')}>新建资源库</button>
      {/if}
      <button class="icon-btn" title="刷新" aria-label="刷新" onclick={load}>↻</button>
    </div>
  </header>

  {#if notice}<div class="notice">{notice}</div>{/if}
  {#if error}
    <div class="state error"><strong>无法加载数据</strong><span>{error}</span><button class="btn" onclick={load}>重试</button></div>
  {:else if loading}
    <div class="state">正在读取管理数据...</div>
  {:else if kind === 'issues'}
    <div class="metric-strip">
      <button onclick={() => goto('/manage?section=files&source=missing')}><strong>{missingFiles.length}</strong><span>文件丢失</span></button>
      <button onclick={() => goto('/manage?section=files&asset=1&status=untagged')}><strong>{untagged.length}</strong><span>缺少标签</span></button>
      <button onclick={() => goto('/manage?section=metadata')}><strong>{incompleteMetadata.length}</strong><span>元数据不完整</span></button>
      <div><strong>{mediaTotal}</strong><span>媒体记录</span></div>
    </div>
    <section class="work-section">
      <div class="section-title"><div><h2>优先处理</h2><p>问题按文件可用性、元数据、标签顺序归并</p></div></div>
      <div class="issue-grid">
        <article class="issue-panel critical">
          <header><span>文件丢失</span><strong>{missingFiles.length}</strong></header>
          {#each missingFiles.slice(0, 6) as item (item.id)}
            <button class="compact-row" onclick={() => goto(`/detail/${item.id}`)}><span><b>{item.title ?? item.filename}</b><small>{item.path || '本地路径不可用'}</small></span><i>检查</i></button>
          {:else}<div class="empty">没有丢失文件</div>{/each}
          <button class="panel-action" onclick={() => goto('/manage?section=files&source=missing')}>进入文件与路径处理</button>
        </article>
        <article class="issue-panel">
          <header><span>缺少封面或匹配</span><strong>{incompleteMetadata.length}</strong></header>
          {#each incompleteMetadata.slice(0, 6) as item (item.id)}
            <div class="compact-row"><span><b>{item.title ?? item.filename}</b><small>{item.poster ? '缺少完整匹配信息' : '缺少封面'}</small></span><button disabled={busyIds.has(`media-${item.id}`)} onclick={() => scrapeOne(item)}>刮削</button></div>
          {:else}<div class="empty">元数据状态正常</div>{/each}
          <button class="panel-action" onclick={() => goto('/manage?section=metadata')}>打开元数据工作台</button>
        </article>
        <article class="issue-panel">
          <header><span>缺少标签</span><strong>{untagged.length}</strong></header>
          {#each untagged.slice(0, 6) as item (item.id)}
            <button class="compact-row" onclick={() => goto(`/detail/${item.id}`)}><span><b>{item.title ?? item.filename}</b><small>{item.filename}</small></span><i>编辑</i></button>
          {:else}<div class="empty">当前媒体均有标签</div>{/each}
          <button class="panel-action" onclick={() => goto('/manage?section=files&asset=1&status=untagged')}>进入媒体资产批量治理</button>
        </article>
      </div>
    </section>
  {:else if kind === 'metadata'}
    <div class="toolbar">
        <div class="search"><span>⌕</span><input bind:value={query} placeholder={showIgnored ? '搜索已忽略媒体' : '搜索待处理媒体'} /></div>
        <div class="seg">
          <button class:active={!showIgnored} onclick={() => (showIgnored = false)}>待处理 <b>{incompleteMetadata.length}</b></button>
          <button class:active={showIgnored} onclick={() => (showIgnored = true)}>已忽略 <b>{ignoredPending}</b></button>
        </div>
        {#if showIgnored}
          <button class="btn" disabled={busyIds.has('batch-restore') || ignoredItems.length === 0} onclick={restoreAll}>批量恢复</button>
        {:else}
          <button class="btn" disabled={busyIds.has('batch-ignore') || metadataItems.length === 0} onclick={ignoreAll}>批量忽略</button>
        {/if}
        <span class="result-count">{showIgnored ? ignoredItems.length : metadataItems.length} 项</span>
      </div>
      <div class="data-table metadata-table">
        <div class="table-head"><span>媒体</span><span>识别状态</span><span>封面</span><span>更新时间</span><span>操作</span></div>
        {#each (showIgnored ? ignoredItems : metadataItems) as item (item.id)}
          <div class="table-row">
            <div class="media-cell"><div class="mini-poster">{#if item.poster || item.thumbnail}<img src={item.poster ? mediaApi.posterUrl(item.id, item.updated_at ?? undefined) : mediaApi.thumbnailUrl(item.id, item.updated_at ?? undefined)} alt={item.title ?? item.filename} onerror={(e) => imageFallback(e, item)} />{:else}<span>—</span>{/if}</div><span><b>{item.title ?? item.filename}</b><small>{item.filename}</small></span></div>
            <span class:warning={!item.scrape_data}>{item.scrape_data ? '已有匹配' : '未匹配'}</span>
            <span class:warning={!item.poster}>{item.poster ? '已就绪' : '缺失'}</span>
            <span>{formatDate(item.updated_at)}</span>
            <div class="row-actions">
              <button onclick={() => goto(`/detail/${item.id}`)}>详情</button>
              {#if showIgnored}
                <button class="accent" disabled={busyIds.has(`meta-${item.id}`)} onclick={() => restoreOne(item)}>恢复</button>
              {:else}
                <button class="minor" disabled={busyIds.has(`meta-${item.id}`)} onclick={() => ignoreOne(item)}>忽略</button>
                <button class="accent" disabled={busyIds.has(`media-${item.id}`)} onclick={() => scrapeOne(item)}>重新刮削</button>
              {/if}
            </div>
          </div>
        {:else}<div class="empty large">{showIgnored ? '暂无可恢复的已忽略媒体' : '没有需要处理的媒体'}</div>{/each}
      </div>
  {:else if kind === 'tasks' || kind === 'history'}
    {#if kind === 'history'}
      <div class="metric-strip task-metrics">
        <div><strong>{historyTasks.length}</strong><span>已结束活动</span></div><div><strong>{tasks.filter((t) => t.status === 'completed').length}</strong><span>完成</span></div><div><strong>{tasks.filter((t) => t.status === 'failed').length}</strong><span>失败</span></div><div><strong>{tasks.filter((t) => t.status === 'cancelled').length}</strong><span>已取消</span></div>
      </div>
      <div class="toolbar">
        <div class="search"><span>⌕</span><input bind:value={query} placeholder="搜索操作记录" /></div>
      </div>
      <div class="scope-note">这里展示系统已持久化的任务活动记录（扫描、刮削、缩略图等后台操作）。文件重命名、标签编辑等细粒度审计尚未由后端记录，因此不会在此伪造。</div>
      <div class="history-list">
        {#each filteredHistory as task (task.id)}
          <article class="history-row">
            <div class="history-rail" class:done={task.status === 'completed'} class:failed={task.status === 'failed'} class:cancelled={task.status === 'cancelled'}></div>
            <div class="history-main">
              <div class="history-title"><b>{task.title || taskLabel(task)}</b><span class={`status ${task.status}`}>{statusLabel(task.status)}</span></div>
              <p>{task.message || task.error || `${taskLabel(task)}任务`}</p>
            </div>
            <div class="history-meta">
              <time>{formatDate(task.completed_at ?? task.updated_at)}</time>
              <span>{task.current ?? 0} / {task.total ?? 0}</span>
            </div>
          </article>
        {:else}<div class="empty large">暂无操作记录</div>{/each}
      </div>
    {:else}
      <div class="metric-strip task-metrics">
        <div><strong>{activeTasks.length}</strong><span>正在执行</span></div><div><strong>{tasks.filter((t) => t.status === 'failed').length}</strong><span>失败</span></div><div><strong>{tasks.filter((t) => t.status === 'completed').length}</strong><span>已完成</span></div><div><strong>{tasks.length}</strong><span>保留记录</span></div>
      </div>
      <div class="toolbar">
        <div class="search"><span>⌕</span><input bind:value={query} placeholder="搜索任务名称或类型" /></div>
        <select bind:value={status} aria-label="任务状态"><option value="all">全部状态</option><option value="pending">等待中</option><option value="running">运行中</option><option value="completed">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option></select>
      </div>
      <div class="task-list">
        {#each filteredTasks as task (task.id)}
          <article class="task-row">
            <div class="status-rail" class:running={task.status === 'running'} class:failed={task.status === 'failed'} class:done={task.status === 'completed'}></div>
            <div class="task-main"><div class="task-title"><b>{task.title || taskLabel(task)}</b><span class={`status ${task.status}`}>{statusLabel(task.status)}</span></div><p>{task.message || task.error || `${taskLabel(task)}任务`}</p><div class="progress"><i style={`width:${Math.max(0, Math.min(100, task.progress || 0))}%`}></i></div></div>
            <div class="task-meta"><span>{task.current ?? 0} / {task.total ?? 0}</span><time>{formatDate(task.created_at)}</time></div>
            {#if task.status === 'running' || task.status === 'pending'}<button class="btn danger" disabled={busyIds.has(`task-${task.id}`)} onclick={() => cancelTask(task)}>取消</button>{/if}
          </article>
        {:else}<div class="empty large">没有符合条件的任务记录</div>{/each}
      </div>
    {/if}
  {:else if kind === 'libraries'}
    <div class="metric-strip"><div><strong>{libraries.length}</strong><span>资源库</span></div><div><strong>{libraries.reduce((sum, item) => sum + (item.media_count ?? 0), 0)}</strong><span>媒体记录</span></div><div><strong>{libraries.filter((item) => item.scrape_mode !== 'none').length}</strong><span>启用刮削</span></div><div><strong>{activeTasks.length}</strong><span>活动任务</span></div></div>
    <div class="library-list">
      {#each libraries as library (library.id)}
        <article class="library-row">
          <div class="library-icon">▰</div>
          <div class="library-main"><div><h2>{library.name}</h2>{#if library.is_restricted}<span class="restricted">限制内容</span>{/if}</div><p title={library.path}>{library.path}</p></div>
          <div class="library-stat"><strong>{library.media_count ?? 0}</strong><span>媒体</span></div>
          <div class="library-stat"><strong>{library.scrape_mode ?? 'none'}</strong><span>刮削模式</span></div>
          <div class="row-actions"><button disabled={busyIds.has(`scan-${library.id}`)} onclick={() => scanLibrary(library)}>扫描</button><button disabled={library.scrape_mode === 'none' || busyIds.has(`scrape-${library.id}`)} onclick={() => scrapeLibrary(library)}>刮削</button><button class="accent" onclick={() => goto('/libraries')}>配置</button></div>
        </article>
      {:else}<div class="empty large">尚未创建资源库</div>{/each}
    </div>
  {/if}
</div>

<style>
  .module-view { flex: 1; min-height: 0; overflow: auto; padding: 22px 26px 40px; color: var(--ink); }
  .module-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; padding-bottom: 18px; border-bottom: 1px solid var(--rule); }
  .eyebrow { margin-bottom: 6px; color: var(--ink-tertiary); font-size: 11px; font-weight: 650; }
  h1 { margin: 0; font-size: 23px; line-height: 1.2; letter-spacing: 0; } .module-head p { margin: 7px 0 0; color: var(--ink-secondary); font-size: 13px; }
  .head-actions,.row-actions { display: flex; align-items: center; gap: 7px; flex-shrink: 0; }
  button, input, select { font: inherit; } button { cursor: pointer; }
  .btn,.row-actions button,.compact-row button { min-height: 30px; padding: 0 11px; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--bg-elevated); color: var(--ink); font-size: 12px; }
  .btn:hover,.row-actions button:hover,.compact-row button:hover { border-color: var(--ink-tertiary); } .btn.primary,.row-actions .accent { border-color: var(--accent); background: var(--accent); color: white; }
  .btn.danger { color: #d84a46; } button:disabled { cursor: default; opacity: .45; }
  .icon-btn { width: 32px; height: 32px; border: 1px solid var(--rule); border-radius: var(--radius); background: var(--bg-elevated); color: var(--ink-secondary); font-size: 18px; }
  .notice,.scope-note { margin-top: 14px; padding: 10px 12px; border: 1px solid var(--rule); border-left: 3px solid var(--accent); background: var(--bg-surface); color: var(--ink-secondary); font-size: 12px; line-height: 1.6; }
  .state { min-height: 240px; display: flex; align-items: center; justify-content: center; gap: 12px; color: var(--ink-tertiary); font-size: 13px; } .state.error { flex-direction: column; } .state.error strong { color: #d84a46; }
  .metric-strip { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); margin: 18px 0 22px; border: 1px solid var(--rule); background: var(--bg-elevated); }
  .metric-strip > * { min-height: 84px; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; padding: 14px 18px; border: 0; border-right: 1px solid var(--rule); background: transparent; color: var(--ink); text-align: left; border-radius: 0; }
  .metric-strip > *:last-child { border-right: 0; } .metric-strip button:hover { background: var(--bg-hover); }
  .metric-strip strong { font-size: 22px; font-variant-numeric: tabular-nums; } .metric-strip span { margin-top: 4px; color: var(--ink-tertiary); font-size: 11.5px; }
  .section-title { display:flex; justify-content:space-between; margin-bottom: 12px; } .section-title h2 { margin:0; font-size:15px; } .section-title p { margin:4px 0 0; color:var(--ink-tertiary); font-size:14.5px; }
  .issue-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
  .issue-panel { min-width:0; border:1px solid var(--rule); background:var(--bg-elevated); } .issue-panel.critical { border-top:2px solid #d84a46; }
  .issue-panel > header { display:flex; justify-content:space-between; align-items:center; padding:12px 14px; border-bottom:1px solid var(--rule); font-size:14px; font-weight:650; } .issue-panel header strong { font-size:16px; }
  .compact-row { width:100%; min-height:52px; display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 12px; border:0; border-bottom:1px solid var(--rule); background:transparent; color:var(--ink); text-align:left; }
  button.compact-row:hover { background:var(--bg-hover); } .compact-row > span { min-width:0; display:flex; flex-direction:column; gap:3px; } .compact-row b { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:14px; } .compact-row small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--ink-tertiary); font-size:13.5px; } .compact-row i { color:var(--accent); font-size:14px; font-style:normal; }
  .panel-action { width:100%; height:36px; border:0; background:var(--bg-surface); color:var(--accent); font-size:14.5px; }
  .toolbar { display:flex; align-items:center; gap:10px; margin:18px 0 10px; } .search { flex:1; height:34px; display:flex; align-items:center; gap:8px; padding:0 10px; border:1px solid var(--rule); background:var(--bg-elevated); } .search input { width:100%; border:0; outline:0; background:transparent; color:var(--ink); font-size:14px; } .toolbar select { height:34px; padding:0 28px 0 10px; border:1px solid var(--rule); border-radius:var(--radius); background:var(--bg-elevated); color:var(--ink); } .result-count { color:var(--ink-tertiary); font-size:13.5px; }
  .seg { display:flex; align-items:center; gap:6px; } .seg button { height:32px; padding:0 11px; border:1px solid var(--rule); border-radius:var(--radius); background:var(--bg-elevated); color:var(--ink-secondary); font-size:12.5px; } .seg button b { margin-left:5px; color:var(--ink); font-weight:650; } .seg button:hover { border-color:var(--ink-tertiary); } .seg button.active { border-color:var(--accent); color:var(--accent); background:var(--bg-hover); } .seg button.active b { color:var(--accent); }
  .row-actions .minor { color:var(--ink-secondary); }
  .data-table { border:1px solid var(--rule); background:var(--bg-elevated); overflow:hidden; } .table-head,.table-row { display:grid; grid-template-columns:minmax(260px,2fr) .75fr .6fr .9fr 1fr; align-items:center; gap:14px; padding:10px 14px; } .table-head { background:var(--bg-surface); color:var(--ink-tertiary); font-size:13.5px; font-weight:650; } .table-row { min-height:58px; border-top:1px solid var(--rule); color:var(--ink-secondary); font-size:14.5px; }
  .media-cell { min-width:0; display:flex; align-items:center; gap:10px; } .mini-poster { width:28px; height:38px; display:flex; align-items:center; justify-content:center; background:var(--bg-surface); color:var(--ink-tertiary); overflow:hidden; border-radius:2px; flex-shrink:0; } .mini-poster img { width:100%; height:100%; object-fit:cover; } .mini-poster span { font-size:12px; } .media-cell > span { min-width:0; display:flex; flex-direction:column; gap:3px; } .media-cell b,.media-cell small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; } .media-cell b { color:var(--ink); font-size:14px; } .warning { color:#d88a24; }
  .task-list,.library-list { margin-top:10px; border:1px solid var(--rule); background:var(--bg-elevated); } .task-row { min-height:76px; display:grid; grid-template-columns:3px minmax(0,1fr) 130px auto; align-items:center; gap:14px; padding:10px 14px 10px 0; border-bottom:1px solid var(--rule); } .task-row:last-child,.library-row:last-child { border-bottom:0; } .status-rail { align-self:stretch; background:var(--ink-tertiary); }.status-rail.running{background:var(--accent)}.status-rail.failed{background:#d84a46}.status-rail.done{background:var(--ok)}
  .task-title { display:flex; align-items:center; gap:8px; font-size:14px; } .task-main p { margin:4px 0 7px; color:var(--ink-tertiary); font-size:14px; } .status { padding:2px 6px; background:var(--bg-surface); color:var(--ink-tertiary); font-size:11px; }.status.running{color:var(--accent)}.status.failed{color:#d84a46}.status.completed{color:var(--ok)}
  .progress { height:3px; background:var(--bg-surface); overflow:hidden; }.progress i{display:block;height:100%;background:var(--accent)} .task-meta { display:flex; flex-direction:column; align-items:flex-end; gap:5px; color:var(--ink-tertiary); font-size:13.5px; }
  /* ---- 操作记录（历史活动时间线） ---- */
  .history-list { margin-top:10px; border:1px solid var(--rule); background:var(--bg-elevated); }
  .history-row { min-height:64px; display:grid; grid-template-columns:3px minmax(0,1fr) auto; align-items:center; gap:14px; padding:10px 14px 10px 0; border-bottom:1px solid var(--rule); }
  .history-row:last-child { border-bottom:0; }
  .history-rail { align-self:stretch; background:var(--ink-tertiary); }
  .history-rail.done { background:var(--ok); }
  .history-rail.failed { background:#d84a46; }
  .history-rail.cancelled { background:var(--ink-tertiary); }
  .history-main { min-width:0; }
  .history-title { display:flex; align-items:center; gap:8px; font-size:13.5px; }
  .history-title b { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--ink); }
  .history-main p { margin:4px 0 0; color:var(--ink-tertiary); font-size:12.5px; }
  .history-meta { display:flex; flex-direction:column; align-items:flex-end; gap:5px; color:var(--ink-tertiary); font-size:12.5px; }
  .library-row { min-height:76px; display:grid; grid-template-columns:36px minmax(260px,1fr) 80px 100px auto; align-items:center; gap:14px; padding:10px 14px; border-bottom:1px solid var(--rule); }.library-icon{width:34px;height:34px;display:flex;align-items:center;justify-content:center;background:var(--bg-surface);color:var(--accent)} .library-main>div{display:flex;align-items:center;gap:8px}.library-main h2{margin:0;font-size:13.5px}.library-main p{margin:5px 0 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink-tertiary);font-size:14px}.restricted{padding:2px 6px;background:rgba(216,74,70,.12);color:#d84a46;font-size:11px}.library-stat{display:flex;flex-direction:column;gap:3px}.library-stat strong{font-size:14px}.library-stat span{color:var(--ink-tertiary);font-size:13.5px}
  .empty { padding:18px 12px; color:var(--ink-tertiary); font-size:14.5px; }.empty.large { padding:70px 20px; text-align:center; }
  @media(max-width:1050px){.issue-grid{grid-template-columns:1fr}.table-head,.table-row{grid-template-columns:minmax(220px,2fr) .7fr .6fr 1fr}.table-head span:nth-child(4),.table-row>span:nth-child(4){display:none}.library-row{grid-template-columns:36px minmax(220px,1fr) 70px auto}.library-row .library-stat:nth-of-type(2){display:none}}
  @media(max-width:760px){.module-view{padding:16px}.module-head{align-items:flex-start;flex-direction:column}.metric-strip{grid-template-columns:repeat(2,1fr)}.metric-strip>*:nth-child(2){border-right:0}.metric-strip>*:nth-child(-n+2){border-bottom:1px solid var(--rule)}.task-row{grid-template-columns:3px minmax(0,1fr) auto}.task-meta{display:none}.library-row{grid-template-columns:32px minmax(0,1fr)}.library-row>.library-stat,.library-row>.row-actions{grid-column:2}.table-head,.table-row{grid-template-columns:minmax(180px,1fr) auto}.table-head span:nth-child(2),.table-head span:nth-child(3),.table-head span:nth-child(4),.table-row>span{display:none}}
</style>
