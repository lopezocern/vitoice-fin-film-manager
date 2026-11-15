<script lang="ts">
  // 资产工作台 — 管理页唯一的列表层（PR3）。
  //
  // 职责边界：
  //   · 拥有 MediaQueryState（从真实 URL 初始化，改动写回 URL）
  //   · 摘要条 + 工具栏 + 表格/网格 + 批量操作
  //   · 不做任何客户端过滤：状态筛选全部走服务端谓词（PR1）
  //
  // 与旧实现的关系：旧 `?section=files` 的管理表已在 PR6 删除，旧 URL 由
  // `routes/manage/+page.ts` 307 重定向到这里；本组件是管理页唯一的列表层。
  import { untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { client } from '$lib/api/client';
  import { librariesApi } from '$lib/api/libraries';
  import { mediaApi, type Media } from '$lib/api/media';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { toasts } from '$lib/stores/toast.svelte';
  import { folderTree } from '$lib/stores/folderTree.svelte';
  import { tasks } from '$lib/stores/tasks.svelte';
  import { realSearchParams } from '$lib/utils/urlState';
  import {
    applyPatch,
    DEFAULT_MEDIA_QUERY,
    parseMediaQuery,
    serializeMediaQuery,
    type MediaQueryState
  } from '$lib/media/query';
  import type { SavedViewId } from '$lib/media/status';
  import { savedView } from '$lib/media/views';
  import { createMediaList } from '$lib/media/useMediaList.svelte';
  import { buildMediaQuery } from '$lib/media/query';
  import { loadScroll, saveScroll, scrollKey } from '$lib/media/assetsScroll';
  import { chunkIds } from '$lib/media/batch';
  import { pageList } from '$lib/utils/pagination';
  import AssetsSummary from './AssetsSummary.svelte';
  import AssetsToolbar from './AssetsToolbar.svelte';
  import AssetsFolderBar from './AssetsFolderBar.svelte';
  import DuplicatesDialog from './DuplicatesDialog.svelte';
  import ReconcileDialog from './ReconcileDialog.svelte';
  import NetworkImportDialog from './NetworkImportDialog.svelte';
  import AssetsTable from './AssetsTable.svelte';
  import AssetsGrid from './AssetsGrid.svelte';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
  import EditMediaDialog from './EditMediaDialog.svelte';
  import ToastHost from '$lib/components/common/ToastHost.svelte';
  import { errorMessage } from '$lib/utils/errors';

  /** 统计字段 → 摘要条用的计数。 */
  type SummaryCounts = Partial<Record<string, number>>;

  interface BatchResponse {
    action: string;
    total: number;
    success_count: number;
    failed: { id: number; error: string }[];
    task_id: number | null;
    export_url: string | null;
    message: string;
  }

  // ---- 查询状态：从真实 URL 初始化（popstate 下 $page.url 会丢 query）----
  let query = $state<MediaQueryState>(parseMediaQuery(realSearchParams(), DEFAULT_MEDIA_QUERY));

  const list = createMediaList({
    getState: () => query,
    onLoaded: (items) => {
      // 选中集只保留仍在列表里的项，避免跨页残留
      const alive = new Set(items.map((m) => Number(m.id)));
      selected = new Set([...selected].filter((id) => alive.has(id)));
    }
  });

  let selected = $state<Set<number>>(new Set());
  // 跨页全选：选中集来自"当前筛选结果的全部 id"，而不是当前页
  let selectAllMode = $state(false);
  let selectingAll = $state(false);
  // 分片批量提交的进度（null = 空闲）
  let progress = $state<{ done: number; total: number } | null>(null);
  /** 当前批量操作的取消句柄；非 null 表示有操作在跑。 */
  let batchAbort = $state<AbortController | null>(null);
  let counts = $state<SummaryCounts>({});
  let countsLoading = $state(false);
  let busy = $state<string | null>(null);
  let deleteOpen = $state(false);
  let ratingValue = $state(3);
  let tagPick = $state('');
  // 行内编辑（复用既有 EditMediaDialog，旧管理页也是这么用的）
  let editOpen = $state(false);
  let editing = $state<Media | null>(null);
  // 治理工具对话框（重构期间随旧组件一起失去入口，PR‑A 恢复）
  let duplicatesOpen = $state(false);
  let reconcileOpen = $state(false);
  let networkImportOpen = $state(false);
  // 移动库 / 模板改名（内联在批处理栏，避免为两个输入再开对话框）
  let moveTarget = $state('');
  let renameTemplate = $state('{title} ({year})');
  // 移动到目录（同库内，相对库根）
  let targetDir = $state('');

  // 花括号不能直接写在模板属性里（Svelte 会当表达式解析），用常量注入
  const RENAME_HINT = '改名模板，可用 {title} {year} {series} {season} {episode}';
  const RENAME_PLACEHOLDER = '{title} ({year})';

  const selectedMedia = $derived(list.items.filter((m) => selected.has(Number(m.id))));
  const pageCount = $derived(
    query.pageSize > 0 ? Math.max(1, Math.ceil(list.total / query.pageSize)) : 1
  );
  const pageButtons = $derived(pageList(query.page, pageCount, 7));

  const libraryName = (id: string): string =>
    librariesStore.libraries.find((l) => String(l.id) === String(id))?.name ?? '—';

  // ---- 加载 ----
  async function loadCounts(): Promise<void> {
    countsLoading = true;
    try {
      const resp = await client.get<{ summary: SummaryCounts }>(
        '/stats/summary',
        undefined,
        undefined,
        true
      );
      counts = resp.summary ?? {};
    } catch {
      counts = {};
    } finally {
      countsLoading = false;
    }
  }

  /** 把当前 query 写回 URL（replaceState：不产生历史条目，返回键行为不变）。 */
  function syncUrl(): void {
    const sp = serializeMediaQuery(query);
    sp.set('section', 'assets');
    goto(`/manage?${sp.toString()}`, { replaceState: true, noScroll: true, keepFocus: true });
  }

  function patch(partial: Partial<MediaQueryState>): void {
    // 换库清目录等规则集中在 applyPatch（见 lib/media/query.ts）
    query = applyPatch(query, partial);
  }

  function resetFilters(): void {
    const view = query.view;
    query = { ...DEFAULT_MEDIA_QUERY, view };
  }

  function selectView(view: SavedViewId): void {
    patch({ view, page: 1 });
  }

  function setPage(page: number): void {
    const next = Math.min(Math.max(1, page), pageCount);
    patch({ page: next });
  }

  // ---- 选中 ----
  function toggleOne(id: string): void {
    const n = Number(id);
    const next = new Set(selected);
    if (next.has(n)) next.delete(n);
    else next.add(n);
    selected = next;
  }

  function toggleAll(ids: string[], checked: boolean): void {
    const next = new Set(selected);
    for (const id of ids) {
      const n = Number(id);
      if (checked) next.add(n);
      else next.delete(n);
    }
    selected = next;
  }

  function clearSelection(): void {
    selected = new Set();
    selectAllMode = false;
  }

  // ---- 批量操作 ----
  /** 后端 `BatchActionRequest.media_ids` 单次上限（max_length=1000）。 */
  const BATCH_CHUNK = 1000;

  /**
   * 跨页全选：向 `/media?ids_only=true` 要"当前筛选条件匹配的全部 id"。
   * 只传 id 不传对象——874 条约 3.4MB 的完整对象，上万条就是几十 MB。
   */
  async function selectAllMatching(): Promise<void> {
    if (selectingAll) return;
    selectingAll = true;
    try {
      const res = await mediaApi.listIds(buildMediaQuery(query));
      selected = new Set(res.ids);
      selectAllMode = true;
      toasts.push(`已选中全部 ${res.ids.length} 项（跨页）`);
    } catch (e) {
      toasts.push(errorMessage(e, '选取失败'), 'err');
    } finally {
      selectingAll = false;
    }
  }

  async function runBatch(action: string, params: Record<string, unknown> = {}): Promise<BatchResponse | null> {
    const ids = [...selected];
    if (ids.length === 0) return null;
    busy = action;
    progress = { done: 0, total: ids.length };
    const controller = new AbortController();
    batchAbort = controller;
    try {
      // 后端单次最多 1000 个 id（Pydantic max_length），超出必须切片顺序提交
      const chunks = chunkIds(ids);

      let success = 0;
      let failedCount = 0;
      let firstFailure: { id: number; error: string } | undefined;
      const taskIds: number[] = [];
      const succeededIds: number[] = [];
      let lastMessage = '';
      let canceled = false;

      for (const chunk of chunks) {
        // 点击「取消」后：在途请求会被 abort，这里把已完成的片数如实汇报
        if (controller.signal.aborted) {
          canceled = true;
          break;
        }
        const resp = await client.post<BatchResponse>(
          '/media/batch',
          { action, media_ids: chunk, params },
          { signal: controller.signal }
        );
        success += resp.success_count ?? 0;
        lastMessage = resp.message || lastMessage;
        if (resp.task_id != null) taskIds.push(resp.task_id);
        if (resp.failed?.length) {
          failedCount += resp.failed.length;
          firstFailure ??= resp.failed[0];
        }
        // 只有真正成功的 id 才进"撤销"名单（失败的本来就还在）
        if (resp.success_count > 0 && resp.failed?.length) {
          const failedIds = new Set(resp.failed.map((f) => f.id));
          succeededIds.push(...chunk.filter((id) => !failedIds.has(id)));
        } else if (resp.success_count > 0) {
          succeededIds.push(...chunk);
        }
        progress = { done: Math.min(progress.done + chunk.length, ids.length), total: ids.length };
      }

      if (canceled) {
        // 取消不是错误：已处理的部分照常提交，剩余部分明确告知
        toasts.push(
          `已取消：完成 ${success} 项，剩余 ${ids.length - progress.done} 项未处理`,
          'warn'
        );
        librariesStore.notifyChanged();
        void list.reload();
        void loadCounts();
        return null;
      }

      // 失败明细里带上第一条原因：只报"失败 3 项"用户无从下手
      const failSuffix = failedCount
        ? `，失败 ${failedCount} 项${firstFailure ? `（#${firstFailure.id}：${firstFailure.error}）` : ''}`
        : '';

      if (taskIds.length > 0) {
        toasts.push(`已创建 ${taskIds.length} 个任务，共 ${success} 项待处理`);
        void tasks.refresh();
      } else if (action === 'delete' && success > 0) {
        // 软删除可撤销：10 秒内点「撤销」直接把记录从回收站恢复
        toasts.push(`已移入回收站 ${success} 项${failSuffix}`, failedCount ? 'err' : 'ok', {
          action: {
            label: '撤销',
            run: () => restoreFromRecycleBin(succeededIds)
          }
        });
      } else {
        toasts.push(
          `${lastMessage || '完成'}：成功 ${success} 项${failSuffix}`,
          failedCount ? 'err' : 'ok'
        );
      }
      clearSelection();
      librariesStore.notifyChanged();
      void list.reload();
      void loadCounts();
      return { action, total: ids.length, success_count: success, failed: [], task_id: taskIds[0] ?? null, export_url: null, message: lastMessage };
    } catch (e) {
      // abort 抛的是 AbortError：属于用户主动取消，不该报成失败
      if (e instanceof DOMException && e.name === 'AbortError') {
        toasts.push(`已取消：完成 ${progress?.done ?? 0} 项`, 'warn');
        librariesStore.notifyChanged();
        void list.reload();
        void loadCounts();
        return null;
      }
      toasts.push(errorMessage(e, '操作失败'), 'err');
      return null;
    } finally {
      batchAbort = null;
      busy = null;
      progress = null;
    }
  }

  /** 撤销软删除：逐条从回收站恢复（后端逐条接口，失败不阻断其它项）。 */
  async function restoreFromRecycleBin(ids: number[]): Promise<void> {
    const results = await Promise.allSettled(
      ids.map((id) => client.post(`/recycle-bin/${id}/restore`, {}))
    );
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    const bad = results.length - ok;
    toasts.push(
      `已撤销删除：恢复 ${ok} 项${bad ? `，${bad} 项恢复失败（可到回收站手动恢复）` : ''}`,
      bad ? 'err' : 'ok'
    );
    librariesStore.notifyChanged();
    void list.reload();
    void loadCounts();
  }

  async function applyRating(): Promise<void> {
    await runBatch('rating', { rating: ratingValue });
  }

  async function applyTag(): Promise<void> {
    if (!tagPick) return;
    await runBatch('tag', { tag_ids: [Number(tagPick)] });
    tagPick = '';
  }

  async function toggleIgnore(media: Media): Promise<void> {
    busy = 'ignore';
    try {
      await client.post('/media/batch', {
        action: 'metadata_ignore',
        media_ids: [Number(media.id)],
        params: { ignored: !media.metadata_ignored }
      });
      toasts.push(media.metadata_ignored ? '已恢复刮削' : '已忽略刮削');
      librariesStore.notifyChanged();
      void list.reload();
      void loadCounts();
    } catch (e) {
      toasts.push(errorMessage(e, '操作失败'), 'err');
    } finally {
      busy = null;
    }
  }

  async function confirmDelete(): Promise<void> {
    deleteOpen = false;
    await runBatch('delete', { permanent: false });
  }

  async function applyMove(): Promise<void> {
    if (!moveTarget) return;
    await runBatch('move', { target_library_id: Number(moveTarget) });
    moveTarget = '';
  }

  /**
   * 把选中项移动到本库内的某个子目录（磁盘真正移动 + 更新 file_path）。
   * 与「移动库」不同：这是 librariesApi.moveFiles（PUT /files/move），
   * 支持跨库、同名冲突自动加后缀，返回逐条错误。
   */
  async function applyMoveToDir(): Promise<void> {
    if (!query.libraryId || selected.size === 0) return;
    busy = 'move-dir';
    try {
      const res = await librariesApi.moveFiles(
        query.libraryId,
        [...selected].map(String),
        query.libraryId,
        targetDir.trim()
      );
      const errCount = res.errors?.length ?? 0;
      const firstError = res.errors?.[0]?.reason;
      toasts.push(
        `已移动 ${res.moved} 项${res.skipped ? `，跳过 ${res.skipped} 项` : ''}${
          errCount ? `，失败 ${errCount} 项${firstError ? `（${firstError}）` : ''}` : ''
        }`,
        errCount ? 'err' : 'ok'
      );
      clearSelection();
      librariesStore.notifyChanged();
      folderTree.bump();
      void list.reload();
      void loadCounts();
    } catch (e) {
      toasts.push(errorMessage(e, '移动失败'), 'err');
    } finally {
      busy = null;
    }
  }

  async function applyRename(): Promise<void> {
    if (!renameTemplate.trim()) return;
    await runBatch('rename', { template: renameTemplate.trim(), start_index: 1 });
  }

  function openMedia(media: Media): void {
    goto(`/detail/${media.id}`);
  }

  function openEdit(media: Media): void {
    editing = media;
    editOpen = true;
  }

  // ---- 滚动位置记忆（进详情页返回后回到原处）----
  let bodyEl = $state<HTMLElement | null>(null);
  let restoredScroll = false;

  function onBodyScroll(): void {
    if (!bodyEl) return;
    saveScroll(scrollKey('assets', query.view), bodyEl.scrollTop);
  }

  // 每次视图/页码变化后尝试恢复一次（只在回到同一视图时生效）
  $effect(() => {
    const key = scrollKey('assets', query.view);
    const page = query.page;
    untrack(() => {
      if (!bodyEl || !list.loaded) return;
      if (restoredScroll) return;
      restoredScroll = true;
      const top = loadScroll(key);
      if (top > 0) requestAnimationFrame(() => bodyEl?.scrollTo({ top }));
    });
    void page;
  });

  // ---- 响应式：state → URL + 重新取数 ----
  // 所有读 query 的字段都必须在这里被「摸到」，否则改筛选不会触发重载。
  $effect(() => {
    const snapshot: MediaQueryState = {
      ...query,
      tags: [...query.tags]
    };
    untrack(() => {
      syncUrl();
      void list.reload();
    });
    void snapshot;
  });

  // 侧边栏/其它视图改动媒体数据后（打标、移动库、删除…）自动刷新
  $effect(() => {
    librariesStore.revision;
    untrack(() => {
      void list.reload();
      void loadCounts();
    });
  });

  // 首次进入：确保库/标签已加载（受限于 store 的幂等 ensureLoaded）
  $effect(() => {
    untrack(() => {
      void librariesStore.ensureLoaded();
      void loadCounts();
    });
  });
</script>

<div class="workspace">
  <AssetsSummary
    {counts}
    loading={countsLoading}
    view={query.view}
    onSelect={selectView}
  />

  <AssetsFolderBar
    libraryId={query.libraryId}
    dir={query.dir}
    libraries={librariesStore.libraries}
    onnavigate={(next) => patch({ dir: next, page: 1 })}
    onchanged={() => {
      void list.reload();
      void loadCounts();
    }}
  />

  <AssetsToolbar
    query={query}
    libraries={librariesStore.libraries}
    tagTypes={librariesStore.tagTypes}
    tags={librariesStore.tags}
    total={list.total}
    loading={list.loading}
    onpatch={patch}
    onreset={resetFilters}
    onreload={() => {
      void list.reload();
      void loadCounts();
    }}
    onopenDuplicates={() => (duplicatesOpen = true)}
    onopenReconcile={query.view === 'missing' ? () => (reconcileOpen = true) : undefined}
    onopenNetworkImport={() => (networkImportOpen = true)}
  />

  {#if list.error}
    <div class="error">
      <span>{list.error}</span>
      <button type="button" onclick={() => void list.reload()}>重试</button>
    </div>
  {/if}

  <!-- 跨页全选：仅当筛选结果跨页时才出现，避免单页时制造噪音 -->
  {#if selectAllMode}
    <div class="selectbar on">
      <span>已选中全部 <b>{selected.size}</b> 项（含跨页）</span>
      <button type="button" onclick={clearSelection}>取消全选</button>
    </div>
  {:else if list.total > list.items.length && list.items.length > 0}
    <div class="selectbar">
      <button type="button" disabled={selectingAll} onclick={() => void selectAllMatching()}>
        {selectingAll ? '正在选取…' : `全选筛选结果（${list.total} 项）`}
      </button>
      <span class="hint">跨页选中当前筛选下的全部条目，可一次批量处理</span>
    </div>
  {/if}

  <div
    class="body"
    class:dim={list.loading && list.items.length > 0}
    bind:this={bodyEl}
    onscroll={onBodyScroll}
  >
    {#if query.display === 'grid'}
      <AssetsGrid
        items={list.items}
        {selected}
        loading={list.loading}
        onToggle={toggleOne}
        onOpen={openMedia}
        onEdit={openEdit}
        onIgnore={(m) => void toggleIgnore(m)}
      />
    {:else}
      <AssetsTable
        items={list.items}
        {selected}
        sort={query.sort}
        order={query.order}
        loading={list.loading}
        scroller={bodyEl}
        {libraryName}
        onToggle={toggleOne}
        onToggleAll={toggleAll}
        onSort={(field) =>
          patch({
            sort: field,
            order: query.sort === field && query.order === 'desc' ? 'asc' : 'desc',
            page: 1
          })}
        onOpen={openMedia}
        onEdit={openEdit}
        onIgnore={(m) => void toggleIgnore(m)}
      />
    {/if}
  </div>

  {#if pageCount > 1}
    <div class="pager">
      <button type="button" disabled={query.page <= 1} onclick={() => setPage(1)}>«</button>
      <button type="button" disabled={query.page <= 1} onclick={() => setPage(query.page - 1)}>
        上一页
      </button>
      {#each pageButtons as p (p)}
        {#if typeof p === 'number'}
          <button type="button" class:active={p === query.page} onclick={() => setPage(p)}>
            {p}
          </button>
        {:else}
          <span class="ellipsis">{p}</span>
        {/if}
      {/each}
      <button
        type="button"
        disabled={query.page >= pageCount}
        onclick={() => setPage(query.page + 1)}>下一页</button
      >
      <button
        type="button"
        disabled={query.page >= pageCount}
        onclick={() => setPage(pageCount)}>»</button
      >
      <span class="pager-info">
        <kbd class="kbd-hint">j/k</kbd> 移动 · <kbd class="kbd-hint">空格</kbd> 选中 ·
        <kbd class="kbd-hint">x</kbd> 全选 · <kbd class="kbd-hint">Enter</kbd> 打开
      </span>
      <span class="pager-info">第 {query.page} / {pageCount} 页 · 共 {list.total} 项</span>
    </div>
  {/if}

  {#if selected.size > 0}
    <div class="batchbar" role="toolbar" aria-label="批量操作">
      <span class="picked">
        已选 {selected.size} 项{selectAllMode ? '（跨页）' : ''}
      </span>
      {#if progress}
        <span class="progress-note">
          处理中 {progress.done}/{progress.total}
        </span>
        <button type="button" class="ghost cancel-btn" onclick={() => batchAbort?.abort()}>
          取消
        </button>
      {/if}

      <div class="group">
        <select bind:value={ratingValue} title="评分">
          {#each [1, 2, 3, 4, 5] as r (r)}
            <option value={r}>{r} 星</option>
          {/each}
        </select>
        <button type="button" disabled={busy === 'rating'} onclick={() => void applyRating()}>
          评分
        </button>
      </div>

      <div class="group">
        <select bind:value={tagPick} title="添加标签">
          <option value="">选择标签…</option>
          {#each librariesStore.tags as t (t.id)}
            <option value={t.id}>{t.name}</option>
          {/each}
        </select>
        <button type="button" disabled={busy === 'tag' || !tagPick} onclick={() => void applyTag()}>
          打标
        </button>
      </div>

      <button type="button" disabled={busy === 'scrape'} onclick={() => void runBatch('scrape')}>
        刮削
      </button>
      <button type="button" disabled={busy === 'thumbnail'} onclick={() => void runBatch('thumbnail')}>
        缩略图
      </button>
      <button
        type="button"
        disabled={busy === 'metadata_ignore'}
        onclick={() => void runBatch('metadata_ignore', { ignored: true })}
      >
        忽略刮削
      </button>
      <button
        type="button"
        disabled={busy === 'metadata_ignore'}
        onclick={() => void runBatch('metadata_ignore', { ignored: false })}
      >
        恢复刮削
      </button>
      <button
        type="button"
        disabled={busy === 'export'}
        onclick={async () => {
          const resp = await runBatch('export', { format: 'json' });
          if (resp?.export_url) window.open(resp.export_url, '_blank');
        }}
      >
        导出
      </button>

      <div class="group">
        <select bind:value={moveTarget} title="移动到资源库">
          <option value="">移到…</option>
          {#each librariesStore.libraries as lib (lib.id)}
            <option value={lib.id}>{lib.name}</option>
          {/each}
        </select>
        <button
          type="button"
          disabled={busy === 'move' || !moveTarget}
          onclick={() => void applyMove()}
        >
          移动
        </button>
      </div>

      <div class="group">
        <input
          class="tpl"
          bind:value={renameTemplate}
          placeholder={RENAME_PLACEHOLDER}
          title={RENAME_HINT}
        />
        <button
          type="button"
          disabled={busy === 'rename' || !renameTemplate.trim()}
          onclick={() => void applyRename()}
        >
          改名
        </button>
      </div>

      <div class="group">
        <input
          class="tpl"
          bind:value={targetDir}
          placeholder="目标子目录（留空=库根）"
          title="把选中项移动到本库的某个子目录；不存在会报错，请先新建"
          disabled={!query.libraryId}
        />
        <button
          type="button"
          disabled={busy === 'move-dir' || !query.libraryId}
          onclick={() => void applyMoveToDir()}
        >
          移到目录
        </button>
      </div>

      <button type="button" class="danger" onclick={() => (deleteOpen = true)}>删除</button>

      <span class="spacer"></span>
      <button type="button" class="ghost" onclick={clearSelection}>取消选择</button>
    </div>
  {/if}

  <ConfirmDialog
    bind:open={deleteOpen}
    title="移入回收站"
    description={`将选中的 ${selected.size} 项移入回收站（可恢复）。`}
    confirmText="移入回收站"
    danger
    onconfirm={() => void confirmDelete()}
  />

  <EditMediaDialog
    bind:open={editOpen}
    media={editing}
    onsuccess={() => {
      librariesStore.notifyChanged();
      void list.reload();
      void loadCounts();
    }}
  />

  <!-- 治理工具（三个对话框都自带取数与内部状态，只管 open） -->
  <DuplicatesDialog bind:open={duplicatesOpen} />
  <ReconcileDialog bind:open={reconcileOpen} />
  <NetworkImportDialog
    bind:open={networkImportOpen}
    onsuccess={() => {
      librariesStore.notifyChanged();
      void list.reload();
      void loadCounts();
    }}
  />

  <ToastHost />
</div>

<style>
  .workspace {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    min-width: 0;
    position: relative;
    overflow: hidden;
  }
  .body {
    flex: 1;
    min-height: 0;
    overflow: auto;
    transition: opacity var(--dur-fast);
  }
  .body.dim {
    opacity: 0.6;
  }
  .error {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 10px 16px 0;
    padding: 8px 12px;
    border-radius: var(--radius);
    border: 1px solid var(--danger);
    color: var(--danger);
    font-size: 13px;
  }
  .error button {
    font: inherit;
    font-size: 12px;
    padding: 3px 10px;
    border-radius: var(--radius-xs);
    border: 1px solid currentColor;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }
  .pager {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 10px 16px;
    border-top: 1px solid var(--rule);
    font-size: 12.5px;
    color: var(--ink-secondary);
    flex-wrap: wrap;
  }
  .pager button {
    font: inherit;
    font-size: 12.5px;
    min-width: 26px;
    padding: 3px 8px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: transparent;
    color: inherit;
    cursor: pointer;
  }
  .pager button:hover:not(:disabled) {
    border-color: var(--ink-faint);
    color: var(--ink);
  }
  .pager button.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
  }
  .pager button:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .pager .ellipsis {
    color: var(--ink-faint);
    padding: 0 3px;
  }
  .pager-info {
    margin-left: auto;
    color: var(--ink-tertiary);
    font-variant-numeric: tabular-nums;
  }
  /* 键盘提示：轻到不抢视线，但能被发现 */
  .pager-info + .pager-info {
    margin-left: 14px;
    color: var(--ink-faint);
  }
  .kbd-hint {
    font: inherit;
    font-size: 10.5px;
    padding: 1px 5px;
    border-radius: 4px;
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink-tertiary);
  }
  .selectbar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 16px;
    font-size: 12.5px;
    color: var(--ink-tertiary);
    border-bottom: 1px solid var(--rule-light);
  }
  .selectbar.on {
    color: var(--accent);
    background: var(--accent-soft);
  }
  .selectbar button {
    font: inherit;
    font-size: 12px;
    padding: 3px 10px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    cursor: pointer;
  }
  .selectbar.on button {
    border-color: var(--accent);
    color: var(--accent);
    background: transparent;
  }
  .selectbar button:hover:not(:disabled) {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .selectbar button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .selectbar .hint {
    color: var(--ink-faint);
    font-size: 12px;
  }
  .progress-note {
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }
  .cancel-btn {
    border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
    color: var(--danger);
  }
  .batchbar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 9px 16px;
    border-top: 1px solid var(--rule);
    background: var(--bg-elevated);
    box-shadow: 0 -6px 18px rgba(0, 0, 0, 0.18);
    font-size: 12.5px;
  }
  .batchbar .picked {
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }
  .batchbar .group {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .batchbar select {
    font: inherit;
    font-size: 12px;
    padding: 3px 6px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: var(--bg-surface);
    color: var(--ink-secondary);
    max-width: 130px;
  }
  .batchbar .tpl {
    font: inherit;
    font-size: 12px;
    padding: 3px 7px;
    width: 148px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: var(--bg-surface);
    color: var(--ink);
  }
  .batchbar .tpl:focus {
    outline: none;
    border-color: var(--accent);
  }
  .batchbar button {
    font: inherit;
    font-size: 12px;
    padding: 4px 10px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--ink-secondary);
    cursor: pointer;
  }
  .batchbar button:hover:not(:disabled) {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .batchbar button:disabled {
    opacity: 0.55;
    cursor: default;
  }
  .batchbar button.danger {
    color: var(--danger);
    border-color: color-mix(in srgb, var(--danger) 50%, transparent);
  }
  .batchbar button.ghost {
    border-color: transparent;
    color: var(--ink-tertiary);
  }
  .batchbar .spacer {
    flex: 1;
  }
</style>