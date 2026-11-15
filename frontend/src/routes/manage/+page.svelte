<script lang="ts">
  // 管理页 — 薄编排层（PR4：5 个 section）。
  //
  //   section=assets    资产工作台（唯一列表层 + 摘要条）
  //   section=tags      标签治理
  //   section=trash     回收站
  //   section=runs      运行（任务 + 历史，tab 区分）
  //   section=libraries 资源库状态（含库健康）
  //
  // 旧 `?section=overview|files|issues|metadata|tasks|history` 一律在
  // `+page.ts` 里 307 重定向到上面五项（见该文件顶部的迁移表）。
  import { liveQueryParam } from '$lib/stores/urlState.svelte';
  import AssetsWorkspace from '$lib/components/manage/AssetsWorkspace.svelte';
  import RunsView from '$lib/components/manage/RunsView.svelte';
  import LibrariesStatusView from '$lib/components/manage/LibrariesStatusView.svelte';
  import TagsManageView from '$lib/components/manage/TagsManageView.svelte';
  import RecycleBinView from '$lib/components/manage/RecycleBinView.svelte';

  type ManageSection = 'assets' | 'tags' | 'trash' | 'runs' | 'libraries';

  // 用 liveQueryParam 而非 $pageStore.url：popstate 重挂载时只恢复 pathname、丢 query，
  // section 会退回默认值并被写回 URL，覆盖刚返回的历史条目。
  const currentSection = $derived.by((): ManageSection => {
    const raw = liveQueryParam('section');
    const section = raw === 'recycle' ? 'trash' : raw;
    if (section === 'tags' || section === 'trash' || section === 'runs' || section === 'libraries') {
      return section;
    }
    return 'assets';
  });

  const runsTab = $derived(liveQueryParam('tab') === 'history' ? 'history' : 'tasks');
</script>

<svelte:head><title>管理 — vitoice</title></svelte:head>

<div class="manage-page">
  <div class="manage-main">
    {#if currentSection === 'assets'}
      <AssetsWorkspace />
    {:else if currentSection === 'tags'}
      <div class="tags-view">
        <TagsManageView />
      </div>
    {:else if currentSection === 'trash'}
      <RecycleBinView />
    {:else if currentSection === 'runs'}
      <RunsView tab={runsTab} />
    {:else}
      <LibrariesStatusView />
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

  /* 标签治理视图容器 — 必须撑满高度并传递 flex 链 */
  .tags-view {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
</style>
