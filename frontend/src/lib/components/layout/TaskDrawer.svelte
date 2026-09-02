<script lang="ts">
  import { untrack } from 'svelte';
  import { tasks } from '$lib/stores/tasks.svelte';
  import { tasksApi, type Task, type TaskType } from '$lib/api/tasks';

  let refreshTimer: ReturnType<typeof setInterval> | null = null;
  let tickTimer: ReturnType<typeof setInterval> | null = null;
  /** Live clock so elapsed/ETA tick every second while a task runs. */
  let now = $state(Date.now());
  /** Which task cards are expanded to show details. */
  let expandedIds = $state<number[]>([]);

  async function refresh(): Promise<void> {
    try {
      const items = await tasksApi.list();
      tasks.setItems(items ?? []);
    } catch {
      /* 静默失败 */
    }
  }

  async function cancelTask(id: number): Promise<void> {
    try {
      await tasksApi.cancel(id);
      tasks.updateProgress(id, { status: 'cancelled' });
    } catch {
      /* 忽略 */
    }
  }

  /** Human-readable label + accent for each task type. */
  const typeMeta: Record<TaskType, { label: string }> = {
    scan: { label: '扫描' },
    thumbnail: { label: '缩略图' },
    metadata: { label: '元数据' },
    ai_tag: { label: 'AI 打标' },
    subtitle: { label: '字幕' },
    hash: { label: '哈希' },
    scrape: { label: '刮削' }
  };

  function typeLabel(type: TaskType): string {
    return typeMeta[type]?.label ?? type;
  }

  function statusLabel(status: Task['status']): string {
    switch (status) {
      case 'pending': return '等待中';
      case 'running': return '进行中';
      case 'completed': return '已完成';
      case 'failed': return '失败';
      case 'cancelled': return '已取消';
      default: return status;
    }
  }

  function pct(task: Task): number {
    if (task.total > 0) return Math.min(100, Math.round((task.current / task.total) * 100));
    if (task.progress) return Math.min(100, Math.round(task.progress));
    return 0;
  }

  /** Type-specific unit label for the progress counter ("个文件", "张缩略图"…). */
  function progressUnit(type: TaskType): string {
    switch (type) {
      case 'scan': return '个文件';
      case 'thumbnail': return '张缩略图';
      case 'metadata': return '个文件';
      case 'ai_tag': return '个媒体';
      case 'scrape': return '个媒体';
      case 'subtitle': return '条字幕';
      case 'hash': return '个媒体';
      default: return '项';
    }
  }

  /** "15/100 个文件" style progress string when counts are known. */
  function progressText(task: Task): string {
    if (task.total > 0) {
      return `${task.current} / ${task.total} ${progressUnit(task.type)}`;
    }
    return '';
  }

  /** Prefix verb for the live "currently working on" line, per task type. */
  function activityPrefix(type: TaskType): string {
    switch (type) {
      case 'scan': return '正在扫描';
      case 'thumbnail': return '正在生成';
      case 'metadata': return '正在提取';
      case 'ai_tag': return '正在分析';
      case 'scrape': return '正在刮削';
      case 'subtitle': return '正在提取';
      case 'hash': return '正在计算';
      default: return '正在处理';
    }
  }

  /** Scrape source badge (TMDB / JavBus) parsed from the live subtitle. */
  function scrapeSource(task: Task): string | null {
    if (task.type !== 'scrape' || !task.message) return null;
    if (task.message.includes('JavBus')) return 'JavBus';
    if (task.message.includes('TMDB')) return 'TMDB';
    return null;
  }

  /** Display text for the activity line (strip the "· source" suffix for scrape). */
  function activityText(task: Task): string {
    if (!task.message) return '';
    if (task.type === 'scrape') {
      const idx = task.message.lastIndexOf(' · ');
      return idx > 0 ? task.message.slice(0, idx) : task.message;
    }
    return task.message;
  }

  function formatDuration(ms: number): string {
    const s = Math.floor(ms / 1000);
    if (s < 1) return '< 1 秒';
    if (s < 60) return `${s} 秒`;
    const m = Math.floor(s / 60);
    const rs = s % 60;
    if (m < 60) return rs > 0 ? `${m} 分 ${rs} 秒` : `${m} 分`;
    const h = Math.floor(m / 60);
    const rm = m % 60;
    return rm > 0 ? `${h} 时 ${rm} 分` : `${h} 时`;
  }

  /** Elapsed time for running tasks (live), or total duration for finished ones. */
  function elapsed(task: Task): string {
    if (!task.started_at) return '';
    const start = new Date(task.started_at).getTime();
    if (Number.isNaN(start)) return '';
    const end = task.completed_at
      ? new Date(task.completed_at).getTime()
      : now;
    if (Number.isNaN(end)) return '';
    return formatDuration(Math.max(0, end - start));
  }

  /** Estimated time remaining based on elapsed vs progress. */
  function eta(task: Task): string {
    if (task.status !== 'running') return '';
    const p = pct(task);
    if (p <= 0 || p >= 100 || !task.started_at) return '';
    const start = new Date(task.started_at).getTime();
    if (Number.isNaN(start)) return '';
    const elapsedMs = Math.max(0, now - start);
    const remainingMs = (elapsedMs / p) * (100 - p);
    return formatDuration(remainingMs);
  }

  function formatTime(iso: string | null | undefined): string {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  /** Pretty key→value rendering for the result payload of completed tasks. */
  function resultEntries(task: Task): { key: string; value: string }[] {
    if (!task.result || typeof task.result !== 'object') return [];
    const labels: Record<string, string> = {
      new_count: '新增',
      processed_count: '已处理',
      generated_count: '已生成',
      tagged_count: '已打标',
      subtitle_count: '字幕',
      duplicate_pairs: '重复对',
      matched_count: '已匹配'
    };
    return Object.entries(task.result)
      .filter(([, v]) => v !== null && v !== undefined)
      .map(([k, v]) => ({
        key: labels[k] ?? k,
        value: typeof v === 'object' ? JSON.stringify(v) : String(v)
      }));
  }

  function toggleExpand(id: number): void {
    expandedIds = expandedIds.includes(id)
      ? expandedIds.filter((x) => x !== id)
      : [...expandedIds, id];
  }

  function isExpanded(id: number): boolean {
    return expandedIds.includes(id);
  }

  // 任务轮询：抽屉打开时高频（3s，进度实时刷新）；
  // 关闭时低频常驻（5s，仅更新顶栏任务徽标）——否则任务发起后
  // 顶栏看不到"有任务运行"的标记，必须点进任务中心才显示。
  let drawerOpen = $derived(tasks.open);
  $effect(() => {
    // untrack：refresh 若同步部分读写 $state 会扩大 effect 依赖面（轮询本体在
    // setInterval 回调里跑，天然不在追踪上下文，无需包裹）
    untrack(() => void refresh());
    const interval = drawerOpen ? 3000 : 5000;
    refreshTimer = setInterval(refresh, interval);
    if (drawerOpen) {
      tickTimer = setInterval(() => { now = Date.now(); }, 1000);
    }
    return () => {
      if (refreshTimer) clearInterval(refreshTimer);
      if (tickTimer) clearInterval(tickTimer);
      refreshTimer = null;
      tickTimer = null;
    };
  });
</script>

{#if tasks.open}
  <div class="drawer">
    <div class="drawer-head">
      <div class="head-title">
        任务中心
        {#if tasks.count > 0}
          <span class="count-pill">{tasks.count}</span>
        {/if}
      </div>
      <div class="head-actions">
        <button class="head-btn" title="刷新" onclick={refresh}>↻</button>
        <button class="head-btn" title="关闭" onclick={() => tasks.closePanel()}>×</button>
      </div>
    </div>

    <div class="drawer-body">
      {#if tasks.items.length === 0}
        <div class="empty">暂无任务</div>
      {:else}
        <ul class="task-list">
          {#each tasks.items as task (task.id)}
            {@const p = pct(task)}
            {@const expanded = isExpanded(task.id)}
            <li class="task" data-status={task.status} data-expanded={expanded}>
              <button
                class="task-head"
                onclick={() => toggleExpand(task.id)}
                aria-expanded={expanded}
              >
                <span class="task-icon" data-type={task.type}>
                  <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
                    {#if task.type === 'scan'}
                      <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
                    {:else if task.type === 'thumbnail'}
                      <rect x="2" y="3" width="12" height="10" rx="1.5"></rect>
                      <circle cx="5.5" cy="6.5" r="1"></circle>
                      <path d="M2 11l3.5-3 3 2.5L10 9l4 3" stroke-opacity="0.5"></path>
                    {:else if task.type === 'metadata'}
                      <circle cx="8" cy="8" r="6"></circle>
                      <path d="M8 4.5V8l2.2 1.4" stroke-linecap="round"></path>
                    {:else if task.type === 'ai_tag'}
                      <path d="M8 1.5l1.8 4.2 4.2.3-3.3 2.8 1.1 4.1L8 11l-3.8 2.3 1.1-4.1L2 6.5l4.2-.3L8 1.5z" stroke-linejoin="round"></path>
                    {:else if task.type === 'subtitle'}
                      <rect x="2" y="3" width="12" height="10" rx="1.5"></rect>
                      <path d="M4.5 11h2M9 11h2.5M4 8.5h3M9.5 8.5h2.5" stroke-linecap="round"></path>
                    {:else if task.type === 'hash'}
                      <path d="M3 4h10M3 8h10M3 12h10" stroke-linecap="round"></path>
                      <circle cx="5.5" cy="4" r="0.9" fill="currentColor" stroke="none"></circle>
                      <circle cx="10" cy="8" r="0.9" fill="currentColor" stroke="none"></circle>
                      <circle cx="6" cy="12" r="0.9" fill="currentColor" stroke="none"></circle>
                    {:else if task.type === 'scrape'}
                      <circle cx="8" cy="8" r="5.5"></circle>
                      <path d="M8 4.5v3.5M8 8l2.2 1.5" stroke-linecap="round"></path>
                      <path d="M2.8 5.5l1.6.9M13.2 5.5l-1.6.9" stroke-opacity="0.6"></path>
                    {:else}
                      <circle cx="8" cy="8" r="6"></circle>
                      <path d="M8 5v3.5M8 11h.01" stroke-linecap="round"></path>
                    {/if}
                  </svg>
                </span>

                <span class="task-type-badge">{typeLabel(task.type)}</span>

                <div class="task-main">
                  <div class="task-title" title={task.title}>{task.title || typeLabel(task.type)}</div>
                  {#if task.message && (task.status === 'running' || task.status === 'pending')}
                    <div class="task-activity" title={task.message}>
                      <span class="activity-prefix">{activityPrefix(task.type)}</span>
                      <span class="activity-text">{activityText(task)}</span>
                      {#if scrapeSource(task)}
                        <span class="source-badge" data-source={scrapeSource(task)}>{scrapeSource(task)}</span>
                      {/if}
                    </div>
                  {/if}
                  <div class="task-sub">
                    <span class="status-dot" data-status={task.status}></span>
                    {statusLabel(task.status)}
                    {#if progressText(task)}· {progressText(task)}{/if}
                    {#if p > 0}· {p}%{/if}
                  </div>
                </div>

                <span class="chevron" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
              </button>

              {#if task.status === 'running' || task.status === 'pending'}
                <div class="bar"><div class="bar-fill" style="width:{p}%"></div></div>
                <div class="task-meta">
                  {#if task.status === 'running'}
                    {#if elapsed(task)}<span>已用 {elapsed(task)}</span>{/if}
                    {#if eta(task)}<span class="meta-sep">·</span><span>预计剩余 {eta(task)}</span>{/if}
                  {:else}
                    <span>创建于 {formatTime(task.created_at)}</span>
                    <span class="meta-sep">·</span><span class="meta-muted">排队等待中</span>
                  {/if}
                </div>
              {:else if task.status === 'completed'}
                <div class="bar"><div class="bar-fill ok" style="width:100%"></div></div>
                <div class="task-meta">
                  {#if elapsed(task)}<span>用时 {elapsed(task)}</span>{/if}
                  {#if resultEntries(task).length > 0}
                    {#each resultEntries(task) as r, i}
                      {#if i > 0 || elapsed(task)}<span class="meta-sep">·</span>{/if}
                      <span class="meta-ok">{r.key} {r.value}</span>
                    {/each}
                  {/if}
                </div>
              {:else if task.status === 'failed'}
                <div class="bar"><div class="bar-fill err" style="width:100%"></div></div>
                <div class="task-meta">
                  {#if elapsed(task)}<span>用时 {elapsed(task)}</span>{/if}
                </div>
                {#if task.error}
                  <div class="task-err" title={task.error}>{task.error}</div>
                {/if}
              {:else if task.status === 'cancelled'}
                <div class="bar"><div class="bar-fill cancelled" style="width:{p}%"></div></div>
                <div class="task-meta">
                  {#if elapsed(task)}<span>用时 {elapsed(task)}</span><span class="meta-sep">·</span>{/if}
                  <span class="meta-muted">已手动取消</span>
                </div>
              {/if}

              {#if task.status === 'pending' || task.status === 'running'}
                <button class="cancel" onclick={(e) => { e.stopPropagation(); cancelTask(task.id); }}>取消</button>
              {/if}

              {#if expanded}
                <div class="task-details">
                  {#if task.message}
                    <div class="detail-row">
                      <span class="detail-label">当前处理</span>
                      <span class="detail-value" title={task.message}>{task.message}</span>
                    </div>
                  {/if}
                  <div class="detail-row">
                    <span class="detail-label">进度</span>
                    <span class="detail-value">
                      {#if task.total > 0}
                        {task.current} / {task.total} {progressUnit(task.type)} ({p}%)
                      {:else if task.progress > 0}
                        {p}%
                      {:else}
                        —
                      {/if}
                    </span>
                  </div>
                  {#if task.library_id}
                    <div class="detail-row">
                      <span class="detail-label">媒体库</span>
                      <span class="detail-value">ID {task.library_id}</span>
                    </div>
                  {/if}
                  {#if task.media_id}
                    <div class="detail-row">
                      <span class="detail-label">媒体</span>
                      <span class="detail-value">ID {task.media_id}</span>
                    </div>
                  {/if}
                  {#if elapsed(task)}
                    <div class="detail-row">
                      <span class="detail-label">已用时</span>
                      <span class="detail-value">{elapsed(task)}{#if task.status === 'running' && eta(task)} · 预计剩余 {eta(task)}{/if}</span>
                    </div>
                  {/if}
                  <div class="detail-row">
                    <span class="detail-label">创建</span>
                    <span class="detail-value">{formatTime(task.created_at)}</span>
                  </div>
                  {#if task.started_at}
                    <div class="detail-row">
                      <span class="detail-label">开始</span>
                      <span class="detail-value">{formatTime(task.started_at)}</span>
                    </div>
                  {/if}
                  {#if task.completed_at}
                    <div class="detail-row">
                      <span class="detail-label">完成</span>
                      <span class="detail-value">{formatTime(task.completed_at)}</span>
                    </div>
                  {/if}
                  {#if task.error}
                    <div class="detail-row detail-err">
                      <span class="detail-label">错误详情</span>
                      <span class="detail-value">{task.error}</span>
                    </div>
                  {/if}
                  {#if resultEntries(task).length > 0}
                    <div class="detail-row">
                      <span class="detail-label">结果</span>
                      <span class="detail-value">
                        {#each resultEntries(task) as r, i}{#if i > 0}，{/if}{r.key} {r.value}{/each}
                      </span>
                    </div>
                  {/if}
                </div>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>
{/if}

<style>
  .drawer {
    position: fixed;
    right: 20px;
    bottom: 20px;
    width: 380px;
    max-width: calc(100vw - 40px);
    max-height: 70vh;
    background: var(--bg2);
    backdrop-filter: blur(12px);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
    display: flex;
    flex-direction: column;
    z-index: 900;
    animation: slideUp 200ms ease;
  }

  @keyframes slideUp {
    from { transform: translateY(12px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  .drawer-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid var(--rule);
  }

  .head-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .count-pill {
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 11px;
    font-weight: 600;
    padding: 1px 7px;
    border-radius: var(--radius-full);
  }

  .head-actions {
    display: flex;
    gap: 4px;
  }

  .head-btn {
    width: 26px;
    height: 26px;
    border: none;
    background: none;
    border-radius: var(--radius);
    color: var(--muted);
    font-size: 15px;
    transition: background 150ms, color 150ms;
  }

  .head-btn:hover {
    background: var(--bg-soft);
    color: var(--ink);
  }

  .drawer-body {
    overflow-y: auto;
    padding: 6px;
  }

  .empty {
    padding: 40px 12px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }

  .task-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .task {
    padding: 10px 10px 8px;
    border-radius: var(--radius);
    background: var(--bg-soft);
    transition: background 150ms;
    position: relative;
  }

  .task:hover {
    background: var(--bg);
  }

  .task-head {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    width: 100%;
    border: none;
    background: none;
    padding: 0;
    text-align: left;
    cursor: pointer;
    color: inherit;
    font: inherit;
  }

  .task:has(.cancel) .task-head {
    box-sizing: border-box;
    padding-right: 48px;
  }

  .task-icon {
    font-size: 16px;
    line-height: 1;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    color: var(--accent);
    margin-top: 1px;
  }

  .task[data-status='failed'] .task-icon { color: #ff3b30; }
  .task[data-status='completed'] .task-icon { color: var(--ok); }
  .task[data-status='cancelled'] .task-icon { color: var(--muted); }

  .task-type-badge {
    font-size: 10.5px;
    font-weight: 600;
    color: var(--accent);
    background: var(--accent-soft);
    padding: 2px 6px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
    margin-top: 1px;
    line-height: 1.3;
  }

  .task[data-status='failed'] .task-type-badge {
    color: #ff3b30;
    background: rgba(255, 59, 48, 0.12);
  }
  .task[data-status='completed'] .task-type-badge {
    color: var(--ok);
    background: rgba(76, 175, 80, 0.12);
  }
  .task[data-status='cancelled'] .task-type-badge {
    color: var(--muted);
    background: var(--rule);
  }

  .task-main {
    flex: 1;
    min-width: 0;
  }

  .task-title {
    font-size: 13px;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.35;
  }

  .task-sub {
    font-size: 11.5px;
    color: var(--muted);
    margin-top: 2px;
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }

  .task-activity {
    font-size: 11.5px;
    margin-top: 3px;
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    line-height: 1.35;
  }

  .activity-prefix {
    color: var(--muted);
    flex-shrink: 0;
  }

  .activity-text {
    color: var(--ink);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
    flex: 1;
  }

  .source-badge {
    font-size: 10px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
    background: var(--accent-soft);
    color: var(--accent);
    line-height: 1.4;
  }

  .source-badge[data-source='JavBus'] {
    background: rgba(175, 82, 222, 0.14);
    color: #af52de;
  }

  .source-badge[data-source='TMDB'] {
    background: rgba(14, 156, 140, 0.14);
    color: #0e9c8c;
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--muted);
  }
  .status-dot[data-status='running'] {
    background: var(--accent);
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
    animation: pulse 1.6s ease-in-out infinite;
  }
  .status-dot[data-status='pending'] { background: var(--muted); }
  .status-dot[data-status='completed'] { background: var(--ok); }
  .status-dot[data-status='failed'] { background: #ff3b30; }
  .status-dot[data-status='cancelled'] { background: var(--muted); }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }

  .chevron {
    flex-shrink: 0;
    color: var(--muted);
    font-size: 11px;
    margin-top: 2px;
    line-height: 1;
  }

  .cancel {
    position: absolute;
    top: 10px;
    right: 10px;
    background: none;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: 3px 8px;
    font-size: 11.5px;
    color: var(--muted);
    transition: all 150ms;
    cursor: pointer;
  }

  .cancel:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  .bar {
    margin-top: 8px;
    height: 5px;
    background: var(--rule);
    border-radius: var(--radius-full);
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    background: var(--accent);
    border-radius: var(--radius-full);
    transition: width 300ms ease;
  }

  .bar-fill.ok { background: var(--ok); }
  .bar-fill.err { background: #ff3b30; }
  .bar-fill.cancelled { background: var(--muted); }

  .task-meta {
    margin-top: 5px;
    font-size: 11px;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }

  .meta-sep {
    opacity: 0.5;
  }

  .meta-ok {
    color: var(--ok);
    font-weight: 500;
  }

  .meta-muted {
    color: var(--muted);
  }

  .task-err {
    margin-top: 6px;
    font-size: 11.5px;
    color: #ff3b30;
    word-break: break-word;
    background: rgba(255, 59, 48, 0.08);
    padding: 4px 8px;
    border-radius: var(--radius);
    line-height: 1.4;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .task-details {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px dashed var(--rule);
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .detail-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 11.5px;
    line-height: 1.4;
  }

  .detail-label {
    color: var(--muted);
    flex-shrink: 0;
    width: 56px;
  }

  .detail-value {
    color: var(--ink);
    word-break: break-word;
    flex: 1;
    min-width: 0;
  }

  .detail-err .detail-value {
    color: #ff3b30;
  }
</style>
