<script lang="ts">
  // 回收站视图 — 展示已软删除的媒体，支持恢复和彻底删除
  import { onMount } from 'svelte';
  import { client } from '$lib/api/client';
  import { formatSize, formatDate } from '$lib/utils/format';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

  interface RecycleItem {
    id: number;
    title: string;
    file_name: string;
    file_size: number | null;
    thumbnail_path: string | null;
    poster_path: string | null;
    library_id: number;
    deleted_at: string | null;
    file_missing: boolean;
    media_type: string;
    urls?: { url_role: string; is_expired: boolean }[];
  }

  // 检查回收站项目是否有可用的网络源
  function hasNetworkSource(item: RecycleItem): boolean {
    return !!item.urls?.some((u) => u.url_role === 'source' && !u.is_expired);
  }

  // 返回状态标签文本
  function statusLabel(item: RecycleItem): string {
    if (item.file_missing && hasNetworkSource(item)) return '🔗 网络可用';
    if (item.file_missing) return '⚠ 文件丢失';
    if (item.media_type === 'network' || item.media_type === 'both') return '🔗 含网络源';
    return '—';
  }

  let items = $state<RecycleItem[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let page = $state(1);
  const pageSize = 50;
  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  // 恢复相关
  let restoreTarget = $state<RecycleItem | null>(null);
  let restoreDialogOpen = $state(false);
  let restoreLibraryId = $state('');

  // 彻底删除
  let permanentTarget = $state<RecycleItem | null>(null);
  let permanentDialogOpen = $state(false);

  // 清空回收站
  let emptyDialogOpen = $state(false);

  function showToast(msg: string, type: 'ok' | 'err' = 'ok'): void {
    toast = { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 3000);
  }

  // 请求竞态守卫：防止并发 loadItems 时旧响应覆盖新数据
  let listReqId = 0;

  async function loadItems(): Promise<void> {
    const myId = ++listReqId;
    loading = true;
    try {
      let currentPage = page;
      let resp = await client.get<{ items: RecycleItem[]; total: number }>(
        `/recycle-bin?page=${currentPage}&page_size=${pageSize}`
      );
      if (myId !== listReqId) return;
      let list = resp.items;
      let totalCount = resp.total;
      // 当前页越界（如删除了本页最后一条）→ 回退到最后一页并重新加载，
      // 否则列表会停在空页，看起来"删除后没刷新"。
      const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
      if (currentPage > totalPages) {
        currentPage = totalPages;
        page = totalPages;
        resp = await client.get<{ items: RecycleItem[]; total: number }>(
          `/recycle-bin?page=${currentPage}&page_size=${pageSize}`
        );
        if (myId !== listReqId) return;
        list = resp.items;
        totalCount = resp.total;
      }
      items = list;
      total = totalCount;
    } catch {
      showToast('加载回收站失败', 'err');
    } finally {
      if (myId === listReqId) loading = false;
    }
  }

  onMount(() => {
    loadItems();
  });

  function openRestore(item: RecycleItem): void {
    restoreTarget = item;
    restoreDialogOpen = true;
  }

  async function confirmRestore(): Promise<void> {
    if (!restoreTarget) return;
    try {
      const params = restoreLibraryId
        ? `?target_library_id=${restoreLibraryId}`
        : '';
      await client.post(`/recycle-bin/${restoreTarget.id}/restore${params}`);
      showToast(`已恢复「${restoreTarget.title}」`);
      await loadItems();
    } catch (e) {
      const msg = e instanceof Error ? e.message : '恢复失败';
      showToast(msg, 'err');
    } finally {
      restoreDialogOpen = false;
      restoreTarget = null;
      restoreLibraryId = '';
    }
  }

  function openPermanent(item: RecycleItem): void {
    permanentTarget = item;
    permanentDialogOpen = true;
  }

  async function confirmPermanent(): Promise<void> {
    if (!permanentTarget) return;
    try {
      await client.delete(
        `/recycle-bin/${permanentTarget.id}/permanent?delete_file=true`
      );
      showToast(
        `已彻底删除「${permanentTarget.title}」（含本地文件与系统记录）`
      );
      await loadItems();
    } catch {
      showToast('彻底删除失败', 'err');
    } finally {
      permanentDialogOpen = false;
      permanentTarget = null;
    }
  }

  // 二次确认"仅删本地文件"：删磁盘文件 + 转 OFFLINE + 恢复媒体（虚拟网络文件，可继续经网络源播放）
  async function confirmPurgeLocal(): Promise<void> {
    if (!permanentTarget) return;
    try {
      await client.post(`/recycle-bin/${permanentTarget.id}/purge-local`, {});
      showToast(`已删除本地文件，「${permanentTarget.title}」已恢复到媒体页（标记为文件丢失，可经网络源播放）`);
      await loadItems();
    } catch {
      showToast('删除本地文件失败', 'err');
    } finally {
      permanentDialogOpen = false;
      permanentTarget = null;
    }
  }

  // 有本地文件 + 有可用网络源的回收站媒体，二次确认时提供"仅删本地文件"选项
  const canPurgeLocal = $derived(
    !!permanentTarget &&
      !permanentTarget.file_missing &&
      hasNetworkSource(permanentTarget)
  );

  async function confirmEmpty(): Promise<void> {
    try {
      const resp = await client.post<{ deleted_count: number }>(
        '/recycle-bin/empty?delete_files=true'
      );
      showToast(`已清空回收站，共删除 ${resp.deleted_count} 项（含本地文件）`);
      page = 1;
      await loadItems();
    } catch {
      showToast('清空失败', 'err');
    } finally {
      emptyDialogOpen = false;
    }
  }

  const totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));
</script>

<div class="recycle-view">
  <!-- 顶部警告条 -->
  <div class="warning-bar">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
    <span>回收站中的媒体记录将保留直到手动清除。「仅删本地文件」会把媒体恢复回媒体页并标记为"文件丢失"；「彻底删除」会同时删除本地文件和系统记录。</span>
    {#if total > 0}
      <button class="btn-empty" onclick={() => (emptyDialogOpen = true)}>清空回收站</button>
    {/if}
  </div>

  {#if loading}
    <div class="empty-state">加载中...</div>
  {:else if items.length === 0}
    <div class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
      </svg>
      <p>回收站为空</p>
    </div>
  {:else}
    <!-- 列表 -->
    <div class="recycle-list">
      <div class="list-header">
        <span class="col-thumb"></span>
        <span class="col-title">标题</span>
        <span class="col-status">状态</span>
        <span class="col-size">大小</span>
        <span class="col-date">删除时间</span>
        <span class="col-actions">操作</span>
      </div>
      {#each items as item (item.id)}
        <div class="list-row">
          <div class="col-thumb">
            {#if item.poster_path}
              <img src={`${import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8765'}/api/media/${item.id}/poster`} alt="" />
            {:else if item.thumbnail_path}
              <img src={`${import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8765'}/api/media/${item.id}/thumbnail`} alt="" />
            {:else}
              <div class="thumb-placeholder">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
                  <rect x="2" y="6" width="20" height="14" rx="2"/>
                  <path d="M2 10h20"/>
                </svg>
              </div>
            {/if}
          </div>
          <div class="col-title" title={item.title}>{item.title}</div>
          <div class="col-status">
            <span class="status-tag" class:net={item.file_missing && hasNetworkSource(item)} class:missing={item.file_missing && !hasNetworkSource(item)}>
              {statusLabel(item)}
            </span>
          </div>
          <div class="col-size">{item.file_size ? formatSize(item.file_size) : '-'}</div>
          <div class="col-date">
            {item.deleted_at ? formatDate(item.deleted_at) : '-'}
          </div>
          <div class="col-actions">
            <button class="btn-restore" onclick={() => openRestore(item)}>恢复</button>
            <button class="btn-permanent" onclick={() => openPermanent(item)}>彻底删除</button>
          </div>
        </div>
      {/each}
    </div>

    <!-- 分页 -->
    {#if totalPages > 1}
      <div class="pagination">
        <button disabled={page <= 1} onclick={() => { page--; loadItems(); }}>上一页</button>
        <span>{page} / {totalPages}</span>
        <button disabled={page >= totalPages} onclick={() => { page++; loadItems(); }}>下一页</button>
      </div>
    {/if}
  {/if}
</div>

<!-- 恢复确认对话框 -->
<ConfirmDialog
  bind:open={restoreDialogOpen}
  title="恢复媒体"
  description={restoreTarget ? `确认恢复「${restoreTarget.title}」？` : ''}
  confirmText="恢复"
  onconfirm={confirmRestore}
/>

<!-- 彻底删除确认对话框（有本地文件+网络源时，可改选"仅删本地文件"） -->
<ConfirmDialog
  bind:open={permanentDialogOpen}
  title="彻底删除"
  description={permanentTarget ? (hasNetworkSource(permanentTarget)
    ? `「${permanentTarget.title}」含网络源。\n\n选择「仅删本地文件」：删除磁盘文件，但媒体会恢复回媒体页并标记为"文件丢失"（记录/标签/元数据保留，可经网络源继续播放）。\n选择「确认删除」：本地文件、媒体记录与所有网络源将一并永久删除，不可撤销。`
    : `「${permanentTarget.title}」将被永久删除，本地文件和系统记录会一并清除，此操作不可撤销。`)
    : ''}
  confirmText="确认删除"
  danger={true}
  extraButtonText={canPurgeLocal ? '仅删本地文件' : ''}
  onextra={confirmPurgeLocal}
  onconfirm={confirmPermanent}
/>

<!-- 清空回收站确认对话框 -->
<ConfirmDialog
  bind:open={emptyDialogOpen}
  title="清空回收站"
  description={`将永久删除回收站中的全部 ${total} 项记录及其本地文件，此操作不可撤销。`}
  confirmText="全部清空"
  danger={true}
  onconfirm={confirmEmpty}
/>

{#if toast}
  <div class="toast" class:err={toast.type === 'err'}>{toast.msg}</div>
{/if}

<style>
  .recycle-view {
    padding: 16px 24px;
    height: 100%;
    overflow-y: auto;
  }
  .warning-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: rgba(245, 158, 11, 0.1);
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: 8px;
    margin-bottom: 16px;
    font-size: 13px;
    color: #f59e0b;
  }
  .warning-bar span {
    flex: 1;
  }
  .btn-empty {
    padding: 4px 12px;
    border: 1px solid #ef4444;
    border-radius: 6px;
    background: transparent;
    color: #ef4444;
    font-size: 12px;
    cursor: pointer;
  }
  .btn-empty:hover {
    background: rgba(239, 68, 68, 0.1);
  }
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 80px 0;
    color: var(--text-tertiary, #888);
    font-size: 14px;
  }
  .recycle-list {
    border: 1px solid var(--border, rgba(255,255,255,0.08));
    border-radius: 8px;
    overflow: hidden;
  }
  .list-header,
  .list-row {
    display: grid;
    grid-template-columns: 48px 1fr 90px 80px 140px 140px;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
  }
  .list-header {
    font-size: 12px;
    color: var(--text-tertiary, #888);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: var(--bg-elevated, rgba(255,255,255,0.03));
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
  }
  .list-row {
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.04));
    font-size: 13px;
  }
  .list-row:hover {
    background: var(--bg-hover, rgba(255,255,255,0.03));
  }
  .col-thumb img {
    width: 36px;
    height: 24px;
    object-fit: cover;
    border-radius: 4px;
  }
  .thumb-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 24px;
  }
  .col-title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .col-status {
    font-size: 11.5px;
    white-space: nowrap;
  }
  .status-tag {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    color: var(--text-tertiary, #888);
    background: var(--bg-elevated, rgba(255,255,255,0.03));
  }
  .status-tag.net {
    color: #635bff;
    background: rgba(99, 91, 255, 0.1);
  }
  .status-tag.missing {
    color: #ef4444;
    background: rgba(239, 68, 68, 0.1);
  }
  .col-actions {
    display: flex;
    gap: 6px;
  }
  .btn-restore {
    padding: 3px 10px;
    border: 1px solid var(--accent, #635bff);
    border-radius: 4px;
    background: transparent;
    color: var(--accent, #635bff);
    font-size: 12px;
    cursor: pointer;
  }
  .btn-restore:hover {
    background: rgba(99, 91, 255, 0.1);
  }
  .btn-permanent {
    padding: 3px 10px;
    border: 1px solid #ef4444;
    border-radius: 4px;
    background: transparent;
    color: #ef4444;
    font-size: 12px;
    cursor: pointer;
  }
  .btn-permanent:hover {
    background: rgba(239, 68, 68, 0.1);
  }
  .pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 12px;
    margin-top: 16px;
    font-size: 13px;
  }
  .pagination button {
    padding: 4px 12px;
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    border-radius: 6px;
    background: transparent;
    color: var(--text-primary, #fff);
    cursor: pointer;
  }
  .pagination button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    padding: 8px 20px;
    background: var(--accent, #635bff);
    color: #fff;
    border-radius: 8px;
    font-size: 14px;
    z-index: 1000;
  }
  .toast.err {
    background: #ef4444;
  }
</style>
