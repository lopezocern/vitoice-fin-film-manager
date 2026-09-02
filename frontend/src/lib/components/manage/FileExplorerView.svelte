<script lang="ts">
  import { onMount } from 'svelte';
  import { librariesApi, type Library } from '$lib/api/libraries';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import DirectoryTree from '$lib/components/layout/DirectoryTree.svelte';
  import MediaManageView from '$lib/components/manage/MediaManageView.svelte';
  import { createAsyncCleanup } from '$lib/utils/asyncCleanup';
  import { realQueryParam } from '$lib/utils/urlState';
  import { liveQueryParam } from '$lib/stores/urlState.svelte';

  let libraries = $state<Library[]>([]);
  let selectedLibraryId = $state('');
  let action = $state<'new-folder' | null>(null);
  let actionName = $state('');
  let busy = $state(false);
  let toast = $state<{ message: string; type: 'ok' | 'error' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  const currentLibrary = $derived(libraries.find((lib) => lib.id === selectedLibraryId) ?? null);
  const canImport = $derived(!!currentLibrary);
  /** 目录树当前选中目录（URL dir 参数）：新建文件夹/导入文件以它为目标目录 */
  // 用 liveQueryParam 而非 $page.url：popstate 重挂载时 page store 丢 query，dir 变空
  const currentDir = $derived(liveQueryParam('dir') ?? '');

  function showToast(message: string, type: 'ok' | 'error' = 'ok'): void {
    toast = { message, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 3200);
  }

  async function loadLibraries(): Promise<void> {
    try {
      const loaded = await librariesApi.list(true);
      libraries = loaded;
      // 一次性读取：以真实 location 为准（$page.url 在 popstate 后可能丢 query）
      const urlLib = realQueryParam('lib') ?? '';
      selectedLibraryId = urlLib && loaded.some((lib) => lib.id === urlLib) ? urlLib : (loaded[0]?.id ?? '');
    } catch {
      showToast('资源库列表加载失败，请检查后端服务', 'error');
    }
  }

  // 目录树通过 URL（lib/dir）导航；同步当前库以驱动头部按钮状态
  $effect(() => {
    // effect 内一次性读取真实 URL 即可，无需响应式
    const urlLib = realQueryParam('lib') ?? '';
    if (urlLib && libraries.some((lib) => lib.id === urlLib)) selectedLibraryId = urlLib;
  });

  onMount(() => {
    void loadLibraries();
    // 拖拽监听只挂在管理页组件生命周期内：离开页面自动注销，其他页面不受影响
    if (!isTauri) return;
    // createAsyncCleanup 防止竞态：onDragDropEvent 是 async 的，若在 await 期间
    // 卸载，旧写法的 cleanup 拿到 null，之后注册的监听永久挂在 webview 上，
    // 每次进出管理页就多叠一份回调。
    const ac = createAsyncCleanup();
    (async () => {
      const { getCurrentWebview } = await import('@tauri-apps/api/webview');
      ac.set(
        await getCurrentWebview().onDragDropEvent((event) => {
        const p = event.payload;
        if (p.type === 'enter' || p.type === 'over') {
          dragging = true;
          if (pendingDrop) return;
          const hit = hitTestDrop(p.position);
          if (hit) {
            const scale = window.devicePixelRatio || 1;
            const el = document
              .elementFromPoint(p.position.x / scale, p.position.y / scale)
              ?.closest('[data-drop-dir]');
            if (el) setHover(hit, el);
          } else {
            clearHover();
          }
        } else if (p.type === 'drop') {
          dragging = false;
          clearHover();
          if (pendingDrop || busy) return;
          const paths = Array.isArray(p.paths)
            ? p.paths.filter((x): x is string => typeof x === 'string')
            : [];
          if (!paths.length) return;
          const target = resolveDropTarget(p.position);
          if (!target) {
            showToast('请先选择一个资源库', 'error');
            return;
          }
          pendingDrop = { paths, target };
        } else {
          // leave
          dragging = false;
          clearHover();
        }
        })
      );
    })();
    return () => {
      ac.dispose();
      clearHover();
    };
  });

  async function refreshLibrary(): Promise<void> {
    if (!selectedLibraryId) return;
    busy = true;
    try {
      await librariesApi.scan(selectedLibraryId);
      showToast('已加入扫描队列');
      await loadLibraries();
    } catch {
      showToast('扫描启动失败', 'error');
    } finally {
      busy = false;
    }
  }

  function openNewFolder(): void {
    action = 'new-folder';
    actionName = '';
  }

  function closeAction(): void {
    if (busy) return;
    action = null;
    actionName = '';
  }

  async function confirmNewFolder(): Promise<void> {
    if (!action || !currentLibrary) return;
    busy = true;
    try {
      await librariesApi.createDirectory(selectedLibraryId, currentDir, actionName.trim());
      showToast('文件夹已创建');
      librariesStore.notifyChanged();
      closeAction();
    } catch (e) {
      showToast(e instanceof Error ? e.message : '操作失败', 'error');
    } finally {
      busy = false;
    }
  }

  /** 与后端 scanner.VIDEO_EXTENSIONS 对齐的选择器扩展名过滤 */
  const VIDEO_EXT_FILTER = [
    'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v',
    'mpg', 'mpeg', 'ts', 'm2ts', 'vob', 'ogv', '3gp',
  ];

  // ---- 拖拽导入（方案 C：drop 后弹确认条，用户选 复制/移动）----
  type DropTarget = { libId: string; dir: string; name: string };
  let dragging = $state(false);
  let pendingDrop = $state<{ paths: string[]; target: DropTarget } | null>(null);
  let hoverEl: Element | null = null;

  const isTauri =
    typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

  /** 物理坐标 → CSS 逻辑坐标，再命中目录树节点（库/目录按钮带 data-drop-*） */
  function hitTestDrop(position: { x: number; y: number }): DropTarget | null {
    const scale = window.devicePixelRatio || 1;
    const el = document.elementFromPoint(position.x / scale, position.y / scale);
    const node = el?.closest('[data-drop-dir]') as HTMLElement | null;
    if (node && node.dataset.dropLib) {
      return {
        libId: node.dataset.dropLib,
        dir: node.dataset.dropDir ?? '',
        name: node.dataset.dropName ?? '根目录',
      };
    }
    return null;
  }

  function clearHover(): void {
    hoverEl?.removeAttribute('data-drop-hover');
    hoverEl = null;
  }

  function setHover(target: DropTarget, el: Element): void {
    if (hoverEl === el) return;
    clearHover();
    hoverEl = el;
    el.setAttribute('data-drop-hover', 'true');
  }

  function resolveDropTarget(position: { x: number; y: number }): DropTarget | null {
    const hit = hitTestDrop(position);
    if (hit) return hit;
    // 没有命中树节点 → 落到当前选中的库 + 目录
    if (selectedLibraryId && currentLibrary) {
      return { libId: selectedLibraryId, dir: currentDir, name: currentDir || currentLibrary.name };
    }
    return null;
  }

  function summarizeImport(
    res: { imported: number; skipped: number; results: Array<{ status: string; reason?: string; renamed?: boolean }> },
    verb: string,
  ): { message: string; type: 'ok' | 'error' } {
    const renamed = res.results.filter((r) => r.status === 'imported' && r.renamed).length;
    const reasons = res.results.filter((r) => r.status === 'skipped' && r.reason).map((r) => r.reason);
    let msg = `${verb} ${res.imported} 个文件`;
    if (renamed > 0) msg += `（${renamed} 个同名文件已自动加序号）`;
    if (res.skipped > 0) msg += `，跳过 ${res.skipped} 个`;
    if (reasons.length > 0 && reasons.length <= 3) msg += `：${reasons.join('；')}`;
    return { message: msg, type: res.imported > 0 ? 'ok' : 'error' };
  }

  async function importFiles(): Promise<void> {
    if (!canImport || !currentLibrary) return;
    if (!isTauri) {
      showToast('文件导入需要在 vitoice 客户端中使用', 'error');
      return;
    }
    busy = true;
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const picked = await open({
        multiple: true,
        directory: false,
        title: '选择要导入的媒体文件（可多选）',
        filters: [{ name: '视频文件', extensions: VIDEO_EXT_FILTER }],
      });
      const paths = typeof picked === 'string' ? [picked] : Array.isArray(picked) ? picked : [];
      if (!paths.length) return;
      const res = await librariesApi.importFiles(selectedLibraryId, currentDir, paths);
      const s = summarizeImport(res, '已导入');
      showToast(s.message, s.type);
      await loadLibraries();
    } catch (e) {
      showToast(e instanceof Error ? e.message : '导入失败', 'error');
    } finally {
      busy = false;
    }
  }

  async function confirmDrop(mode: 'copy' | 'move'): Promise<void> {
    const drop = pendingDrop;
    if (!drop || busy) return;
    busy = true;
    try {
      const res = await librariesApi.importFiles(drop.target.libId, drop.target.dir, drop.paths, mode);
      const s = summarizeImport(res, mode === 'move' ? '已移动' : '已导入');
      showToast(s.message, s.type);
      librariesStore.notifyChanged();
      await loadLibraries();
    } catch (e) {
      showToast(e instanceof Error ? e.message : '导入失败', 'error');
    } finally {
      busy = false;
      pendingDrop = null;
    }
  }

  function cancelDrop(): void {
    if (busy) return;
    pendingDrop = null;
  }
</script>

<div class="explorer" class:dragging>
  <header class="explorer-header">
    <div>
      <div class="eyebrow">资源管理器</div>
      <h1>媒体管理</h1>
      <p>直接管理系统文件夹、媒体文件和没有实体文件的网络记录（支持拖入视频文件导入）</p>
    </div>
    <div class="header-actions">
      <button class="button" disabled={!canImport || busy} onclick={openNewFolder}>新建文件夹</button>
      <button class="button primary" disabled={!canImport || busy} onclick={importFiles}>
        <span class="button-icon">＋</span> 导入文件（可多选）
      </button>
      <button class="button" disabled={!selectedLibraryId || busy} onclick={refreshLibrary}>扫描资源库</button>
    </div>
  </header>

  <div class="manage-layout">
    <aside class="explorer-tree">
      <div class="tree-heading"><span>资源库与目录</span><button class="tree-new-folder" title="新建文件夹" aria-label="新建文件夹" onclick={openNewFolder} disabled={!canImport || busy}>＋</button></div>
      <DirectoryTree {libraries} collapsed={false} />
    </aside>
    <section class="manage-pane">
      <MediaManageView libraries={librariesStore.libraries} tags={librariesStore.tags} tagTypes={librariesStore.tagTypes} />
    </section>
  </div>
</div>

{#if pendingDrop}
  <div class="drop-bar" role="dialog" aria-label="拖入文件确认">
    <span class="drop-info">
      拖入 <b>{pendingDrop.paths.length}</b> 个文件，目标：<b>{pendingDrop.target.name || '根目录'}</b>
    </span>
    <button class="button" disabled={busy} onclick={cancelDrop}>取消</button>
    <button class="button primary" disabled={busy} onclick={() => confirmDrop('copy')}>导入（复制）</button>
    <button class="button" disabled={busy} onclick={() => confirmDrop('move')}>移动</button>
  </div>
{/if}

{#if action === 'new-folder'}
  <div class="modal-backdrop" role="presentation" onclick={(event) => event.target === event.currentTarget && closeAction()}>
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="action-title" tabindex="-1">
      <div class="modal-head"><h2 id="action-title">新建文件夹</h2><button class="icon-button" aria-label="关闭" onclick={closeAction}>×</button></div>
      <label class="field"><span>文件夹名称{currentDir ? `（创建于 ${currentDir}）` : '（创建于资源库根目录）'}</span><input bind:value={actionName} placeholder="请输入名称" onkeydown={(event) => event.key === 'Enter' && confirmNewFolder()} /></label>
      <div class="modal-actions"><button class="button" onclick={closeAction}>取消</button><button class="button primary" disabled={busy || !actionName.trim()} onclick={confirmNewFolder}>{busy ? '处理中…' : '确认'}</button></div>
    </div>
  </div>
{/if}

{#if toast}<div class:error={toast.type === 'error'} class="toast">{toast.message}</div>{/if}

<style>
  .explorer { display:flex; flex-direction:column; min-height:100%; background:var(--bg); color:var(--ink); }
  .explorer.dragging { outline:2px dashed var(--accent); outline-offset:-6px; }
  /* 拖拽悬停时的目录树节点高亮（属性由 JS 设置） */
  :global([data-drop-hover]) {
    outline:2px dashed var(--accent) !important;
    outline-offset:-2px;
    background:color-mix(in srgb, var(--accent) 14%, transparent) !important;
    border-radius:4px;
  }
  .drop-bar {
    position:fixed; z-index:70; left:50%; bottom:30px; transform:translateX(-50%);
    display:flex; align-items:center; gap:10px; padding:11px 16px;
    border:1px solid color-mix(in srgb, var(--accent) 42%, var(--rule));
    border-radius:8px; background:var(--bg-elevated);
    box-shadow:0 12px 34px rgba(0,0,0,.28); font-size:13px; color:var(--ink);
  }
  .drop-info b { color:var(--accent); }
  .explorer-header { display:flex; justify-content:space-between; gap:24px; padding:30px 34px 22px; border-bottom:1px solid var(--rule); }
  .eyebrow { color:var(--accent); font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
  .explorer-header h1 { margin:4px 0 6px; font-size:26px; letter-spacing:0; }
  .explorer-header p { margin:0; color:var(--ink-secondary); font-size:14px; }
  .header-actions { display:flex; gap:10px; align-items:center; flex-shrink:0; }
  .button { min-height:36px; border:1px solid var(--rule); border-radius:6px; background:var(--bg-elevated); color:var(--ink); padding:0 13px; font:inherit; font-size:13px; cursor:pointer; }
  .button:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); }
  .button.primary { background:var(--accent); border-color:var(--accent); color:#061812; font-weight:700; }
  .button.primary:hover:not(:disabled) { filter:brightness(1.08); color:#061812; }
  .button:disabled { opacity:.45; cursor:not-allowed; }
  .button-icon { font-size:18px; vertical-align:-1px; }
  .icon-button { border:0; background:transparent; color:var(--ink-faint); font-size:16px; cursor:pointer; }
  .icon-button:hover { color:var(--ink); }

  /* 主布局：左目录树 + 右媒体资产治理 */
  .manage-layout { display:grid; grid-template-columns:240px minmax(0,1fr); flex:1; min-height:0; }
  .explorer-tree { min-width:0; min-height:0; overflow:auto; padding:18px 12px; border-right:1px solid var(--rule); background:var(--bg-elevated); }
  .tree-heading { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; color:var(--ink-secondary); font-size:13px; font-weight:700; }
  .tree-new-folder { width:26px; height:26px; border:1px solid var(--rule); border-radius:5px; background:transparent; color:var(--ink-faint); font-size:15px; cursor:pointer; }
  .tree-new-folder:hover { border-color:var(--accent); color:var(--accent); }
  .manage-pane { min-width:0; min-height:0; display:flex; flex-direction:column; }

  .modal-backdrop { position:fixed; z-index:50; inset:0; display:grid; place-items:center; padding:20px; background:rgba(0,0,0,.48); }
  .modal { width:min(440px, 100%); padding:20px; border:1px solid var(--rule); border-radius:8px; background:var(--bg-elevated); box-shadow:0 18px 50px rgba(0,0,0,.3); }
  .modal-head { display:flex; align-items:center; justify-content:space-between; }
  .modal h2 { margin:0; font-size:17px; }
  .field { display:flex; flex-direction:column; gap:7px; margin:18px 0; color:var(--ink-secondary); font-size:12px; }
  .field input { width:100%; padding:0 10px; outline:0; border:1px solid var(--rule); border-radius:5px; background:var(--bg-elevated); color:var(--ink); font:inherit; font-size:12px; }
  .field input:focus { border-color:var(--accent); }
  .modal-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:20px; }
  .toast { position:fixed; z-index:60; right:24px; bottom:24px; padding:11px 15px; border:1px solid color-mix(in srgb, var(--accent) 42%, var(--rule)); border-radius:6px; background:var(--bg-elevated); color:var(--accent); box-shadow:0 10px 30px rgba(0,0,0,.2); font-size:13px; }
  .toast.error { border-color:color-mix(in srgb, var(--danger, #e26d78) 42%, var(--rule)); color:var(--danger, #e26d78); }
  @media (max-width:1000px) { .explorer-header { padding:24px 22px 18px; } .manage-layout { grid-template-columns:200px minmax(0,1fr); } }
  @media (max-width:760px) { .explorer-header { flex-direction:column; } .header-actions { width:100%; } .header-actions .button { flex:1; } .manage-layout { display:block; } .explorer-tree { border-right:0; border-bottom:1px solid var(--rule); max-height:220px; } }
</style>
