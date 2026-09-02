<script lang="ts">
  // 管理页 - 全局治理页，处理批量操作和破坏性操作
  // 与 /media 页筛选独立
  // 支持新的 ?section=overview|files|assets|tags|recycle，同时兼容旧 ?tab= 参数
  //
  // 父组件职责（薄编排层）：
  //   1. 管理 active tab 状态（从 URL ?tab= 读取）
  //   2. 加载共享数据（libraries、tags），供 MediaManageView 使用
  //   3. 根据 tab 渲染对应子组件
  //
  // 各 Tab 视图逻辑已在子组件中实现：
  //   - MediaManageView.svelte 媒体管理（筛选/批量操作/列表/网格）
  //   - TagsManageView.svelte  标签管理
  //   - RecycleBinView.svelte  回收站

  import { liveQueryParam } from '$lib/stores/urlState.svelte';
  import OverviewView from '$lib/components/manage/OverviewView.svelte';
  import FileExplorerView from '$lib/components/manage/FileExplorerView.svelte';
  import ManageModuleView from '$lib/components/manage/ManageModuleView.svelte';
  import TagsManageView from '$lib/components/manage/TagsManageView.svelte';
  import RecycleBinView from '$lib/components/manage/RecycleBinView.svelte';

  type ManageSection = 'dashboard' | 'files' | 'issues' | 'assets' | 'metadata' | 'tags' | 'trash' | 'tasks' | 'history' | 'libraries';
  // 用 liveQueryParam 而非 $pageStore.url：popstate 重挂载时只恢复 pathname、丢 query，
  // section 会退回 files 并被写回 URL，覆盖刚返回的历史条目。
  const currentSection = $derived.by((): ManageSection => {
    const section = liveQueryParam('section');
    if (section === 'overview') return 'dashboard';
    if (section === 'recycle') return 'trash';
    // 媒体资产已并入媒体管理：?section=assets 与 ?tab=media 都进入 files（默认媒体资产视图）
    if (section === 'assets') return 'files';
    if (section === 'dashboard' || section === 'files' || section === 'issues' || section === 'metadata' || section === 'tags' || section === 'trash' || section === 'tasks' || section === 'history' || section === 'libraries') {
      return section;
    }
    const tab = liveQueryParam('tab');
    if (tab === 'tags') return 'tags';
    if (tab === 'recycle') return 'trash';
    return 'files';
  });
</script>

<svelte:head><title>管理 — vitoice</title></svelte:head>

<div class="manage-page">
  <div class="manage-main">
    {#if currentSection === 'dashboard'}
      <OverviewView />
    {:else if currentSection === 'files'}
      <FileExplorerView />
    {:else if currentSection === 'tags'}
      <!-- ============ 标签管理视图 ============ -->
      <div class="tags-view">
        <TagsManageView />
      </div>
    {:else if currentSection === 'trash'}
      <!-- ============ 回收站视图 ============ -->
      <RecycleBinView />
    {:else}
      <ManageModuleView kind={currentSection as 'issues' | 'metadata' | 'tasks' | 'history' | 'libraries'} />
    {/if}
  </div>
</div>

<style>
  .manage-page {
    display: flex;
    flex-direction: row;
    flex: 1;
    min-height: 0;
  }

  .manage-main {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    min-height: 0;
  }

  /* 标签管理视图容器 — 必须撑满高度并传递 flex 链 */
  .tags-view {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
</style>
