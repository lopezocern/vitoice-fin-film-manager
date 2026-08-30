<script lang="ts">
  /** DirectoryTree — displays the actual file system structure of libraries.

   * Lazy-loads directory contents on expand. Supports right-click context
   * menu for files: rename, rename + re-scrape, and re-scrape.
   */
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { untrack } from 'svelte';
  import { librariesApi, type Library, type TreeNode } from '$lib/api/libraries';
  import { mediaApi } from '$lib/api/media';
  import { formatSize } from '$lib/utils/format';

  interface Props {
    libraries: Library[];
    collapsed: boolean;
  }

  let { libraries, collapsed }: Props = $props();

  // ---- 当前选中的库/目录（从 URL 读取，用于高亮选中项） ----
  const selectedLib = $derived($page.url.searchParams.get('lib') || '');
  const selectedDir = $derived.by(() => {
    const dir = $page.url.searchParams.get('dir');
    return dir || '';
  });
  const currentManageSection = $derived($page.url.searchParams.get('section') || 'assets');

  function gotoDirectory(libId: string, relPath = ''): void {
    const section = currentManageSection === 'files' ? 'files' : 'assets';
    const path = relPath
      ? `/manage?section=${section}&lib=${libId}&dir=${encodeURIComponent(relPath)}`
      : `/manage?section=${section}&lib=${libId}`;
    void goto(path);
  }

  // ---- Tree state ----
  // Path key format: `${libId}::${relPath}`  (relPath is "" for library root)
  let expandedPaths = $state<Set<string>>(new Set());
  let loadedChildren = $state<Map<string, TreeNode[]>>(new Map());
  let loadingPaths = $state<Set<string>>(new Set());
  let loadErrors = $state<Map<string, string>>(new Map());

  // ---- Context menu ----
  let contextMenu = $state<{ x: number; y: number; node: TreeNode; libId: string } | null>(null);

  // ---- Rename dialog (files) ----
  let renameState = $state<{ mediaId: string; oldName: string; libId: string } | null>(null);
  let renameInput = $state('');
  let renameReScrape = $state(false);
  let renaming = $state(false);

  // ---- Directory action dialog (create / rename / delete) ----
  type DirAction =
    | { type: 'create'; libId: string; parentPath: string; parentName: string }
    | { type: 'rename'; libId: string; relPath: string; oldName: string }
    | { type: 'delete'; libId: string; relPath: string; dirName: string; childCount: number | undefined };
  let dirAction = $state<DirAction | null>(null);
  let dirActionInput = $state('');
  let dirActionRecursive = $state(false);
  let dirActionLoading = $state(false);

  // ---- Toast ----
  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  function showToast(msg: string, type: 'ok' | 'err' = 'ok'): void {
    toast = { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 3000);
  }

  // ---- Path key helpers ----
  function pathKey(libId: string, relPath: string): string {
    return `${libId}::${relPath}`;
  }

  function isExpanded(libId: string, relPath: string): boolean {
    return expandedPaths.has(pathKey(libId, relPath));
  }

  function isLoading(libId: string, relPath: string): boolean {
    return loadingPaths.has(pathKey(libId, relPath));
  }

  // ---- Load directory children from API ----
  async function loadChildren(libId: string, relPath: string): Promise<void> {
    const key = pathKey(libId, relPath);
    if (loadedChildren.has(key) || loadingPaths.has(key)) return;

    loadingPaths = new Set(loadingPaths).add(key);
    try {
      const nodes = await librariesApi.tree(libId, relPath);
      loadedChildren = new Map(loadedChildren).set(key, nodes);
      loadErrors.delete(key);
    } catch {
      loadErrors = new Map(loadErrors).set(key, '加载失败');
    } finally {
      const next = new Set(loadingPaths);
      next.delete(key);
      loadingPaths = next;
    }
  }

  // ---- Toggle expand/collapse ----
  async function toggleExpand(libId: string, relPath: string): Promise<void> {
    const key = pathKey(libId, relPath);
    const next = new Set(expandedPaths);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
      if (!loadedChildren.has(key)) {
        await loadChildren(libId, relPath);
      }
    }
    expandedPaths = next;
  }

  // ---- Expand/collapse all libraries ----
  let expandAll = $state(false);
  async function toggleExpandAll(): Promise<void> {
    expandAll = !expandAll;
    if (expandAll) {
      // Expand all libraries
      const next = new Set(expandedPaths);
      for (const lib of libraries) {
        const key = pathKey(lib.id, '');
        next.add(key);
        if (!loadedChildren.has(key)) {
          await loadChildren(lib.id, '');
        }
      }
      expandedPaths = next;
    } else {
      expandedPaths = new Set();
    }
  }

  // ---- 选中项高亮（不再自动展开） ----
  // 展开/收起完全由左侧箭头控制：点击库或文件夹名称只做导航选中（右侧内容区
  // 跟随 URL 更新），不再强制展开目录树，避免"选中即展开、无法收起"的困扰。
  // selectedLib / selectedDir 已在文件头部定义。

  // 切换库时收起其他库的展开状态，避免旧库子树残留（文件混在新库视图下，
  // 点击旧库文件会错误跳回旧库）。
  let lastShownLib = '';
  $effect(() => {
    const lib = selectedLib;
    if (!lib || lib === lastShownLib) return;
    lastShownLib = lib;
    if (expandedPaths.size === 0) return;
    const next = new Set<string>();
    for (const key of expandedPaths) {
      if (key.startsWith(`${lib}::`)) next.add(key);
    }
    // 保留当前库的展开，清除其他库
    expandedPaths = next;
  });

  // ---- Flat tree rendering ----
  interface FlatNode {
    kind: 'library' | 'directory' | 'file';
    libId: string;
    node?: TreeNode;
    depth: number;
    expanded: boolean;
    loading: boolean;
    lib?: Library;
  }

  const flatTree = $derived.by(() => {
    const result: FlatNode[] = [];

    const walk = (libId: string, relPath: string, depth: number) => {
      const key = pathKey(libId, relPath);
      const children = loadedChildren.get(key);
      if (!children) return;

      for (const child of children) {
        const childExpanded = isExpanded(libId, child.rel_path);
        const childLoading = isLoading(libId, child.rel_path);

        if (child.node_type === 'directory') {
          result.push({
            kind: 'directory',
            libId,
            node: child,
            depth,
            expanded: childExpanded,
            loading: childLoading,
          });
          if (childExpanded) {
            walk(libId, child.rel_path, depth + 1);
          }
        } else {
          result.push({
            kind: 'file',
            libId,
            node: child,
            depth,
            expanded: false,
            loading: false,
          });
        }
      }
    };

    for (const lib of libraries) {
      const libExpanded = isExpanded(lib.id, '') || expandAll;
      result.push({
        kind: 'library',
        libId: lib.id,
        lib,
        depth: 0,
        expanded: libExpanded,
        loading: isLoading(lib.id, ''),
      });
      if (libExpanded) {
        walk(lib.id, '', 1);
      }
    }

    return result;
  });

  // ---- Context menu actions ----
  function onContextMenu(e: MouseEvent, node: TreeNode, libId: string): void {
    e.preventDefault();
    e.stopPropagation();
    contextMenu = { x: e.clientX, y: e.clientY, node, libId };
  }

  function closeContextMenu(): void {
    contextMenu = null;
  }

  function startRename(): void {
    if (!contextMenu || !contextMenu.node.media_id) return;
    renameState = {
      mediaId: String(contextMenu.node.media_id),
      oldName: contextMenu.node.name,
      libId: contextMenu.libId,
    };
    renameInput = contextMenu.node.name;
    renameReScrape = false;
    closeContextMenu();
  }

  async function startRescrape(): Promise<void> {
    if (!contextMenu || !contextMenu.node.media_id) return;
    const mediaId = String(contextMenu.node.media_id);
    const libId = contextMenu.libId;  // 在 closeContextMenu 前保存
    closeContextMenu();
    showToast('正在重新刮削…', 'ok');
    try {
      await mediaApi.scrape(mediaId);
      const parentKey = pathKey(libId, '');
      loadedChildren.delete(parentKey);
      await loadChildren(libId, '');
      showToast('刮削完成', 'ok');
    } catch {
      showToast('刮削失败', 'err');
    }
  }

  // AI 辅助二次刮削：AI 分析文件名后重试 TMDB 匹配
  async function startAiRescrape(): Promise<void> {
    if (!contextMenu || !contextMenu.node.media_id) return;
    const mediaId = String(contextMenu.node.media_id);
    const libId = contextMenu.libId;  // 在 closeContextMenu 前保存
    closeContextMenu();
    showToast('AI 辅助刮削中…', 'ok');
    try {
      const result = await mediaApi.aiRescrape(mediaId);
      if (result.success) {
        showToast(`AI 辅助刮削成功: ${result.matched_title ?? ''}`, 'ok');
      } else {
        showToast(
          result.suggested_title
            ? `AI 建议「${result.suggested_title}」但 TMDB 未匹配`
            : 'AI 未能生成有效建议',
          'err'
        );
      }
      // 刷新目录树以反映最新刮削状态
      const parentKey = pathKey(libId, '');
      loadedChildren.delete(parentKey);
      await loadChildren(libId, '');
    } catch (e) {
      const status = (e as { status?: number })?.status;
      let msg = 'AI 辅助刮削失败';
      if (status === 400) {
        const detail = (e as { body?: { detail?: string } })?.body?.detail;
        msg = detail || '请检查 AI / TMDB 配置';
      } else if (status === 502) {
        const detail = (e as { body?: { detail?: string } })?.body?.detail;
        msg = detail || 'AI 或 TMDB 调用失败，请检查配置或网络';
      }
      showToast(msg, 'err');
    }
  }

  async function confirmRename(): Promise<void> {
    if (!renameState) return;
    const newName = renameInput.trim();
    if (!newName || newName === renameState.oldName) {
      renameState = null;
      return;
    }

    renaming = true;
    try {
      await mediaApi.rename(renameState.mediaId, newName, renameReScrape);
      // Refresh the tree for this directory
      const key = pathKey(renameState.libId, '');
      loadedChildren.delete(key);
      await loadChildren(renameState.libId, '');
      showToast(
        renameReScrape ? '已重命名并重新刮削' : '已重命名',
        'ok'
      );
    } catch (e: any) {
      const msg = e?.message ?? '重命名失败';
      showToast(msg, 'err');
    } finally {
      renaming = false;
      renameState = null;
    }
  }

  function cancelRename(): void {
    renameState = null;
  }

  // ---- Directory operations (create / rename / delete) ----
  function startCreateFolder(): void {
    if (!contextMenu) return;
    const { libId, node } = contextMenu;
    const parentPath = node.node_type === 'directory' ? node.rel_path : '';
    const parentName = node.node_type === 'directory' ? node.name : '根目录';
    dirAction = { type: 'create', libId, parentPath, parentName };
    dirActionInput = '';
    closeContextMenu();
  }

  function startRenameDir(): void {
    if (!contextMenu || contextMenu.node.node_type !== 'directory') return;
    dirAction = {
      type: 'rename',
      libId: contextMenu.libId,
      relPath: contextMenu.node.rel_path,
      oldName: contextMenu.node.name,
    };
    dirActionInput = contextMenu.node.name;
    closeContextMenu();
  }

  function startDeleteDir(): void {
    if (!contextMenu || contextMenu.node.node_type !== 'directory') return;
    dirAction = {
      type: 'delete',
      libId: contextMenu.libId,
      relPath: contextMenu.node.rel_path,
      dirName: contextMenu.node.name,
      childCount: contextMenu.node.child_count,
    };
    dirActionRecursive = false;
    closeContextMenu();
  }

  async function confirmDirAction(): Promise<void> {
    if (!dirAction) return;
    dirActionLoading = true;
    try {
      if (dirAction.type === 'create') {
        const name = dirActionInput.trim();
        if (!name) return;
        await librariesApi.createDirectory(dirAction.libId, dirAction.parentPath, name);
        // Refresh parent directory
        const key = pathKey(dirAction.libId, dirAction.parentPath);
        loadedChildren.delete(key);
        await loadChildren(dirAction.libId, dirAction.parentPath);
        showToast('文件夹已创建', 'ok');
      } else if (dirAction.type === 'rename') {
        const newName = dirActionInput.trim();
        if (!newName || newName === dirAction.oldName) {
          dirAction = null;
          return;
        }
        await librariesApi.renameDirectory(dirAction.libId, dirAction.relPath, newName);
        // Refresh parent directory
        const parts = dirAction.relPath.split(/[/\\]/);
        parts.pop();
        const parentRel = parts.join('/');
        const key = pathKey(dirAction.libId, parentRel);
        loadedChildren.delete(key);
        await loadChildren(dirAction.libId, parentRel);
        showToast('文件夹已重命名', 'ok');
      } else if (dirAction.type === 'delete') {
        await librariesApi.deleteDirectory(
          dirAction.libId, dirAction.relPath, dirActionRecursive
        );
        // Refresh parent directory
        const parts = dirAction.relPath.split(/[/\\]/);
        parts.pop();
        const parentRel = parts.join('/');
        const key = pathKey(dirAction.libId, parentRel);
        loadedChildren.delete(key);
        await loadChildren(dirAction.libId, parentRel);
        showToast('文件夹已删除', 'ok');
      }
    } catch (e: any) {
      const detail = e?.body?.detail ?? e?.message ?? '操作失败';
      showToast(detail, 'err');
    } finally {
      dirActionLoading = false;
      dirAction = null;
    }
  }

  function cancelDirAction(): void {
    dirAction = null;
  }

  // ---- 选中节点（点击文件夹名称时触发，与展开/收起箭头分离） ----
  function selectNode(node: FlatNode): void {
    if (node.kind === 'library') {
      gotoDirectory(node.libId);
    } else if (node.kind === 'directory' && node.node) {
      gotoDirectory(node.libId, node.node.rel_path);
    } else if (node.kind === 'file' && node.node?.media_id) {
      // 文件节点点击 → 导航到所在目录并在右侧"媒体信息"选中展示，不直接打开详情页
      const rel = node.node.rel_path;
      const lastSep = Math.max(rel.lastIndexOf('/'), rel.lastIndexOf('\\'));
      const parentDir = lastSep >= 0 ? rel.slice(0, lastSep) : '';
      const section = currentManageSection === 'files' ? 'files' : 'assets';
      const sel = node.node.media_id;
      const params = new URLSearchParams({ section, lib: node.libId });
      if (parentDir) params.set('dir', parentDir);
      params.set('sel', String(sel));
      void goto(`/manage?${params.toString()}`);
    }
  }

  // ---- Click outside to close context menu ----
  function onWindowClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    if (contextMenu && !target.closest('.fs-ctx-menu')) {
      contextMenu = null;
    }
  }

  $effect(() => {
    if (contextMenu) {
      window.addEventListener('click', onWindowClick);
      return () => window.removeEventListener('click', onWindowClick);
    }
  });

  // ---- Auto-expand first library on load ----
  // 用 untrack 包裹：toggleExpand → loadChildren 在 await 前会同步读写
  // loadingPaths / expandedPaths / loadedChildren，若被追踪为依赖会在每次
  // 加载完成时重新触发本 effect，形成响应式循环。
  let prevLibIds = '';
  $effect(() => {
    const ids = libraries.map((l) => l.id).join(',');
    if (ids !== prevLibIds && ids && !collapsed) {
      prevLibIds = ids;
      // 初次进入时默认全部折叠，不自动展开任何库
      // 仅当 URL 中有 lib 参数时由"自动展开到选中目录"逻辑处理展开
    }
  });
</script>

<!-- ============ Collapsed mode: library icons only ============ -->
{#if collapsed}
  {#each libraries as lib (lib.id)}
    <button
      class="item"
      data-tip={lib.name}
      onclick={() => gotoDirectory(lib.id)}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
      </svg>
    </button>
  {/each}
{:else}
  <!-- ============ Expanded mode: full file system tree ============ -->
  <div class="fs-tree">
    {#each flatTree as item (item.kind + ':' + item.libId + ':' + (item.node?.rel_path ?? '') + ':' + item.depth)}
      {#if item.kind === 'library'}
        <div class="fs-lib-row">
          <button
            class="fs-arrow-btn"
            onclick={() => toggleExpand(item.libId, '')}
            aria-label={item.expanded ? '收起' : '展开'}
          >
            <span class="fs-arrow">{item.expanded ? '▾' : '▸'}</span>
          </button>
          <button
            class="fs-lib"
            class:active={selectedLib === item.libId && !selectedDir}
            data-drop-dir=""
            data-drop-lib={item.libId}
            data-drop-name={item.lib?.name}
            onclick={() => selectNode(item)}
            oncontextmenu={(e) => {
              // Create a synthetic directory node for the library root
              const root_node: TreeNode = {
                name: item.lib?.name ?? '',
                rel_path: '',
                node_type: 'directory',
                child_count: item.lib?.media_count,
                is_scraped: false,
                has_poster: false,
              };
              onContextMenu(e, root_node, item.libId);
            }}
          >
            <svg class="fs-icon" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
            </svg>
            <span class="fs-label" title={item.lib?.name}>{item.lib?.name}</span>
            {#if item.lib?.media_count != null}
              <span class="fs-count">{item.lib.media_count}</span>
            {/if}
          </button>
        </div>
      {:else if item.kind === 'directory'}
        <div class="fs-dir-row" style={`padding-left: ${4 + item.depth * 14}px`}>
          <button
            class="fs-arrow-btn"
            onclick={() => item.node && toggleExpand(item.libId, item.node.rel_path)}
            aria-label={item.expanded ? '收起' : '展开'}
          >
            <span class="fs-arrow">{item.expanded ? '▾' : '▸'}</span>
          </button>
          <button
            class="fs-dir"
            class:active={selectedLib === item.libId && selectedDir === (item.node?.rel_path ?? '')}
            data-drop-dir={item.node?.rel_path ?? ''}
            data-drop-lib={item.libId}
            data-drop-name={item.node?.name}
            onclick={() => selectNode(item)}
            oncontextmenu={(e) => item.node && onContextMenu(e, item.node, item.libId)}
          >
            <svg class="fs-icon" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
            </svg>
            <span class="fs-label" title={item.node?.name}>{item.node?.name}</span>
            {#if item.node?.child_count != null}
              <span class="fs-count">{item.node.child_count}</span>
            {/if}
          </button>
        </div>
      {:else}
        <div
          class="fs-file"
          class:scraped={item.node?.is_scraped}
          class:unscraped={item.node?.media_id && !item.node?.is_scraped}
          class:not-imported={!item.node?.media_id}
          style={`padding-left: ${8 + item.depth * 14}px`}
          oncontextmenu={(e) => item.node && onContextMenu(e, item.node, item.libId)}
          onclick={() => selectNode(item)}
          role="button"
          tabindex="0"
          title={item.node?.name}
        >
          <span class="fs-file-icon">
            {#if item.node?.is_scraped}
              <svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M3 2h7l3 3v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"></path>
                <path d="M6 8l1.5 1.5L10 7" stroke-linecap="round" stroke-linejoin="round"></path>
              </svg>
            {:else if item.node?.media_id}
              <svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M3 2h7l3 3v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"></path>
              </svg>
            {:else}
              <svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5" stroke-opacity="0.4">
                <path d="M3 2h7l3 3v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"></path>
              </svg>
            {/if}
          </span>
          <span class="fs-label">{item.node?.name}</span>
          {#if item.node?.size}
            <span class="fs-size">{formatSize(item.node.size)}</span>
          {/if}
          {#if item.node?.media_id && !item.node?.is_scraped}
            <span class="fs-badge" title="未刮削">!</span>
          {/if}
        </div>
      {/if}
    {/each}

    {#if flatTree.length === 0}
      <div class="fs-empty">暂无媒体库</div>
    {/if}
  </div>
{/if}

<!-- ============ Context Menu ============ -->
{#if contextMenu}
  <div
    class="fs-ctx-menu"
    style={`left:${Math.min(contextMenu.x, window.innerWidth - 200)}px; top:${Math.min(contextMenu.y, window.innerHeight - 280)}px`}
  >
    {#if contextMenu.node.node_type === 'directory'}
      <!-- Directory context menu -->
      <button class="fs-ctx-item" onclick={startCreateFolder}>
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
          <path d="M8 8v3M6.5 9.5h3" stroke-linecap="round"></path>
        </svg>
        新建文件夹
      </button>
      <button class="fs-ctx-item" onclick={startRenameDir}>
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M11 2l3 3-8 8H3v-3l8-8z" stroke-linejoin="round"></path>
        </svg>
        重命名文件夹
      </button>
      <div class="fs-ctx-divider"></div>
      <button class="fs-ctx-item danger" onclick={startDeleteDir}>
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M3 4h10M6 4V2.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 .5.5V4M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4" stroke-linecap="round" stroke-linejoin="round"></path>
        </svg>
        删除文件夹
      </button>
    {:else if contextMenu.node.media_id}
      <!-- File context menu (imported media) -->
      <button class="fs-ctx-item" onclick={startRename}>
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M11 2l3 3-8 8H3v-3l8-8z" stroke-linejoin="round"></path>
        </svg>
        重命名
      </button>
      <button class="fs-ctx-item" onclick={() => { renameReScrape = true; startRename(); }}>
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M11 2l3 3-8 8H3v-3l8-8z" stroke-linejoin="round"></path>
          <path d="M2 14l3-1" stroke-linecap="round"></path>
        </svg>
        重命名并刮削
      </button>
      <button class="fs-ctx-item" onclick={startRescrape}>
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 8a6 6 0 1 1-2-4.5" stroke-linecap="round"></path>
          <path d="M12 1v3.5h-3.5" stroke-linecap="round" stroke-linejoin="round"></path>
        </svg>
        重新刮削
      </button>
      <div class="fs-ctx-divider"></div>
      <button class="fs-ctx-item ai-item" onclick={startAiRescrape}>
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M8 1L1 4l7 3 7-3-7-3zM1 11l7 3 7-3M1 7.5l7 3 7-3"></path>
        </svg>
        AI 辅助刮削
      </button>
    {/if}
  </div>
{/if}

<!-- ============ Rename Dialog ============ -->
{#if renameState}
  <div
    class="fs-rename-overlay"
    role="dialog"
    aria-modal="true"
    onclick={cancelRename}
    onkeydown={(e) => e.key === 'Escape' && cancelRename()}
  >
    <div class="fs-rename-dialog" onclick={(e) => e.stopPropagation()}>
      <h3 class="fs-rename-title">重命名文件</h3>
      <p class="fs-rename-hint">修改文件名后可重新刮削以获取正确的元数据</p>
      <input
        class="fs-rename-input"
        bind:value={renameInput}
        onkeydown={(e) => {
          if (e.key === 'Enter') confirmRename();
          if (e.key === 'Escape') cancelRename();
        }}
        placeholder="输入新文件名"
        autocomplete="off"
      />
      <label class="fs-rename-check">
        <input type="checkbox" bind:checked={renameReScrape} />
        <span>同时重新刮削（清除旧元数据并重新匹配）</span>
      </label>
      <div class="fs-rename-actions">
        <button class="fs-btn-cancel" onclick={cancelRename} disabled={renaming}>取消</button>
        <button class="fs-btn-ok" onclick={confirmRename} disabled={renaming || !renameInput.trim()}>
          {renaming ? '处理中…' : '确认'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- ============ Directory Action Dialog ============ -->
{#if dirAction}
  <div
    class="fs-rename-overlay"
    role="dialog"
    aria-modal="true"
    onclick={cancelDirAction}
    onkeydown={(e) => e.key === 'Escape' && cancelDirAction()}
  >
    <div class="fs-rename-dialog" onclick={(e) => e.stopPropagation()}>
      {#if dirAction.type === 'create'}
        <h3 class="fs-rename-title">新建文件夹</h3>
        <p class="fs-rename-hint">在「{dirAction.parentName}」下创建新文件夹</p>
        <input
          class="fs-rename-input"
          bind:value={dirActionInput}
          onkeydown={(e) => {
            if (e.key === 'Enter') confirmDirAction();
            if (e.key === 'Escape') cancelDirAction();
          }}
          placeholder="输入文件夹名称"
          autocomplete="off"
        />
        <div class="fs-rename-actions">
          <button class="fs-btn-cancel" onclick={cancelDirAction} disabled={dirActionLoading}>取消</button>
          <button class="fs-btn-ok" onclick={confirmDirAction} disabled={dirActionLoading || !dirActionInput.trim()}>
            {dirActionLoading ? '创建中…' : '创建'}
          </button>
        </div>
      {:else if dirAction.type === 'rename'}
        <h3 class="fs-rename-title">重命名文件夹</h3>
        <p class="fs-rename-hint">重命名后，文件夹内所有媒体的路径将自动更新</p>
        <input
          class="fs-rename-input"
          bind:value={dirActionInput}
          onkeydown={(e) => {
            if (e.key === 'Enter') confirmDirAction();
            if (e.key === 'Escape') cancelDirAction();
          }}
          placeholder="输入新文件夹名称"
          autocomplete="off"
        />
        <div class="fs-rename-actions">
          <button class="fs-btn-cancel" onclick={cancelDirAction} disabled={dirActionLoading}>取消</button>
          <button class="fs-btn-ok" onclick={confirmDirAction} disabled={dirActionLoading || !dirActionInput.trim() || dirActionInput.trim() === dirAction.oldName}>
            {dirActionLoading ? '处理中…' : '确认'}
          </button>
        </div>
      {:else if dirAction.type === 'delete'}
        <h3 class="fs-rename-title">删除文件夹</h3>
        <p class="fs-rename-hint">
          确定要删除文件夹「{dirAction.dirName}」吗？
          {#if dirAction.childCount != null && dirAction.childCount > 0}
            <br />该文件夹包含 {dirAction.childCount} 个子项。
          {/if}
        </p>
        {#if dirAction.childCount != null && dirAction.childCount > 0}
          <label class="fs-rename-check">
            <input type="checkbox" bind:checked={dirActionRecursive} />
            <span>递归删除（删除文件夹内所有内容，受影响的媒体将标记为文件丢失）</span>
          </label>
        {/if}
        <div class="fs-rename-actions">
          <button class="fs-btn-cancel" onclick={cancelDirAction} disabled={dirActionLoading}>取消</button>
          <button class="fs-btn-ok fs-btn-danger" onclick={confirmDirAction} disabled={dirActionLoading || (dirAction.childCount != null && dirAction.childCount > 0 && !dirActionRecursive)}>
            {dirActionLoading ? '删除中…' : '删除'}
          </button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<!-- ============ Toast ============ -->
{#if toast}
  <div class="fs-toast" class:err={toast.type === 'err'}>{toast.msg}</div>
{/if}

<style>
  /* ---- Tree container ---- */
  .fs-tree {
    padding: 2px 0;
  }

  /* ---- Library / directory row containers（箭头与名称分离） ---- */
  .fs-lib-row {
    display: flex;
    align-items: center;
    padding-left: 4px;
  }
  .fs-dir-row {
    display: flex;
    align-items: center;
  }

  /* ---- 展开/收起箭头按钮（独立于名称点击） ---- */
  .fs-arrow-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    min-height: 24px;
    border: none;
    background: none;
    color: var(--ink-tertiary);
    font-size: 13px;
    cursor: pointer;
    flex-shrink: 0;
    padding: 0;
    border-radius: var(--radius-xs);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
  }
  .fs-arrow-btn:hover {
    background: var(--bg-active);
    color: var(--ink);
  }

  /* ---- Library root node（名称按钮） ---- */
  .fs-lib {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1;
    min-width: 0;
    padding: 6px 12px 6px 2px;
    border: none;
    background: none;
    color: var(--ink-secondary);
    font-size: 12px;
    font-weight: 600;
    text-align: left;
    cursor: pointer;
    border-radius: var(--radius);
    transition: background var(--dur) var(--ease-out);
  }
  .fs-lib:hover {
    background: var(--bg-hover);
  }
  .fs-lib.active {
    background: var(--accent-soft);
    color: var(--accent);
  }

  /* ---- Directory node（名称按钮） ---- */
  .fs-dir {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1;
    min-width: 0;
    padding: 4px 12px 4px 2px;
    border: none;
    background: none;
    color: var(--ink-secondary);
    font-size: 12px;
    text-align: left;
    cursor: pointer;
    border-radius: var(--radius);
    transition: background var(--dur) var(--ease-out);
  }
  .fs-dir:hover {
    background: var(--bg-hover);
  }
  .fs-dir.active {
    background: var(--accent-soft);
    color: var(--accent);
  }

  /* ---- File node ---- */
  .fs-file {
    display: flex;
    align-items: center;
    gap: 4px;
    width: 100%;
    padding: 3px 12px 3px 8px;
    border: none;
    color: var(--ink-secondary);
    font-size: 12px;
    cursor: pointer;
    border-radius: var(--radius);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
    user-select: none;
  }
  .fs-file:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }
  .fs-file.scraped {
    color: var(--ink);
  }
  .fs-file.unscraped {
    color: var(--ink-secondary);
  }
  .fs-file.not-imported {
    color: var(--ink-faint);
    opacity: 0.6;
  }

  /* ---- Common tree elements ---- */
  .fs-arrow {
    width: 16px;
    text-align: center;
    color: var(--ink-tertiary);
    font-size: 13px;
    flex-shrink: 0;
  }
  .fs-icon {
    flex-shrink: 0;
    color: var(--ink-tertiary);
  }
  .fs-file-icon {
    width: 14px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .fs-label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .fs-count {
    color: var(--ink-tertiary);
    font-size: 11px;
    font-weight: 400;
    flex-shrink: 0;
  }
  .fs-size {
    color: var(--ink-faint);
    font-size: 10px;
    flex-shrink: 0;
  }
  .fs-badge {
    color: #f59e0b;
    font-size: 11px;
    font-weight: 700;
    flex-shrink: 0;
  }
  .fs-empty {
    padding: 12px 8px;
    color: var(--ink-faint);
    font-size: 12px;
    text-align: center;
  }

  /* ---- Context menu ---- */
  .fs-ctx-menu {
    position: fixed;
    z-index: 10000;
    min-width: 160px;
    padding: 4px;
    background: var(--bg2, var(--bg-card, #1e1e2e));
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  }
  .fs-ctx-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border: none;
    background: none;
    color: var(--ink-secondary);
    font-size: 12px;
    text-align: left;
    cursor: pointer;
    border-radius: 4px;
    transition: background 0.15s, color 0.15s;
  }
  .fs-ctx-item:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }

  .fs-ctx-divider {
    height: 1px;
    margin: 4px 6px;
    background: var(--border, rgba(255, 255, 255, 0.08));
  }

  .fs-ctx-item.ai-item {
    color: var(--accent, #635bff);
  }

  .fs-ctx-item.ai-item:hover {
    background: var(--accent-soft, rgba(99, 91, 255, 0.12));
    color: var(--accent, #635bff);
  }

  .fs-ctx-item.danger {
    color: #ef4444;
  }

  .fs-ctx-item.danger:hover {
    background: rgba(239, 68, 68, 0.12);
    color: #ef4444;
  }

  /* ---- Rename dialog ---- */
  .fs-rename-overlay {
    position: fixed;
    inset: 0;
    z-index: 10001;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0,0,0,0.5);
    backdrop-filter: blur(4px);
  }
  .fs-rename-dialog {
    width: 420px;
    max-width: 90vw;
    padding: 24px;
    background: var(--bg2, var(--bg-card, #1e1e2e));
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    border-radius: 12px;
    box-shadow: 0 16px 48px rgba(0,0,0,0.4);
  }
  .fs-rename-title {
    margin: 0 0 4px;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
  }
  .fs-rename-hint {
    margin: 0 0 16px;
    font-size: 12px;
    color: var(--ink-faint);
  }
  .fs-rename-input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border, rgba(255,255,255,0.15));
    border-radius: 8px;
    background: var(--bg, rgba(0,0,0,0.2));
    color: var(--ink);
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s;
  }
  .fs-rename-input:focus {
    border-color: var(--accent, #635bff);
  }
  .fs-rename-check {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
    font-size: 12px;
    color: var(--ink-secondary);
    cursor: pointer;
  }
  .fs-rename-check input {
    cursor: pointer;
  }
  .fs-rename-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 20px;
  }
  .fs-btn-cancel,
  .fs-btn-ok {
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.2s, opacity 0.2s;
  }
  .fs-btn-cancel {
    background: var(--bg-hover);
    color: var(--ink-secondary);
  }
  .fs-btn-cancel:hover {
    background: var(--bg-hover);
  }
  .fs-btn-ok {
    background: var(--accent, #635bff);
    color: #fff;
  }
  .fs-btn-ok:hover {
    opacity: 0.9;
  }
  .fs-btn-danger {
    background: #ef4444 !important;
  }
  .fs-btn-danger:hover {
    background: #dc2626 !important;
    opacity: 0.9;
  }
  .fs-btn-cancel:disabled,
  .fs-btn-ok:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* ---- Toast ---- */
  .fs-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 10002;
    padding: 10px 20px;
    background: var(--bg2, var(--bg-card, #1e1e2e));
    color: var(--ink);
    font-size: 13px;
    border-radius: 8px;
    border: 1px solid var(--border, rgba(255,255,255,0.1));
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    animation: fs-toast-in 0.3s var(--ease-out);
  }
  .fs-toast.err {
    border-color: #ef4444;
    color: #ef4444;
  }
  @keyframes fs-toast-in {
    from { opacity: 0; transform: translateX(-50%) translateY(8px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
</style>
