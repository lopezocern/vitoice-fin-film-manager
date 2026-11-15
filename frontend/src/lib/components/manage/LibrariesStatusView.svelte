<script lang="ts">
  // 资源库状态 — 承接已删除概览页的「库健康」（决策 1）。
  // 数字来自 PR1 给 /libraries 新增的聚合：media_count / missing_count / total_size，
  // 配置本身仍留在设置页（这里只处理运行状态与异常）。
  import { onMount, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { client } from '$lib/api/client';
  import { librariesApi, type Library } from '$lib/api/libraries';
  import { tasksApi, type Task } from '$lib/api/tasks';
  import { formatSize } from '$lib/utils/format';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { toasts } from '$lib/stores/toast.svelte';
  import { mediaApi } from '$lib/api/media';
  import ToastHost from '$lib/components/common/ToastHost.svelte';
  import { sparkPoints, trendDelta } from '$lib/media/sparkline';

  let libraries = $state<Library[]>([]);
  let tasks = $state<Task[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  // 容量趋势：lib_id → 按日期升序的点
  let history = $state<Record<string, { date: string; total_size: number }[]>>({});
  // 用 $state 而非普通 Set：按钮的 disabled 依赖它
  let busy = $state<Set<string>>(new Set());

  const activeTasks = $derived(
    tasks.filter((t) => t.status === 'running' || t.status === 'pending')
  );
  const totalMedia = $derived(libraries.reduce((sum, l) => sum + (l.media_count ?? 0), 0));
  const totalMissing = $derived(libraries.reduce((sum, l) => sum + (l.missing_count ?? 0), 0));
  const totalSize = $derived(libraries.reduce((sum, l) => sum + (l.total_size ?? 0), 0));

  async function load(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [libs, taskList, hist] = await Promise.all([
        librariesApi.list(true),
        tasksApi.list(),
        // 趋势是"锦上添花"：失败不该让整页报错
        client
          .get<{ series: Record<string, { date: string; total_size: number }[]> }>(
            '/libraries/size-history',
            { days: 30 }
          )
          .catch(() => ({ series: {} }))
      ]);
      libraries = libs;
      tasks = taskList;
      history = hist.series ?? {};
    } catch (e) {
      error = e instanceof Error ? e.message : '加载资源库失败';
    } finally {
      loading = false;
    }
  }

  /** 某库的趋势线（纯计算在 sparkline.ts 里单测）。 */
  function spark(libId: string | number) {
    const series = (history[String(libId)] ?? []).map((p) => ({
      date: p.date,
      value: p.total_size
    }));
    return sparkPoints(series, 64, 16);
  }

  function delta(libId: string | number): string {
    const series = (history[String(libId)] ?? []).map((p) => ({
      date: p.date,
      value: p.total_size
    }));
    const d = trendDelta(series);
    if (d === null) return '数据积累中';
    if (d === 0) return '近 30 天持平';
    return `${d > 0 ? '+' : '−'}${formatSize(Math.abs(d))}`;
  }

  async function run(key: string, fn: () => Promise<unknown>, ok: string): Promise<void> {
    busy = new Set(busy).add(key);
    try {
      await fn();
      toasts.push(ok);
      await load();
    } catch (e) {
      toasts.push(e instanceof Error ? e.message : '操作失败', 'err');
    } finally {
      const next = new Set(busy);
      next.delete(key);
      busy = next;
    }
  }

  onMount(() => {
    untrack(() => void load());
  });

  /**
   * 调整库顺序：交换相邻两项后把整张表的 sort_order 归一化成 0..n-1。
   *
   * 为什么不只改这两行：历史库的 sort_order 可能全是 0（按 created_at 兜底排序），
   * 只交换两个 0 等于没动。整表归一化对几十个库来说只是一次性开销，且幂等。
   */
  async function move(index: number, delta: number): Promise<void> {
    const target = index + delta;
    if (target < 0 || target >= libraries.length) return;
    const next = [...libraries];
    [next[index], next[target]] = [next[target], next[index]];
    busy = new Set(busy).add('reorder');
    try {
      const results = await Promise.allSettled(
        next.map((lib, i) => librariesApi.update(String(lib.id), { sort_order: i }))
      );
      const bad = results.filter((r) => r.status === 'rejected').length;
      toasts.push(bad ? `顺序已更新，${bad} 项保存失败` : '顺序已更新', bad ? 'err' : 'ok');
      librariesStore.notifyChanged();
      await load();
    } finally {
      const b = new Set(busy);
      b.delete('reorder');
      busy = b;
    }
  }

  async function toggleFlag(lib: Library, key: 'watch_enabled' | 'is_restricted'): Promise<void> {
    const nextValue = !(lib[key] ?? false);
    await run(
      `${key}-${lib.id}`,
      () => librariesApi.update(String(lib.id), { [key]: nextValue }),
      `${lib.name}：${key === 'watch_enabled' ? '文件监控' : '受限内容'}已${nextValue ? '开启' : '关闭'}`
    );
    librariesStore.notifyChanged();
  }
</script>

<div class="libs">
  <header class="head">
    <div>
      <div class="eyebrow">管理 / 资源库</div>
      <h1>资源库状态</h1>
      <p>监控容量、缺失文件与刮削模式；目录配置仍在设置页</p>
    </div>
    <div class="head-actions">
      <button type="button" class="btn primary" onclick={() => goto('/settings')}>前往设置</button>
      <button type="button" class="btn icon" title="刷新" onclick={() => void load()}>↻</button>
    </div>
  </header>

  <div class="metrics">
    <div><strong>{libraries.length}</strong><span>资源库</span></div>
    <div><strong>{totalMedia}</strong><span>媒体记录</span></div>
    <div class:bad={totalMissing > 0}><strong>{totalMissing}</strong><span>文件缺失</span></div>
    <div><strong>{formatSize(totalSize)}</strong><span>占用空间</span></div>
    <div><strong>{activeTasks.length}</strong><span>活动任务</span></div>
  </div>

  {#if error}
    <div class="state error">
      <span>{error}</span>
      <button type="button" class="btn" onclick={() => void load()}>重试</button>
    </div>
  {:else if loading && libraries.length === 0}
    <div class="state">正在读取资源库…</div>
  {:else if libraries.length === 0}
    <div class="state">尚未创建资源库</div>
  {:else}
    <div class="list">
      {#each libraries as lib, i (lib.id)}
        {@const sp = spark(lib.id)}
        <article class="row">
          <div class="order">
            <button
              type="button"
              class="ord"
              title="上移"
              aria-label={`上移 ${lib.name}`}
              disabled={i === 0 || busy.has('reorder')}
              onclick={() => void move(i, -1)}
            >▲</button>
            <button
              type="button"
              class="ord"
              title="下移"
              aria-label={`下移 ${lib.name}`}
              disabled={i === libraries.length - 1 || busy.has('reorder')}
              onclick={() => void move(i, 1)}
            >▼</button>
          </div>
          <div class="icon">▤</div>
          <div class="main">
            <div class="name">
              <h2>{lib.name}</h2>
              {#if lib.is_restricted}<span class="restricted">受限</span>{/if}
              {#if lib.scrape_mode !== 'none'}<span class="mode">刮削 {lib.scrape_mode}</span>{/if}
              <button
                type="button"
                class="flag"
                class:on={lib.watch_enabled !== false}
                disabled={busy.has(`watch_enabled-${lib.id}`)}
                title="目录监控：开启后文件增删会自动同步到媒体库"
                onclick={() => void toggleFlag(lib, 'watch_enabled')}
              >
                监控 {lib.watch_enabled === false ? '关' : '开'}
              </button>
              <button
                type="button"
                class="flag"
                class:on={lib.is_restricted === true}
                disabled={busy.has(`is_restricted-${lib.id}`)}
                title="受限内容：标记后需开启「显示限制内容」才可见"
                onclick={() => void toggleFlag(lib, 'is_restricted')}
              >
                受限 {lib.is_restricted ? '是' : '否'}
              </button>
            </div>
            <p title={lib.root_path}>{lib.root_path}</p>
          </div>
          <div class="stat"><strong>{lib.media_count ?? 0}</strong><span>媒体</span></div>
          <div class="stat" class:bad={(lib.missing_count ?? 0) > 0}>
            <strong>{lib.missing_count ?? 0}</strong><span>缺失</span>
          </div>
          <div class="stat"><strong>{formatSize(lib.total_size ?? 0)}</strong><span>占用</span></div>
          <div class="trend" title={`近 30 天变化：${delta(lib.id)}`}>
            {#if sp.ready}
              <svg viewBox="0 0 64 16" width="64" height="16" aria-hidden="true">
                <polyline
                  points={sp.points}
                  fill="none"
                  stroke="var(--accent)"
                  stroke-width="1.4"
                  stroke-linejoin="round"
                  stroke-linecap="round"
                />
              </svg>
            {:else}
              <span class="trend-empty">—</span>
            {/if}
            <span class="trend-delta">{delta(lib.id)}</span>
          </div>
          <div class="actions">
            <button
              type="button"
              disabled={busy.has(`scan-${lib.id}`)}
              onclick={() => void run(`scan-${lib.id}`, () => client.post(`/libraries/${lib.id}/scan`, {}), `已排队扫描「${lib.name}」`)}
            >
              扫描
            </button>
            <button
              type="button"
              disabled={lib.scrape_mode === 'none' || busy.has(`scrape-${lib.id}`)}
              title={lib.scrape_mode === 'none' ? '该库未启用刮削' : '排列刮削任务'}
              onclick={() => void run(`scrape-${lib.id}`, () => client.post(`/libraries/${lib.id}/scrape`, {}), `已排队刮削「${lib.name}」`)}
            >
              刮削
            </button>
            <button
              type="button"
              class="accent"
              onclick={() => goto(`/manage?section=assets&lib=${lib.id}`)}
            >
              资产
            </button>
          </div>
        </article>
      {/each}
    </div>
  {/if}

  <ToastHost />
</div>

<style>
  .libs {
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
  .btn.primary {
    border-color: var(--accent);
    background: var(--accent);
    color: #04120d;
  }
  .btn.icon {
    min-width: 32px;
  }
  .metrics {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
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
  .metrics .bad strong {
    color: var(--danger);
  }
  .list {
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
  }
  .row {
    display: grid;
    grid-template-columns: 30px 36px minmax(200px, 1fr) 78px 78px 96px 116px auto;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--rule);
  }
  .trend {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 1px;
    min-width: 0;
  }
  .trend svg {
    display: block;
    overflow: visible;
  }
  .trend-empty {
    color: var(--ink-faint);
    font-size: 11px;
  }
  .trend-delta {
    font-size: 10.5px;
    color: var(--ink-faint);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .row:last-child {
    border-bottom: 0;
  }
  .order {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .ord {
    font: inherit;
    font-size: 9px;
    line-height: 1;
    padding: 2px 0;
    border: none;
    background: transparent;
    color: var(--ink-faint);
    cursor: pointer;
  }
  .ord:hover:not(:disabled) {
    color: var(--accent);
  }
  .ord:disabled {
    opacity: 0.3;
    cursor: default;
  }
  .flag {
    font: inherit;
    font-size: 10.5px;
    padding: 1px 7px;
    border-radius: var(--radius-full);
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--ink-tertiary);
    cursor: pointer;
    white-space: nowrap;
  }
  .flag.on {
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
    color: var(--accent);
    background: var(--accent-soft);
  }
  .flag:hover:not(:disabled) {
    color: var(--ink);
  }
  .flag:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .icon {
    width: 34px;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-surface);
    color: var(--accent);
    border-radius: var(--radius-sm);
  }
  .main {
    min-width: 0;
  }
  .name {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .name h2 {
    margin: 0;
    font-size: 13.5px;
  }
  .restricted {
    padding: 1px 6px;
    border-radius: var(--radius-xs);
    background: var(--danger-soft);
    color: var(--danger);
    font-size: 11px;
  }
  .mode {
    padding: 1px 6px;
    border-radius: var(--radius-xs);
    background: var(--bg-surface);
    color: var(--ink-tertiary);
    font-size: 11px;
  }
  .main p {
    margin: 5px 0 0;
    color: var(--ink-tertiary);
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .stat {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .stat strong {
    font-size: 13.5px;
    font-variant-numeric: tabular-nums;
  }
  .stat span {
    color: var(--ink-tertiary);
    font-size: 11.5px;
  }
  .stat.bad strong {
    color: var(--danger);
  }
  .actions {
    display: flex;
    gap: 6px;
  }
  .actions button {
    font: inherit;
    font-size: 12px;
    min-height: 28px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius-xs);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    cursor: pointer;
  }
  .actions button:hover:not(:disabled) {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .actions button.accent {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
  }
  .actions button:disabled {
    opacity: 0.45;
    cursor: default;
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
</style>
