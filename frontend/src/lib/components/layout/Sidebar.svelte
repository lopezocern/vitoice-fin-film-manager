<script lang="ts">
  // Sidebar — thin wrapper that handles route detection, data-loading
  // lifecycle, and common layout (toggle button + container). Delegates
  // the actual sidebar content to MediaSidebar or ManageSidebar based on
  // the current route. Tag context menus and delete dialogs are rendered
  // by TagOverlays (state lives in the tagOps store).
  import { onMount, untrack } from 'svelte';
  import { afterNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { sidebar } from '$lib/stores/sidebar.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { tagOps } from '$lib/stores/tagOps.svelte';
  import MediaSidebar from './MediaSidebar.svelte';
  import ManageSidebar from './ManageSidebar.svelte';
  import SettingsSidebar from './SettingsSidebar.svelte';
  import TagOverlays from './TagOverlays.svelte';

  const collapsed = $derived(sidebar.collapsed);

  // 路由检测：/manage 用管理专用侧边栏，/libraries 用资源库管理侧边栏，
  // 其他路由用默认侧边栏。
  // 详情页 /detail/[id] 保持来源路由的侧边栏（管理页→管理侧边栏，媒体页→媒体侧边栏），
  // 通过 sessionStore 记录上一个非 detail 路由，避免侧边栏在详情页突然切换。
  const isManageRoute = $derived($page.url.pathname.startsWith('/manage'));
  const isSettingsRoute = $derived(
    $page.url.pathname.startsWith('/settings') || $page.url.pathname.startsWith('/libraries')
  );
  const isDetailRoute = $derived($page.url.pathname.startsWith('/detail'));

  // 记录来源路由：非 detail 路由时更新，detail 路由时读取
  let lastMainRoute = $state<'media' | 'manage' | 'settings'>('media');
  $effect(() => {
    const path = $page.url.pathname;
    if (path.startsWith('/manage')) {
      lastMainRoute = 'manage';
    } else if (path.startsWith('/settings') || path.startsWith('/libraries')) {
      lastMainRoute = 'settings';
    } else if (!path.startsWith('/detail') && !path.startsWith('/player')) {
      lastMainRoute = 'media';
    }
  });

  // 详情页使用来源路由的侧边栏
  const showManageSidebar = $derived(isManageRoute || (isDetailRoute && lastMainRoute === 'manage'));
  const showSettingsSidebar = $derived(isSettingsRoute || (isDetailRoute && lastMainRoute === 'settings'));

  async function load(): Promise<void> {
    await librariesStore.reload();
  }

  onMount(() => {
    load();
    const onWindowClick = (e: MouseEvent) => tagOps.handleWindowClick(e);
    window.addEventListener('click', onWindowClick);
    return () => window.removeEventListener('click', onWindowClick);
  });

  // 路由导航后刷新侧边栏数据（如从 /import 返回时）。
  // 注意：不能用 ensureLoaded（只在首次加载）——任何页面（详情/管理/播放器）
  // 中修改媒体、标签、计数后返回，侧边栏必须反映最新数据。reload 内部
  // Promise.allSettled 幂等且轻量（库列表 + 标签 + 两个计数），本地后端开销可忽略。
  afterNavigate(() => {
    void librariesStore.reload();
  });

  // 限制内容开关变化时重新加载侧边栏数据（库列表、标签、计数等）
  let prevRestricted: boolean | null = null;
  $effect(() => {
    const current = settingsStore.showRestricted;
    if (prevRestricted !== null && prevRestricted !== current) {
      untrack(() => void librariesStore.reload());
    }
    prevRestricted = current;
  });
</script>

<aside class="sidebar" class:collapsed>
  <!-- 展开/折叠按钮 -->
  <button
    class="toggle-btn"
    onclick={() => (collapsed ? sidebar.expand() : sidebar.collapse())}
    aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
    title={collapsed ? '展开侧栏' : '收起侧栏'}
  >
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6">
      {#if collapsed}
        <path d="M6 3l5 5-5 5" stroke-linecap="round" stroke-linejoin="round"></path>
      {:else}
        <path d="M10 3L5 8l5 5" stroke-linecap="round" stroke-linejoin="round"></path>
      {/if}
    </svg>
  </button>

  {#if showManageSidebar}
    <ManageSidebar />
  {:else if showSettingsSidebar}
    <SettingsSidebar />
  {:else}
    <MediaSidebar />
  {/if}

  <!-- 标签/类型右键菜单与删除确认弹窗（状态在 tagOps store 中） -->
  <TagOverlays />
</aside>

<style>
  .sidebar {
    position: relative;
    width: var(--sidebar-w);
    flex-shrink: 0;
    background: var(--bg-elevated);
    border-right: 1px solid var(--rule);
    display: flex;
    flex-direction: column;
    transition: width var(--dur) var(--ease-out);
    overflow: hidden;
  }

  .sidebar.collapsed {
    width: var(--sidebar-collapsed-w);
  }

  .toggle-btn {
    position: relative;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 32px;
    margin: 6px 8px;
    border: none;
    background: none;
    color: var(--ink-tertiary);
    border-radius: var(--radius);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
    flex-shrink: 0;
    cursor: pointer;
  }

  .toggle-btn svg {
    pointer-events: none;
  }

  .sidebar.collapsed .toggle-btn {
    margin: 6px auto;
    width: 36px;
  }

  .toggle-btn:hover {
    background: var(--bg-hover);
    color: var(--accent);
  }

  /* ============ 共享样式（通过 :global 应用到子组件） ============ */

  .sidebar :global(.sidebar-scroll) {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 4px 0 8px;
  }

  .sidebar :global(.section) {
    padding: 4px 0;
    border-bottom: 1px solid var(--rule-light);
  }

  .sidebar :global(.section:last-child) {
    border-bottom: none;
  }

  .sidebar :global(.section-head) {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px 4px;
    color: var(--ink-faint);
    font-size: 10.5px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .sidebar.collapsed :global(.section-head) {
    justify-content: center;
    padding: 8px 0 4px;
  }

  .sidebar :global(.sec-icon) {
    flex-shrink: 0;
    opacity: 0.7;
  }

  .sidebar :global(.sec-title) {
    white-space: nowrap;
  }

  .sidebar :global(.add-btn) {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    background: none;
    border: none;
    border-radius: var(--radius-xs);
    color: var(--ink-tertiary);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
  }

  .sidebar :global(.add-btn:hover) {
    background: var(--accent-soft);
    color: var(--accent);
  }

  .sidebar :global(.item) {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 7px 14px;
    border: none;
    background: none;
    color: var(--ink-secondary);
    font-size: 13px;
    font-weight: 450;
    text-align: left;
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
  }

  .sidebar.collapsed :global(.item) {
    justify-content: center;
    padding: 8px 0;
  }

  .sidebar :global(.item:hover:not(.disabled)) {
    background: var(--bg-hover);
    color: var(--ink);
  }

  .sidebar :global(.item.disabled) {
    opacity: 0.4;
    cursor: default;
  }

  .sidebar :global(.item.active) {
    background: var(--accent-soft);
    color: var(--accent);
  }

  .sidebar :global(.item.active::before) {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 2px;
    height: 18px;
    background: var(--accent);
    border-radius: 0 1px 1px 0;
  }

  .sidebar :global(.item-icon) {
    flex-shrink: 0;
    color: inherit;
  }

  .sidebar :global(.tag-dot) {
    width: 9px;
    height: 9px;
    border-radius: var(--radius-full);
    background: var(--neutral);
    flex-shrink: 0;
    box-shadow: 0 0 0 1px var(--rule);
  }

  .sidebar :global(.item-label) {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sidebar :global(.count) {
    font-size: 10.5px;
    font-weight: 500;
    color: var(--ink-tertiary);
    background: var(--bg-surface);
    padding: 1px 7px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }

  .sidebar :global(.item.active .count) {
    background: var(--bg-elevated);
    color: var(--accent);
  }

  .sidebar :global(.empty-hint) {
    padding: 4px 14px 8px;
    font-size: 12px;
    color: var(--ink-faint);
  }

  /* ---- 行内重命名输入框（MediaSidebar 和 ManageSidebar 共用） ---- */
  .sidebar :global(.mt-rename-input),
  .sidebar :global(.mt-child-input) {
    flex: 1;
    min-width: 0;
    border: 1px solid var(--accent);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 12.5px;
    padding: 2px 6px;
    border-radius: var(--radius-xs);
    outline: none;
  }

  .sidebar :global(.mt-rename-input:focus),
  .sidebar :global(.mt-child-input:focus) {
    box-shadow: 0 0 0 2px var(--accent-soft);
  }

  /* ---- 收起态 tooltip ---- */
  .sidebar.collapsed :global(.item[data-tip]:hover::after),
  .sidebar.collapsed :global(.section-head[data-tip]:hover::after) {
    content: attr(data-tip);
    position: absolute;
    left: calc(100% + 12px);
    top: 50%;
    transform: translateY(-50%);
    background: var(--bg-active);
    color: var(--ink);
    padding: 5px 10px;
    border-radius: var(--radius);
    font-size: 12px;
    font-weight: 500;
    white-space: nowrap;
    z-index: 50;
    pointer-events: none;
    box-shadow: var(--shadow-md);
    letter-spacing: 0;
    text-transform: none;
    border: 1px solid var(--rule);
  }

  .sidebar.collapsed :global(.section-head) {
    position: relative;
  }

  .sidebar.collapsed :global(.item) {
    position: relative;
  }
</style>
