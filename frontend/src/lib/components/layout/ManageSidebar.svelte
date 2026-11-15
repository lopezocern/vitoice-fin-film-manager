<script lang="ts">
  // ManageSidebar — /manage 的导航（PR4：10 个 section 收敛到 5）。
  //
  // 结构：资产（资产工作台）· 治理（标签、回收站）· 运行（任务+历史）· 资源库。
  // 「问题中心 / 元数据与刮削 / 文件缺失」不再是导航项，而是资产工作台里的视图
  // （?view=problem|metadata|missing…），因为它们本来就是同一份列表的筛选条件。
  import { untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { sidebar } from '$lib/stores/sidebar.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { liveQueryParam } from '$lib/stores/urlState.svelte';
  import { client } from '$lib/api/client';
  import DirectoryTree from '$lib/components/layout/DirectoryTree.svelte';
  import { folderTree } from '$lib/stores/folderTree.svelte';

  type ManageSection = 'assets' | 'tags' | 'trash' | 'runs' | 'libraries';

  const collapsed = $derived(sidebar.collapsed);

  // 导航徽标：全部来自 /stats/summary，与对应列表的 total 同源（PR1 保证）。
  let navCounts = $state<{ problem: number; media: number; deleted: number; running: number }>({
    problem: 0,
    media: 0,
    deleted: 0,
    running: 0
  });

  async function loadNavCounts(): Promise<void> {
    try {
      const resp = await client.get<{
        summary: {
          media_count?: number;
          problem_count?: number;
          deleted_count?: number;
          running_tasks?: number;
        };
      }>('/stats/summary', undefined, undefined, true);
      const s = resp.summary ?? {};
      navCounts = {
        problem: s.problem_count ?? 0,
        media: s.media_count ?? 0,
        deleted: s.deleted_count ?? 0,
        running: s.running_tasks ?? 0
      };
    } catch {
      // 静默：徽标拿不到不影响导航
    }
  }

  $effect(() => {
    librariesStore.revision;
    untrack(() => void loadNavCounts());
  });

  // 记住上次的管理 section，供详情页等无 section 参数的路由保持侧边栏高亮。
  const VALID: ManageSection[] = ['assets', 'tags', 'trash', 'runs', 'libraries'];
  let lastSection = $state<ManageSection>('assets');

  // 用 liveQueryParam 而非 $page.url：popstate 重挂载时 page store 丢 query。
  const sectionParam = $derived(liveQueryParam('section'));

  const manageSection = $derived.by((): ManageSection => {
    const raw = sectionParam;
    // 兼容旧参数：recycle → trash
    const normalized = raw === 'recycle' ? 'trash' : raw;
    if (normalized && (VALID as string[]).includes(normalized)) {
      return normalized as ManageSection;
    }
    const tab = liveQueryParam('tab');
    if (tab === 'tags') return 'tags';
    if (tab === 'recycle') return 'trash';
    return $page.url.pathname.startsWith('/manage') ? 'assets' : lastSection;
  });

  $effect(() => {
    if ((VALID as string[]).includes(manageSection)) lastSection = manageSection;
  });

  function switchSection(section: ManageSection): void {
    // 已在当前 section：不做任何事（避免"点当前项把筛选重置掉"的意外）
    if (section === manageSection) return;
    // section 之间不共享查询参数：资产工作台的 lib/dir/q/view 带到标签页/运行页
    // 只会造成"看起来生效其实不生效"的假联动，所以这里只保留 section。
    const params = new URLSearchParams();
    params.set('section', section);
    goto(`/manage?${params.toString()}`);
  }
</script>

<div class="sidebar-scroll">
  <section class="section">
    <div class="section-head" data-tip="资产">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect>
        <path d="M2 6h12M6 2.5v11" stroke-opacity="0.4"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">资产</span>{/if}
    </div>
    <button
      class="item"
      class:active={manageSection === 'assets'}
      data-tip="资产工作台"
      onclick={() => switchSection('assets')}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="2" y="2" width="5" height="5" rx="1"></rect>
        <rect x="9" y="2" width="5" height="5" rx="1"></rect>
        <rect x="2" y="9" width="5" height="5" rx="1"></rect>
        <rect x="9" y="9" width="5" height="5" rx="1"></rect>
      </svg>
      {#if !collapsed}<span class="item-label">资产工作台</span>{/if}
      {#if !collapsed && navCounts.problem > 0}
        <span class="count warn">{navCounts.problem}</span>
      {/if}
    </button>

    <!-- 库 / 目录树：仅在资产工作台展开时显示。
         DirectoryTree 直接读写 URL 的 lib/dir 参数，点目录即过滤资产列表。 -->
    {#if manageSection === 'assets'}
      <div class="tree-host">
        {#key folderTree.revision}
          <DirectoryTree libraries={librariesStore.libraries} {collapsed} />
        {/key}
      </div>
    {/if}

    <div class="section-head" data-tip="治理" style="margin-top:14px">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M8 2 2.5 4.5v4c0 3 2.3 5 5.5 5.5 3.2-.5 5.5-2.5 5.5-5.5v-4L8 2z"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">治理</span>{/if}
    </div>
    <button
      class="item"
      class:active={manageSection === 'tags'}
      data-tip="标签治理"
      onclick={() => switchSection('tags')}
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
      onclick={() => switchSection('trash')}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M3 4h10M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M5 4v9a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1V4"></path>
      </svg>
      {#if !collapsed}<span class="item-label">回收站</span>{/if}
      {#if !collapsed && navCounts.deleted > 0}
        <span class="count">{navCounts.deleted}</span>
      {/if}
    </button>

    <div class="section-head" data-tip="运行" style="margin-top:14px">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 8h2l1.5-4 3 8 1.5-4h4"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">运行</span>{/if}
    </div>
    <button
      class="item"
      class:active={manageSection === 'runs'}
      data-tip="运行（任务 + 历史）"
      onclick={() => switchSection('runs')}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="8" cy="8" r="5.5"></circle>
        <path d="M8 5v3.5l2.3 1.4"></path>
      </svg>
      {#if !collapsed}<span class="item-label">运行</span>{/if}
      {#if !collapsed && navCounts.running > 0}
        <span class="count warn">{navCounts.running}</span>
      {/if}
    </button>

    <div class="section-head" data-tip="资源库" style="margin-top:14px">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 5h4l1.4 1.5H14V13H2z"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">资源库</span>{/if}
    </div>
    <button
      class="item"
      class:active={manageSection === 'libraries'}
      data-tip="资源库状态"
      onclick={() => switchSection('libraries')}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 4.5h12v8H2zM4 2.5h8v2"></path>
        <path d="M5 8h6" stroke-opacity=".5"></path>
      </svg>
      {#if !collapsed}<span class="item-label">资源库状态</span>{/if}
    </button>
  </section>
</div>

<style>
  /* 基础徽标样式由 Sidebar.svelte 的全局 .count 提供；这里只补语义色。 */
  .count.warn {
    color: var(--warn);
  }
  /* 目录树嵌在导航里：左侧缩进与滚动交给子组件，这里只做与导航项的对齐 */
  .tree-host {
    margin: 2px 0 6px;
    min-height: 0;
  }
</style>
