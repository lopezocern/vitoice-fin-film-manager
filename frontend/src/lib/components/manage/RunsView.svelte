<script lang="ts">
  // 运行 — 任务队列 + 操作记录合并为一个页面（PR4：导航 10→5 的一项）。
  // 两个视图数据同源（都是 /tasks 的持久化任务），区别只是时间视角：
  // 任务队列看进行中，操作记录看已结束。
  import { onMount, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { client } from '$lib/api/client';
  import { tasksApi, type Task, type TaskStatus } from '$lib/api/tasks';
  import { formatDate } from '$lib/utils/format';
  import { toasts } from '$lib/stores/toast.svelte';
  import ToastHost from '$lib/components/common/ToastHost.svelte';

  let { tab = 'tasks' }: { tab?: 'tasks' | 'history' } = $props();

  let tasks = $state<Task[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let query = $state('');
  let status = $state<'all' | TaskStatus>('all');
  // 用 $state 而非普通 Set：按钮的 disabled 依赖它，非响应式会导致点了没反应
  let busy = $state<Set<number>>(new Set());

  const isActive = (t: Task): boolean => t.status === 'running' || t.status === 'pending';

  const activeTasks = $derived(tasks.filter(isActive));
  const historyTasks = $derived(
    tasks
      .filter((t) => !isActive(t))
      .sort((a, b) =>
        (b.completed_at ?? b.updated_at).localeCompare(a.completed_at ?? a.updated_at)
      )
  );

  function matches(t: Task): boolean {
    const text = `${t.title} ${t.message ?? ''} ${t.error ?? ''} ${t.type}`.toLowerCase();
    return text.includes(query.trim().toLowerCase());
  }

  const filteredActive = $derived(
    activeTasks.filter((t) => (status === 'all' || t.status === status) && matches(t))
  );
  const filteredHistory = $derived(
    historyTasks.filter((t) => (status === 'all' || t.status === status) && matches(t))
  );

  const STATUS_LABEL: Record<TaskStatus, string> = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  };

  const TYPE_LABEL: Record<string, string> = {
    scan: '扫描',
    metadata: '元数据',
    thumbnail: '缩略图',
    ai_tag: 'AI 打标',
    subtitle: '字幕',
    hash: '哈希',
    scrape: '刮削'
  };

  async function load(): Promise<void> {
    loading = true;
    error = null;
    try {
      tasks = await tasksApi.list();
    } catch (e) {
      error = e instanceof Error ? e.message : '加载任务失败';
    } finally {
      loading = false;
    }
  }

  async function cancel(task: Task): Promise<void> {
    busy = new Set(busy).add(task.id);
    try {
      await client.post(`/tasks/${task.id}/cancel`, {});
      toasts.push('已取消任务');
      await load();
    } catch (e) {
      toasts.push(e instanceof Error ? e.message : '取消失败', 'err');
    } finally {
      const next = new Set(busy);
      next.delete(task.id);
      busy = next;
    }
  }

  async function clearCompleted(): Promise<void> {
    try {
      await client.delete('/tasks/completed');
      toasts.push('已清理已结束任务');
      await load();
    } catch (e) {
      toasts.push(e instanceof Error ? e.message : '清理失败', 'err');
    }
  }

  onMount(() => {
    untrack(() => void load());
    // 运行中任务需要及时反映进度：沿用旧实现的 3s 轮询，卸载时清理。
    const timer = setInterval(() => {
      if (activeTasks.length > 0 || tab === 'tasks') {
        void tasksApi.list().then((list) => (tasks = list)).catch(() => undefined);
      }
    }, 3000);
    return () => clearInterval(timer);
  });
</script>

<div class="runs">
  <header class="head">
    <div>
      <div class="eyebrow">管理 / 运行</div>
      <h1>{tab === 'history' ? '操作记录' : '任务队列'}</h1>
      <p>
        {tab === 'history'
          ? '系统已持久化的任务活动记录（扫描 / 刮削 / 缩略图等后台操作）'
          : '扫描、刮削和缩略图任务的实时状态'}
      </p>
    </div>
    <div class="head-actions">
      {#if tab === 'tasks'}
        <button type="button" class="btn" onclick={() => void clearCompleted()}>清理已结束</button>
      {/if}
      <button type="button" class="btn icon" title="刷新" onclick={() => void load()}>↻</button>
    </div>
  </header>

  <div class="tabs" role="tablist" aria-label="运行视图">
    <button
      type="button"
      role="tab"
      aria-selected={tab === 'tasks'}
      class:active={tab === 'tasks'}
      onclick={() => goto('/manage?section=runs&tab=tasks')}
    >
      任务队列
      {#if activeTasks.length > 0}<b>{activeTasks.length}</b>{/if}
    </button>
    <button
      type="button"
      role="tab"
      aria-selected={tab === 'history'}
      class:active={tab === 'history'}
      onclick={() => goto('/manage?section=runs&tab=history')}
    >
      操作记录
    </button>
  </div>

  <div class="metrics">
    <div><strong>{activeTasks.length}</strong><span>进行中</span></div>
    <div><strong>{tasks.filter((t) => t.status === 'completed').length}</strong><span>已完成</span></div>
    <div><strong>{tasks.filter((t) => t.status === 'failed').length}</strong><span>失败</span></div>
    <div><strong>{tasks.length}</strong><span>保留记录</span></div>
  </div>

  <div class="toolbar">
    <input class="search" type="search" bind:value={query} placeholder="搜索任务名称或类型…" />
    <select bind:value={status} aria-label="任务状态">
      <option value="all">全部状态</option>
      <option value="pending">等待中</option>
      <option value="running">运行中</option>
      <option value="completed">已完成</option>
      <option value="failed">失败</option>
      <option value="cancelled">已取消</option>
    </select>
    <span class="count">{tab === 'history' ? filteredHistory.length : filteredActive.length} 项</span>
  </div>

  {#if error}
    <div class="state error">
      <span>{error}</span>
      <button type="button" class="btn" onclick={() => void load()}>重试</button>
    </div>
  {:else if loading && tasks.length === 0}
    <div class="state">正在读取任务…</div>
  {:else if tab === 'history'}
    <div class="list">
      {#each filteredHistory as task (task.id)}
        <article class="row">
          <div class="rail {task.status}"></div>
          <div class="main">
            <div class="title">
              <b>{task.title || TYPE_LABEL[task.type] || task.type}</b>
              <span class="status {task.status}">{STATUS_LABEL[task.status]}</span>
            </div>
            <p>{task.message || task.error || `${TYPE_LABEL[task.type] ?? task.type}任务`}</p>
          </div>
          <div class="meta">
            <time>{formatDate(task.completed_at ?? task.updated_at)}</time>
            <span>{task.current ?? 0} / {task.total ?? 0}</span>
          </div>
        </article>
      {:else}
        <div class="empty">暂无操作记录</div>
      {/each}
    </div>
  {:else}
    <div class="list">
      {#each filteredActive as task (task.id)}
        <article class="row">
          <div class="rail {task.status}"></div>
          <div class="main">
            <div class="title">
              <b>{task.title || TYPE_LABEL[task.type] || task.type}</b>
              <span class="status {task.status}">{STATUS_LABEL[task.status]}</span>
            </div>
            <p>{task.message || task.error || `${TYPE_LABEL[task.type] ?? task.type}任务`}</p>
            <div class="progress"><i style={`width:${Math.max(0, Math.min(100, task.progress || 0))}%`}></i></div>
          </div>
          <div class="meta">
            <span>{task.current ?? 0} / {task.total ?? 0}</span>
            <time>{formatDate(task.created_at)}</time>
          </div>
          {#if isActive(task)}
            <button type="button" class="btn danger" disabled={busy.has(task.id)} onclick={() => void cancel(task)}>
              取消
            </button>
          {/if}
        </article>
      {:else}
        <div class="empty">没有进行中的任务</div>
      {/each}
    </div>

    {#if historyTasks.length > 0}
      <div class="recent">
        <h2>最近结束</h2>
        <div class="list">
          {#each historyTasks.slice(0, 5) as task (task.id)}
            <article class="row">
              <div class="rail {task.status}"></div>
              <div class="main">
                <div class="title">
                  <b>{task.title || TYPE_LABEL[task.type] || task.type}</b>
                  <span class="status {task.status}">{STATUS_LABEL[task.status]}</span>
                </div>
                <p>{task.message || task.error || '—'}</p>
              </div>
              <div class="meta"><time>{formatDate(task.completed_at ?? task.updated_at)}</time></div>
            </article>
          {/each}
        </div>
      </div>
    {/if}
  {/if}

  <ToastHost />
</div>

<style>
  .runs {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 22px 26px 40px;
    color: var(--ink);
  }
  .head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--rule);
  }
  .eyebrow {
    margin-bottom: 6px;
    color: var(--ink-tertiary);
    font-size: 11px;
    font-weight: 650;
  }
  h1 {
    margin: 0;
    font-size: 23px;
    line-height: 1.2;
  }
  .head p {
    margin: 7px 0 0;
    color: var(--ink-secondary);
    font-size: 13px;
  }
  .head-actions {
    display: flex;
    gap: 7px;
  }
  .btn {
    font: inherit;
    font-size: 12px;
    min-height: 30px;
    padding: 0 11px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    cursor: pointer;
  }
  .btn:hover:not(:disabled) {
    border-color: var(--ink-tertiary);
  }
  .btn.icon {
    min-width: 32px;
  }
  .btn.danger {
    color: var(--danger);
  }
  .btn:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .tabs {
    display: flex;
    gap: 6px;
    margin: 16px 0 0;
  }
  .tabs button {
    font: inherit;
    font-size: 12.5px;
    padding: 6px 13px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    cursor: pointer;
  }
  .tabs button b {
    margin-left: 6px;
    color: var(--accent);
    font-weight: 650;
  }
  .tabs button:hover {
    border-color: var(--ink-tertiary);
    color: var(--ink);
  }
  .tabs button.active {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-soft);
  }
  .metrics {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    margin: 16px 0 14px;
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
  }
  .metrics > div {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 13px 16px;
    border-right: 1px solid var(--rule);
  }
  .metrics > div:last-child {
    border-right: 0;
  }
  .metrics strong {
    font-size: 21px;
    font-variant-numeric: tabular-nums;
  }
  .metrics span {
    color: var(--ink-tertiary);
    font-size: 11.5px;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 9px;
    margin-bottom: 10px;
  }
  .search {
    flex: 1;
    min-width: 160px;
    font: inherit;
    font-size: 13px;
    padding: 7px 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
  }
  .toolbar select {
    font: inherit;
    font-size: 12.5px;
    padding: 7px 9px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
  }
  .count {
    color: var(--ink-tertiary);
    font-size: 12.5px;
    font-variant-numeric: tabular-nums;
  }
  .list {
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
  }
  .row {
    display: grid;
    grid-template-columns: 3px minmax(0, 1fr) 130px auto;
    align-items: center;
    gap: 14px;
    padding: 10px 14px 10px 0;
    border-bottom: 1px solid var(--rule);
  }
  .row:last-child {
    border-bottom: 0;
  }
  .rail {
    align-self: stretch;
    background: var(--ink-tertiary);
  }
  .rail.running {
    background: var(--accent);
  }
  .rail.pending {
    background: var(--warn);
  }
  .rail.failed {
    background: var(--danger);
  }
  .rail.completed {
    background: var(--ok);
  }
  .main {
    min-width: 0;
  }
  .title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13.5px;
  }
  .title b {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status {
    flex: none;
    padding: 1px 6px;
    border-radius: var(--radius-xs);
    background: var(--bg-surface);
    color: var(--ink-tertiary);
    font-size: 11px;
  }
  .status.running {
    color: var(--accent);
  }
  .status.failed {
    color: var(--danger);
  }
  .status.completed {
    color: var(--ok);
  }
  .main p {
    margin: 4px 0 0;
    color: var(--ink-tertiary);
    font-size: 12.5px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .progress {
    height: 3px;
    margin-top: 7px;
    background: var(--bg-surface);
    overflow: hidden;
  }
  .progress i {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width var(--dur) var(--ease-out);
  }
  .meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
    color: var(--ink-tertiary);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
  .state {
    min-height: 200px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--ink-tertiary);
    font-size: 13px;
  }
  .state.error {
    color: var(--danger);
  }
  .empty {
    padding: 60px 20px;
    text-align: center;
    color: var(--ink-tertiary);
    font-size: 13px;
  }
  .recent {
    margin-top: 22px;
  }
  .recent h2 {
    margin: 0 0 8px;
    font-size: 14px;
    color: var(--ink-secondary);
  }
</style>
