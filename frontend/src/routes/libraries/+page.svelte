<script lang="ts">
  // 资源库配置页：管理所有资源库
  // 后端 LibraryResponse 含完整字段（type / scrape_mode / watch_enabled / media_count）
  // 使用 client 直接获取完整数据（前端 libraries.ts 接口较精简）
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { client, ApiError } from '$lib/api/client';
  import { librariesApi } from '$lib/api/libraries';
  import { formatNumber } from '$lib/utils/format';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { tasks } from '$lib/stores/tasks.svelte';

  interface LibraryFull {
    id: number;
    name: string;
    type: string;
    root_path: string;
    scrape_mode: string;
    is_restricted: boolean;
    watch_enabled: boolean;
    auto_import: boolean;
    auto_mark_missing: boolean;
    description: string | null;
    color: string | null;
    sort_order: number;
    created_at: string;
    updated_at: string;
    media_count: number;
  }

  type ScrapeMode = 'none' | 'movie' | 'tv' | 'av' | 'custom';

  // ---- 状态 ----
  let libraries = $state<LibraryFull[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);

  // 编辑对话框
  let editOpen = $state(false);
  let editing = $state<LibraryFull | null>(null);
  let editName = $state('');
  let editScrape = $state<ScrapeMode>('none');
  let editWatch = $state(true);
  let editRestricted = $state(false);
  let saving = $state(false);

  // 删除确认
  let deleteOpen = $state(false);
  let deleteTarget = $state<LibraryFull | null>(null);
  let deleteCleanTags = $state(true);  // 默认勾选清理空标签
  let deleting = $state(false);

  // 扫描中的库
  let scanningIds = $state<Set<number>>(new Set());

  // toast
  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  function showToast(msg: string, type: 'ok' | 'err' = 'ok'): void {
    toast = { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2600);
  }

  // 扫描轮询定时器集合（组件销毁时统一清理）
  const scanTimers = new Set<ReturnType<typeof setTimeout>>();
  function addScanTimer(fn: () => void, delay: number): ReturnType<typeof setTimeout> {
    const id = setTimeout(() => {
      scanTimers.delete(id);
      fn();
    }, delay);
    scanTimers.add(id);
    return id;
  }
  function clearScanTimers(): void {
    for (const id of scanTimers) clearTimeout(id);
    scanTimers.clear();
  }

  // clearScanTimers 此前定义了却从未调用：扫描中离开本页，轮询定时器会继续
  // 触发并写已销毁组件的 $state。
  onDestroy(() => {
    clearScanTimers();
    if (toastTimer) clearTimeout(toastTimer);
  });

  const scrapeLabels: Record<string, string> = {
    none: '不刮削',
    movie: '电影',
    tv: '电视剧',
    av: '限制内容',
    custom: '自定义'
  };

  const typeLabels: Record<string, string> = {
    video: '视频',
    audio: '音频',
    document: '文档'
  };

  const scrapeOptions: { value: ScrapeMode; label: string }[] = [
    { value: 'none', label: '不刮削' },
    { value: 'movie', label: '电影' },
    { value: 'tv', label: '电视剧' },
    { value: 'av', label: '限制内容' },
    { value: 'custom', label: '自定义' }
  ];

  // ---- 加载 ----
  async function loadLibraries(): Promise<void> {
    loading = true;
    error = null;
    try {
      const list = await client.get<LibraryFull[]>('/libraries');
      libraries = list ?? [];
    } catch (e) {
      error = e instanceof ApiError ? '加载资源库失败' : '加载失败，请检查后端服务';
    } finally {
      loading = false;
    }
  }

  // ---- 新建（跳转导入向导） ----
  function goImport(): void {
    goto('/import');
  }

  // ---- 编辑 ----
  function startEdit(lib: LibraryFull): void {
    editing = lib;
    editName = lib.name;
    editScrape = (lib.scrape_mode as ScrapeMode) ?? 'none';
    editWatch = lib.watch_enabled;
    editRestricted = lib.is_restricted ?? false;
    editOpen = true;
  }

  async function saveEdit(): Promise<void> {
    if (!editing) return;
    const id = editing.id;
    saving = true;
    try {
      const updated = await client.put<LibraryFull>(`/libraries/${id}`, {
        name: editName.trim(),
        scrape_mode: editScrape,
        watch_enabled: editWatch,
        is_restricted: editRestricted
      });
      libraries = libraries.map((l) => (l.id === id ? { ...l, ...updated } : l));
      librariesStore.reload();  // 同步侧边栏
      editOpen = false;
      showToast('已保存修改');
    } catch {
      showToast('保存失败', 'err');
    } finally {
      saving = false;
    }
  }

  // ---- 扫描 ----
  async function scanLibrary(lib: LibraryFull): Promise<void> {
    scanningIds = new Set(scanningIds).add(lib.id);
    showToast(`正在扫描「${lib.name}」…`);
    try {
      const res = await client.post<{ task_id: number; status: string }>(`/libraries/${lib.id}/scan`);
      // Poll the task until complete, then refresh (M7 fix: replace hardcoded 3s)
      const taskId = res?.task_id;
      if (taskId) {
        void tasks.refresh(); // 立即更新顶栏任务徽标
        const poll = async () => {
          try {
            const t = await client.get<{ status: string }>(`/tasks/${taskId}`);
            if (t && (t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled')) {
              await loadLibraries();
              scanningIds = new Set([...scanningIds].filter((id) => id !== lib.id));
            } else {
              addScanTimer(poll, 1500);
            }
          } catch {
            // On poll failure, fall back to delayed refresh
            addScanTimer(async () => {
              await loadLibraries();
              scanningIds = new Set([...scanningIds].filter((id) => id !== lib.id));
            }, 3000);
          }
        };
        addScanTimer(poll, 1500);
      } else {
        // No task_id — old fallback
        addScanTimer(async () => {
          await loadLibraries();
          scanningIds = new Set([...scanningIds].filter((id) => id !== lib.id));
        }, 3000);
      }
    } catch {
      showToast('扫描启动失败', 'err');
      scanningIds = new Set([...scanningIds].filter((id) => id !== lib.id));
    }
  }

  // ---- 删除 ----
  function askDelete(lib: LibraryFull): void {
    deleteTarget = lib;
    deleting = false;
    deleteCleanTags = true;  // 每次打开默认勾选
    deleteOpen = true;
  }

  function cancelDelete(): void {
    if (deleting) return;
    deleteOpen = false;
    deleteTarget = null;
  }

  async function confirmDelete(): Promise<void> {
    if (!deleteTarget || deleting) return;
    const target = deleteTarget;
    const cleanTags = deleteCleanTags;
    deleting = true;
    try {
      const result = await librariesApi.delete(String(target.id), cleanTags);
      libraries = libraries.filter((l) => l.id !== target.id);
      librariesStore.reload();  // 同步侧边栏
      const cleaned = result?.cleaned_tags_count ?? 0;
      if (cleanTags && cleaned > 0) {
        showToast(`已删除资源库，清理了 ${cleaned} 个空标签`);
      } else {
        showToast('已删除资源库');
      }
    } catch {
      showToast('删除失败', 'err');
    } finally {
      deleting = false;
      deleteOpen = false;
      deleteTarget = null;
    }
  }

  const totalMedia = $derived(libraries.reduce((s, l) => s + (l.media_count ?? 0), 0));

  // 安全校验颜色值：仅允许 #RRGGBB 格式，避免任意字符串注入到 style
  const safeColor = (c: string | null | undefined): string =>
    /^#[0-9a-fA-F]{6}$/.test(c ?? '') ? (c as string) : '';

  onMount(() => {
    loadLibraries();
    return () => {
      clearScanTimers();
      if (toastTimer) clearTimeout(toastTimer);
    };
  });
</script>

<svelte:head><title>资源库 — vitoice</title></svelte:head>

<div class="lib-page">
  <div class="page-head">
    <div class="head-left">
      <h1>资源库</h1>
      <p>管理所有媒体资源库的扫描、刮削与监控配置。</p>
    </div>
    <div class="head-right">
      <div class="stat-pill">
        <span class="stat-num">{formatNumber(libraries.length)}</span>
        <span class="stat-label">个库</span>
      </div>
      <div class="stat-pill">
        <span class="stat-num">{formatNumber(totalMedia)}</span>
        <span class="stat-label">个媒体</span>
      </div>
      <button class="btn primary" onclick={goImport}>+ 新建库</button>
    </div>
  </div>

  {#if loading}
    <div class="state">加载中…</div>
  {:else if error}
    <div class="state error">{error}</div>
  {:else if libraries.length === 0}
    <div class="empty-state">
      <div class="empty-icon">📂</div>
      <h2>还没有资源库</h2>
      <p>创建第一个资源库，开始导入和管理你的媒体文件。</p>
      <button class="btn primary" onclick={goImport}>前往导入向导</button>
    </div>
  {:else}
    <div class="lib-table">
      <div class="table-head">
        <div class="col-name">名称</div>
        <div class="col-path">路径</div>
        <div class="col-type">类型</div>
        <div class="col-scrape">刮削模式</div>
        <div class="col-watch">监控</div>
        <div class="col-count">媒体数</div>
        <div class="col-actions">操作</div>
      </div>
      {#each libraries as lib (lib.id)}
        <div class="table-row">
          <div class="col-name">
            <span class="lib-dot" style={`background:${safeColor(lib.color) || 'var(--accent)'}`}></span>
            <span class="lib-name">{lib.name}</span>
            {#if lib.is_restricted}
              <span class="restricted-tag" title="限制内容库">18+</span>
            {/if}
          </div>
          <div class="col-path" title={lib.root_path}>
            <span class="path-text">{lib.root_path}</span>
          </div>
          <div class="col-type">
            <span class="badge">{typeLabels[lib.type] ?? lib.type}</span>
          </div>
          <div class="col-scrape">
            <span class="scrape-tag">{scrapeLabels[lib.scrape_mode] ?? lib.scrape_mode}</span>
          </div>
          <div class="col-watch">
            <span class="watch-pill" class:on={lib.watch_enabled}>
              {lib.watch_enabled ? '已启用' : '未启用'}
            </span>
          </div>
          <div class="col-count">
            <span class="count-num">{formatNumber(lib.media_count ?? 0)}</span>
          </div>
          <div class="col-actions">
            <button class="action-btn edit" title="编辑" onclick={() => startEdit(lib)}>编辑</button>
            <button
              class="action-btn scan"
              title="扫描"
              onclick={() => scanLibrary(lib)}
              disabled={scanningIds.has(lib.id)}
            >
              {scanningIds.has(lib.id) ? '扫描中…' : '扫描'}
            </button>
            <button class="action-btn danger" title="删除" onclick={() => askDelete(lib)}>删除</button>
          </div>
        </div>
      {/each}
    </div>

    <div class="page-foot">
      <div class="foot-note">
        <strong>说明：</strong>删除资源库仅会从软件记录中移除该库及其媒体索引，<u>不会删除磁盘上的实际文件</u>。
        删除时可选择是否同时清理因此变空的标签（内置标签不会被删除）。
      </div>
    </div>
  {/if}
</div>

<!-- 编辑对话框 -->
{#if editOpen}
  <div class="modal-overlay" onclick={() => !saving && (editOpen = false)}>
    <div class="modal" onclick={(e) => e.stopPropagation()}>
      <h3>编辑资源库</h3>
      {#if editing}
        <div class="modal-body">
          <div class="form-group">
            <label for="edit-lib-name">库名称</label>
            <input id="edit-lib-name" type="text" class="text-input" bind:value={editName} placeholder="库名称" />
          </div>
          <div class="form-group">
            <label for="edit-lib-path">路径</label>
            <input id="edit-lib-path" type="text" class="text-input readonly" value={editing.root_path} readonly />
          </div>
          <div class="form-group">
            <label for="edit-lib-scrape">刮削模式</label>
            <select id="edit-lib-scrape" class="select-input" bind:value={editScrape}>
              {#each scrapeOptions as o (o.value)}
                <option value={o.value}>{o.label}</option>
              {/each}
            </select>
          </div>
          <div class="form-group toggle-row">
            <div>
              <div class="toggle-label">启用文件监控</div>
              <div class="toggle-hint">目录变化时自动更新媒体记录</div>
            </div>
            <button
              type="button"
              class="toggle"
              class:on={editWatch}
              onclick={() => (editWatch = !editWatch)}
              role="switch"
              aria-checked={editWatch}
            >
              <span class="knob"></span>
            </button>
          </div>
          <div class="form-group toggle-row">
            <div>
              <div class="toggle-label">限制内容</div>
              <div class="toggle-hint">标记为限制的库在「显示限制内容」关闭时隐藏</div>
            </div>
            <button
              type="button"
              class="toggle"
              class:on={editRestricted}
              onclick={() => (editRestricted = !editRestricted)}
              role="switch"
              aria-checked={editRestricted}
            >
              <span class="knob"></span>
            </button>
          </div>
        </div>
      {/if}
      <div class="modal-actions">
        <button class="btn ghost" onclick={() => (editOpen = false)} disabled={saving}>取消</button>
        <button class="btn primary" onclick={saveEdit} disabled={saving || !editName.trim()}>
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- 删除确认对话框 -->
{#if deleteOpen}
  <div
    class="modal-overlay"
    onclick={() => cancelDelete()}
    onkeydown={(e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        cancelDelete();
      }
    }}
    role="presentation"
  >
    <div
      class="modal delete-modal"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-lib-title"
      tabindex="-1"
    >
      <h3 id="delete-lib-title">删除资源库</h3>
      <div class="delete-body">
        {#if deleteTarget}
          <p class="delete-target">
            确定删除资源库「<strong>{deleteTarget.name}</strong>」？（共
            {formatNumber(deleteTarget.media_count ?? 0)} 个媒体）
          </p>
        {/if}
        <p class="delete-desc">
          删除资源库将同时删除其中所有媒体，不会删除磁盘上的实际文件。
        </p>
        <label class="delete-checkbox">
          <input type="checkbox" bind:checked={deleteCleanTags} disabled={deleting} />
          <span>同时清理因此变空的标签（内置标签不会被删除）</span>
        </label>
      </div>
      <div class="modal-actions delete-actions">
        <button class="btn ghost" onclick={() => cancelDelete()} disabled={deleting}>
          取消
        </button>
        <button
          class="btn danger"
          onclick={() => confirmDelete()}
          disabled={deleting}
        >
          {deleting ? '删除中…' : '删除资源库'}
        </button>
      </div>
    </div>
  </div>
{/if}

{#if toast}
  <div class="toast" class:ok={toast.type === 'ok'} class:err={toast.type === 'err'}>{toast.msg}</div>
{/if}

<style>
  .lib-page {
    flex: 1;
    overflow-y: auto;
    padding: 24px 28px 40px;
  }

  .page-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 24px;
  }

  .head-left h1 {
    margin: 0 0 4px;
    font-size: 22px;
    font-weight: 700;
    color: var(--ink);
  }

  .head-left p {
    margin: 0;
    font-size: 13px;
    color: var(--ink-tertiary);
  }

  .head-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .stat-pill {
    display: flex;
    align-items: baseline;
    gap: 4px;
    padding: 6px 14px;
    background: var(--bg-surface);
    border-radius: var(--radius-full);
  }

  .stat-num {
    font-size: 16px;
    font-weight: 700;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }

  .stat-label {
    font-size: 12px;
    color: var(--ink-tertiary);
  }

  .btn {
    height: 36px;
    padding: 0 16px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .btn:hover:not(:disabled) {
    border-color: var(--ink-tertiary);
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn.ghost {
    background: var(--bg-surface);
  }

  .btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .btn.primary:hover:not(:disabled) {
    filter: brightness(1.08);
  }

  .btn.danger {
    background: #ff3b30;
    border-color: #ff3b30;
    color: #fff;
  }

  .btn.danger:hover:not(:disabled) {
    filter: brightness(1.08);
  }

  /* ---- 空状态 ---- */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px 20px;
    text-align: center;
  }

  .empty-icon {
    font-size: 48px;
    opacity: 0.5;
    margin-bottom: 16px;
  }

  .empty-state h2 {
    margin: 0 0 8px;
    font-size: 18px;
    color: var(--ink);
  }

  .empty-state p {
    margin: 0 0 20px;
    font-size: 13px;
    color: var(--ink-tertiary);
  }

  .state {
    padding: 80px 0;
    text-align: center;
    color: var(--ink-tertiary);
    font-size: 14px;
  }

  .state.error {
    color: #ff3b30;
  }

  /* ---- 表格 ---- */
  .lib-table {
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    overflow: hidden;
    background: var(--bg-elevated);
  }

  .table-head {
    display: grid;
    grid-template-columns: 1.4fr 2.2fr 0.8fr 1fr 0.9fr 0.8fr 1.4fr;
    gap: 0;
    padding: 12px 16px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--rule);
    font-size: 11.5px;
    font-weight: 600;
    color: var(--ink-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .table-row {
    display: grid;
    grid-template-columns: 1.4fr 2.2fr 0.8fr 1fr 0.9fr 0.8fr 1.4fr;
    gap: 0;
    padding: 12px 16px;
    border-bottom: 1px solid var(--rule);
    align-items: center;
    transition: background 200ms;
  }

  .table-row:last-child {
    border-bottom: none;
  }

  .table-row:hover {
    background: var(--bg-surface);
  }

  .col-name {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .lib-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .lib-name {
    font-size: 13.5px;
    font-weight: 600;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .col-path {
    min-width: 0;
  }

  .path-text {
    font-size: 12px;
    color: var(--ink-tertiary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: block;
    font-family: 'SF Mono', 'Monaco', monospace;
  }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    background: var(--bg-surface);
    border-radius: var(--radius-full);
    font-size: 11.5px;
    color: var(--ink);
  }

  .scrape-tag {
    font-size: 12.5px;
    color: var(--ink);
  }

  .restricted-tag {
    display: inline-block;
    padding: 1px 6px;
    background: rgba(255, 59, 48, 0.15);
    color: #ff3b30;
    border-radius: var(--radius-full);
    font-size: 10.5px;
    font-weight: 700;
    line-height: 1.4;
  }

  .watch-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    font-size: 11.5px;
    background: var(--bg-surface);
    color: var(--ink-tertiary);
  }

  .watch-pill.on {
    background: var(--ok-soft);
    color: var(--ok);
  }

  .count-num {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
  }

  .col-actions {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
  }

  .action-btn {
    height: 28px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 12px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .action-btn:hover:not(:disabled) {
    border-color: var(--ink-tertiary);
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .action-btn.edit:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  .action-btn.scan:hover:not(:disabled) {
    border-color: var(--accent2);
    color: var(--accent2);
  }

  .action-btn.danger:hover {
    border-color: #ff3b30;
    color: #ff3b30;
  }

  /* ---- 页脚说明 ---- */
  .page-foot {
    margin-top: 16px;
  }

  .foot-note {
    padding: 12px 16px;
    background: var(--bg-surface);
    border-radius: var(--radius);
    font-size: 12px;
    color: var(--ink-tertiary);
    line-height: 1.6;
  }

  .foot-note strong {
    color: var(--ink);
  }

  .foot-note u {
    color: var(--accent2);
  }

  /* ---- Modal ---- */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fade-in 200ms ease;
  }

  .modal {
    width: 440px;
    max-width: 90vw;
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    padding: 24px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
  }

  .modal h3 {
    margin: 0 0 16px;
    font-size: 17px;
    color: var(--ink);
  }

  .modal-body {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-bottom: 20px;
  }

  .form-group label {
    display: block;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 6px;
  }

  .text-input {
    width: 100%;
    height: 36px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 200ms;
  }

  .text-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .text-input.readonly {
    background: var(--bg-surface);
    color: var(--ink-tertiary);
  }

  .select-input {
    width: 100%;
    height: 36px;
    padding: 0 28px 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 200ms;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236e6e73'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
  }

  .select-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .toggle-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
  }

  .toggle-hint {
    font-size: 11.5px;
    color: var(--ink-tertiary);
    margin-top: 2px;
  }

  .toggle {
    width: 42px;
    height: 24px;
    border-radius: var(--radius-full);
    background: var(--rule);
    border: none;
    padding: 2px;
    display: flex;
    align-items: center;
    transition: background 200ms ease;
    flex-shrink: 0;
    cursor: pointer;
  }

  .toggle.on {
    background: var(--accent);
  }

  .knob {
    width: 20px;
    height: 20px;
    border-radius: var(--radius-full);
    background: #fff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    transition: transform 200ms ease;
  }

  .toggle.on .knob {
    transform: translateX(18px);
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  /* ---- 删除确认对话框 ---- */
  .delete-modal {
    width: 480px;
    max-width: 92vw;
  }

  .delete-body {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 20px;
  }

  .delete-target {
    margin: 0;
    font-size: 14px;
    color: var(--ink);
    line-height: 1.6;
  }

  .delete-target strong {
    font-weight: 700;
  }

  .delete-desc {
    margin: 0;
    font-size: 13px;
    color: var(--ink-tertiary);
    line-height: 1.7;
  }

  .delete-checkbox {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-top: 12px;
    font-size: 12.5px;
    color: var(--ink-secondary);
    cursor: pointer;
    user-select: none;
  }
  .delete-checkbox input {
    flex-shrink: 0;
    margin-top: 2px;
    cursor: pointer;
  }

  .delete-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  @keyframes fade-in {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  /* ---- Toast ---- */
  .toast {
    position: fixed;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 18px;
    border-radius: var(--radius-full);
    font-size: 13px;
    z-index: 2000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    color: #fff;
    animation: toast-in 200ms ease;
  }

  .toast.ok {
    background: var(--ok);
  }

  .toast.err {
    background: #ff3b30;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translate(-50%, 10px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  /* ---- 响应式 ---- */
  @media (max-width: 900px) {
    .table-head,
    .table-row {
      grid-template-columns: 1fr 1.5fr 0.7fr 0.9fr 0.8fr 0.7fr 1.2fr;
      font-size: 12px;
    }

    .head-right {
      flex-wrap: wrap;
    }
  }
</style>
