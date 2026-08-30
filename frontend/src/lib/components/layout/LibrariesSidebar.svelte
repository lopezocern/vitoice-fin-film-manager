<script lang="ts">
  // LibrariesSidebar — the sidebar for the /libraries route.
  // Shows library-management-specific navigation and shortcuts,
  // instead of the irrelevant media sidebar content (library list, tags, etc.).
  import { goto } from '$app/navigation';
  import { sidebar } from '$lib/stores/sidebar.svelte';

  const collapsed = $derived(sidebar.collapsed);
</script>

<div class="sidebar-scroll">
  <!-- 第 1 段：导航 -->
  <section class="section">
    <div class="section-head" data-tip="导航">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">导航</span>{/if}
    </div>
    <button
      class="item"
      data-tip="返回媒体"
      onclick={() => goto('/media')}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect>
        <path d="M2 6h12M6 2.5v11" stroke-opacity="0.4"></path>
      </svg>
      {#if !collapsed}<span class="item-label">返回媒体</span>{/if}
    </button>
    <button
      class="item"
      data-tip="管理中心"
      onclick={() => goto('/manage')}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="2" y="2.5" width="5" height="5" rx="1"></rect>
        <rect x="9" y="2.5" width="5" height="5" rx="1"></rect>
        <rect x="2" y="9.5" width="5" height="4" rx="1"></rect>
        <rect x="9" y="9.5" width="5" height="4" rx="1"></rect>
      </svg>
      {#if !collapsed}<span class="item-label">管理中心</span>{/if}
    </button>
  </section>

  <!-- 第 2 段：快捷操作 -->
  <section class="section">
    <div class="section-head" data-tip="快捷操作">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M8 1.5l1.8 4.2 4.2.3-3.3 2.8 1.1 4.1L8 11l-3.8 2.3 1.1-4.1L2 6.5l4.2-.3L8 1.5z" stroke-linejoin="round"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">快捷操作</span>{/if}
    </div>
    <button
      class="item"
      data-tip="新建资源库"
      onclick={() => goto('/import')}
      style="color: var(--accent);"
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6">
        <line x1="8" y1="3" x2="8" y2="13" stroke-linecap="round"></line>
        <line x1="3" y1="8" x2="13" y2="8" stroke-linecap="round"></line>
      </svg>
      {#if !collapsed}<span class="item-label">新建资源库</span>{/if}
    </button>
  </section>

  <!-- 第 3 段：提示 -->
  {#if !collapsed}
    <section class="section">
      <div class="empty-hint">
        在主区域管理资源库的扫描、刮削与监控配置。
      </div>
    </section>
  {/if}
</div>
