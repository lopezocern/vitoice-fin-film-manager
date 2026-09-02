<script lang="ts">
  // ManageSidebar — the sidebar for the /manage route.
  // Contains: view switcher (overview/media/tags/recycle), directory tree
  // (media tab), and tag management tree (tags tab) with full CRUD via
  // context menus, inline rename, color picker, move-to-type, add-child,
  // and add-type.
  import { untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { sidebar } from '$lib/stores/sidebar.svelte';
  import { client } from '$lib/api/client';

  type ManageSection =
    | 'dashboard'
    | 'files'
    | 'issues'
    | 'assets'
    | 'metadata'
    | 'tags'
    | 'trash'
    | 'tasks'
    | 'history'
    | 'libraries';

  // 从共享 store 读取
  const collapsed = $derived(sidebar.collapsed);

  // ---- 导航 count 徽标（设计稿：文件与路径 12 / 问题中心 40 / 媒体资产 794 / 回收站 6 / 任务队列 3）----
  let navCounts = $state<{ missing: number; noPoster: number; noMetadata: number; media: number; deleted: number; runningTasks: number; local: number; network: number }>({
    missing: 0, noPoster: 0, noMetadata: 0, media: 0, deleted: 0, runningTasks: 0, local: 0, network: 0,
  });
  let countsLoaded = false;
  async function loadNavCounts(): Promise<void> {
    try {
      const resp = await client.get<{
        summary: { media_count?: number; missing_count?: number; no_poster_count?: number; no_metadata_count?: number; deleted_count?: number; running_tasks?: number; local_count?: number; network_count?: number };
      }>('/stats/summary', undefined, undefined, true);
      const s = resp.summary ?? {};
      navCounts = {
        missing: s.missing_count ?? 0,
        noPoster: s.no_poster_count ?? 0,
        noMetadata: s.no_metadata_count ?? 0,
        media: s.media_count ?? 0,
        deleted: s.deleted_count ?? 0,
        runningTasks: s.running_tasks ?? 0,
        local: s.local_count ?? 0,
        network: s.network_count ?? 0,
      };
    } catch {
      // silent
    }
  }
  $effect(() => {
    if (countsLoaded) return;
    countsLoaded = true;
    // untrack：loadNavCounts 同步部分若读写 $state 会被追踪进 effect 依赖面
    untrack(() => void loadNavCounts());
  });
  const issueCount = $derived(navCounts.missing + navCounts.noPoster + navCounts.noMetadata);
  const problemCount = $derived(navCounts.missing + navCounts.noMetadata);

  // 管理页 section：overview | files | assets | tags | recycle
  // 详情页 /detail/[id] 没有 tab 参数时，使用上次记住的 tab（保持侧边栏状态一致）
  let lastManageTab = $state<'media' | 'tags' | 'recycle'>('media');
  let lastManageSection = $state<ManageSection>('files');
  const tabParam = $derived($page.url.searchParams.get('tab') as 'media' | 'tags' | 'recycle' | null);
  // 有 tab 参数时记住它（在 $effect 中安全更新 $state）
  $effect(() => {
    if (tabParam) {
      lastManageTab = tabParam;
      lastManageSection = tabParam === 'tags' ? 'tags' : tabParam === 'recycle' ? 'trash' : 'assets';
    }
  });
  // 详情页等无 tab 参数的路由：使用上次记住的值
  const manageTab = $derived(tabParam ?? lastManageTab);
  const sectionParam = $derived($page.url.searchParams.get('section'));
  $effect(() => {
    const normalized = sectionParam === 'overview' ? 'dashboard' : sectionParam === 'recycle' ? 'trash' : sectionParam;
    if (normalized && ['dashboard', 'files', 'issues', 'assets', 'metadata', 'tags', 'trash', 'tasks', 'history', 'libraries'].includes(normalized)) {
      lastManageSection = normalized as ManageSection;
    }
  });
  const manageSection = $derived(
    sectionParam === 'overview' ? 'dashboard' : sectionParam === 'recycle' ? 'trash' :
    sectionParam && ['dashboard', 'files', 'issues', 'assets', 'metadata', 'tags', 'trash', 'tasks', 'history', 'libraries'].includes(sectionParam)
      ? sectionParam as ManageSection
      : tabParam
        ? (manageTab === 'tags' ? 'tags' : manageTab === 'recycle' ? 'trash' : 'assets')
        : $page.url.pathname.startsWith('/manage') ? 'files' : lastManageSection
  );

  function switchManageSection(section: ManageSection): void {
    goto(`/manage?section=${section}`);
  }

  // ---- 来源筛选（仅 media tab） ----
  // source 参数值: '' (全部) | 'local' | 'network' | 'missing'
  const sourceFilter = $derived($page.url.searchParams.get('source') || '');

  function setSourceFilter(value: string): void {
    const params = new URLSearchParams($page.url.searchParams);
    if (value) {
      params.set('source', value);
    } else {
      params.delete('source');
    }
    // 保留 tab 等其他参数
    goto(`/manage?${params.toString()}`);
  }
</script>

<div class="sidebar-scroll">
  <!-- 管理导航：文件操作、资产治理和运行状态保持独立上下文。 -->
  <section class="section">
    <div class="section-head" data-tip="工作区">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect>
        <path d="M2 6h12M6 2.5v11" stroke-opacity="0.4"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">工作区</span>{/if}
    </div>
    <button class="item" class:active={manageSection === 'dashboard'} data-tip="资产概览" onclick={() => switchManageSection('dashboard')}>
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="2" y="2" width="5" height="5" rx="1"></rect><rect x="9" y="2" width="5" height="5" rx="1"></rect><rect x="2" y="9" width="5" height="5" rx="1"></rect><rect x="9" y="9" width="5" height="5" rx="1"></rect>
      </svg>
      {#if !collapsed}<span class="item-label">资产概览</span>{/if}
    </button>
    <button class="item" class:active={manageSection === 'files'} data-tip="媒体管理" onclick={() => switchManageSection('files')}>
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path></svg>
      {#if !collapsed}<span class="item-label">媒体管理</span>{/if}
      {#if !collapsed && navCounts.missing > 0}<span class="item-count danger">{navCounts.missing}</span>{/if}
    </button>
    <button class="item" class:active={manageSection === 'issues'} data-tip="问题中心" onclick={() => switchManageSection('issues')}>
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 2 1.8 13h12.4L8 2z"></path><path d="M8 6v3.2M8 11.5v.2" stroke-linecap="round"></path></svg>
      {#if !collapsed}<span class="item-label">问题中心</span>{/if}
      {#if !collapsed && issueCount > 0}<span class="item-count warn">{issueCount}</span>{/if}
    </button>
    <button class="item" class:active={manageSection === 'metadata'} data-tip="元数据与刮削" onclick={() => switchManageSection('metadata')}>
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 2.5h7l3 3V14H3z"></path><path d="M10 2.5V6h3M5.5 9h5M5.5 11.5h3.5"></path></svg>
      {#if !collapsed}<span class="item-label">元数据与刮削</span>{/if}
      {#if !collapsed && navCounts.noMetadata > 0}<span class="item-count warn">{navCounts.noMetadata}</span>{/if}
    </button>
    <button
      class="item"
      class:active={manageSection === 'tags'}
      data-tip="标签治理"
      onclick={() => switchManageSection('tags')}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 2h6.5L14 7.5 8.5 13 2 6.5V2z" stroke-linejoin="round"></path>
        <circle cx="5" cy="5" r="1" fill="currentColor" stroke="none"></circle>
      </svg>
      {#if !collapsed}<span class="item-label">标签治理</span>{/if}
    </button>
    <button
      class="item"
      class:active={manageSection === 'trash'}
      data-tip="回收站"
      onclick={() => switchManageSection('trash')}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M3 4h10M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4"></path>
      </svg>
      {#if !collapsed}<span class="item-label">回收站</span>{/if}
      {#if !collapsed && navCounts.deleted > 0}<span class="item-count">{navCounts.deleted}</span>{/if}
    </button>
  </section>

  <section class="section">
    <div class="section-head" data-tip="运行状态">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 8h2l1.5-4 3 8 1.5-4h4"></path></svg>
      {#if !collapsed}<span class="sec-title">运行状态</span>{/if}
    </div>
    <button class="item" class:active={manageSection === 'tasks'} data-tip="任务队列" onclick={() => switchManageSection('tasks')}>
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M5 3h9M5 8h9M5 13h9"></path><circle cx="2.5" cy="3" r=".7" fill="currentColor"></circle><circle cx="2.5" cy="8" r=".7" fill="currentColor"></circle><circle cx="2.5" cy="13" r=".7" fill="currentColor"></circle></svg>
      {#if !collapsed}<span class="item-label">任务队列</span>{/if}
      {#if !collapsed && navCounts.runningTasks > 0}<span class="item-count warn">{navCounts.runningTasks}</span>{/if}
    </button>
    <button class="item" class:active={manageSection === 'history'} data-tip="操作记录" onclick={() => switchManageSection('history')}>
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="5.5"></circle><path d="M8 5v3.5l2.3 1.4"></path></svg>
      {#if !collapsed}<span class="item-label">操作记录</span>{/if}
    </button>
  </section>

  <section class="section">
    <div class="section-head" data-tip="资源库">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 5h4l1.4 1.5H14V13H2z"></path></svg>
      {#if !collapsed}<span class="sec-title">资源库</span>{/if}
    </div>
    <button class="item" class:active={manageSection === 'libraries'} data-tip="资源库状态" onclick={() => switchManageSection('libraries')}>
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4.5h12v8H2zM4 2.5h8v2"></path><path d="M5 8h6" stroke-opacity=".5"></path></svg>
      {#if !collapsed}<span class="item-label">资源库状态</span>{/if}
    </button>
  </section>

  <!-- 来源筛选：全部 / 本地 / 网络 / 文件丢失（目录树已移入媒体管理主页） -->
  {#if manageSection === 'files'}
    <section class="section">
      <div class="section-head" data-tip="来源">
        <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8" cy="8" r="6"></circle>
          <path d="M2 8h12M8 2c1.5 2 1.5 10 0 12M8 2c-1.5 2-1.5 10 0 12" stroke-opacity="0.5"></path>
        </svg>
        {#if !collapsed}<span class="sec-title">来源</span>{/if}
      </div>
      <button
        class="item"
        class:active={sourceFilter === ''}
        data-tip="全部来源"
        onclick={() => setSourceFilter('')}
      >
        <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect>
          <path d="M2 6h12" stroke-opacity="0.4"></path>
        </svg>
        {#if !collapsed}<span class="item-label">全部来源</span>{/if}
      </button>
      <button
        class="item"
        class:active={sourceFilter === 'local'}
        data-tip="本地媒体"
        onclick={() => setSourceFilter('local')}
      >
        <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="2" y="3" width="12" height="10" rx="1.5"></rect>
          <path d="M4.5 6.5h7M4.5 9.5h4" stroke-opacity="0.5"></path>
        </svg>
        {#if !collapsed}<span class="item-label">本地媒体</span>{/if}
        {#if !collapsed && navCounts.local > 0}<span class="item-count">{navCounts.local}</span>{/if}
      </button>
      <button
        class="item"
        class:active={sourceFilter === 'network'}
        data-tip="网络媒体"
        onclick={() => setSourceFilter('network')}
      >
        <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8" cy="8" r="5.5"></circle>
          <path d="M2.5 8h11M8 2.5c2 2 2 7 0 11M8 2.5c-2 2-2 7 0 11" stroke-opacity="0.5"></path>
        </svg>
        {#if !collapsed}<span class="item-label">网络媒体</span>{/if}
        {#if !collapsed && navCounts.network > 0}<span class="item-count">{navCounts.network}</span>{/if}
      </button>
      <button
        class="item"
        class:active={sourceFilter === 'missing'}
        data-tip="文件丢失"
        onclick={() => setSourceFilter('missing')}
      >
        <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M8 2 1.5 13.5h13L8 2z"></path>
          <path d="M8 6.5v3M8 11.5v.5" stroke-width="1.8" stroke-linecap="round"></path>
        </svg>
        {#if !collapsed}<span class="item-label">文件丢失</span>{/if}
        {#if !collapsed && navCounts.missing > 0}<span class="item-count danger">{navCounts.missing}</span>{/if}
      </button>
    </section>
  {/if}


</div>

<style>
</style>
