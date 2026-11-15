<script lang="ts">
  // 资产工具栏 — 管理页专用（决策 4：不与媒体页共用一个工具栏组件）。
  // 治理维度（库/目录/标签/状态/来源/排序）与媒体页的浏览维度不同，
  // 共用只会让两边都长出一堆无关控件。
  import { untrack } from 'svelte';
  import type { Library } from '$lib/api/libraries';
  import { filterTreeByType, flattenTags, type Tag } from '$lib/api/tags';
  import type { TagType } from '$lib/stores/libraries.svelte';
  import { SAVED_VIEWS } from '$lib/media/views';
  import { SORT_FIELDS, type MediaQueryState, type ContentSection } from '$lib/media/query';
  import { ATTRIBUTE_LABELS, type AttributeStatus } from '$lib/media/status';
  import { HIDEABLE_COLUMNS } from '$lib/media/columns';
  import { columnPrefs } from '$lib/media/columnPrefs.svelte';
  import { savedFilters } from '$lib/media/savedFilters.svelte';
  import { applyFilter } from '$lib/media/savedFilters';

  let {
    query,
    libraries = [],
    tagTypes = [],
    tags = [],
    total = 0,
    loading = false,
    onpatch,
    onreset,
    onreload,
    onopenDuplicates,
    onopenReconcile,
    onopenNetworkImport
  }: {
    query: MediaQueryState;
    libraries?: Library[];
    tagTypes?: TagType[];
    tags?: Tag[];
    total?: number;
    loading?: boolean;
    onpatch: (patch: Partial<MediaQueryState>) => void;
    onreset: () => void;
    onreload: () => void;
    onopenDuplicates?: () => void;
    onopenReconcile?: () => void;
    onopenNetworkImport?: () => void;
  } = $props();

  /** 「列」下拉是否展开。 */
  let colsOpen = $state(false);
  /** 「我的筛选」下拉是否展开；savingOpen 时显示命名输入框。 */
  let filtersOpen = $state(false);
  // 注意：不要用 `string | null` 直接 bind:value——Svelte 会抛 bind_invalid_value，
  // 而且 svelte-check 不报。开关和文本必须分开。
  let savingOpen = $state(false);
  let savingText = $state('');

  function closeFilters(): void {
    filtersOpen = false;
    savingOpen = false;
    savingText = '';
  }

  function commitSave(): void {
    if (!savingOpen) return;
    const saved = savedFilters.save(savingText, query);
    if (!saved) return;
    savingOpen = false;
    savingText = '';
  }

  const SECTIONS: { value: ContentSection; label: string }[] = [
    { value: 'all', label: '全部类型' },
    { value: 'movie', label: '电影' },
    { value: 'tv', label: '剧集' },
    { value: 'image', label: '图片' },
    { value: 'audio', label: '音频' }
  ];

  const ATTRIBUTES: AttributeStatus[] = ['', 'rated', 'unrated', 'favorite'];

  const SORT_LABELS: Record<string, string> = {
    created_at: '添加时间',
    updated_at: '更新时间',
    filename: '标题',
    size: '大小',
    duration: '时长',
    rating: '评分'
  };

  // 标签按当前标签类型过滤：标签是层级结构，用树过滤（命中的父节点保留整棵子树，
  // 否则会漏掉挂在其它类型父节点下的标签），不能对第一层做扁平 filter。
  // 下拉里仍展平为一维选项。
  const visibleTags = $derived(
    query.tagTypeId === null ? tags : flattenTags(filterTreeByType(tags, query.tagTypeId))
  );

  // 搜索框是本地输入态：只在初始化时取一次 query.q（untrack 表明这是刻意的
  // 快照），之后由下面的 effect 单向同步，避免每次按键回写又触发父级重渲染。
  let searchValue = $state(untrack(() => query.q));
  $effect(() => {
    // 外部重置（点摘要条 / 点「重置」）时把输入框同步回真实值
    if (query.q !== searchValue) searchValue = query.q;
  });
</script>

<div class="toolbar">
  <div class="row">
    <input
      class="search"
      type="search"
      placeholder="搜索标题或文件名…"
      bind:value={searchValue}
      oninput={() => onpatch({ q: searchValue, page: 1 })}
    />

    <select
      class="ctl"
      title="资源库"
      value={query.libraryId}
      onchange={(e) => onpatch({ libraryId: e.currentTarget.value, page: 1 })}
    >
      <option value="">全部资源库</option>
      {#each libraries as lib (lib.id)}
        <option value={lib.id}>{lib.name}</option>
      {/each}
    </select>

    <select
      class="ctl"
      title="内容类型"
      value={query.section}
      onchange={(e) => onpatch({ section: e.currentTarget.value as ContentSection, page: 1 })}
    >
      {#each SECTIONS as s (s.value)}
        <option value={s.value}>{s.label}</option>
      {/each}
    </select>

    <select
      class="ctl"
      title="状态属性"
      value={query.attribute}
      onchange={(e) => onpatch({ attribute: e.currentTarget.value as AttributeStatus, page: 1 })}
    >
      {#each ATTRIBUTES as a (a)}
        <option value={a}>{ATTRIBUTE_LABELS[a]}</option>
      {/each}
    </select>

    <select
      class="ctl"
      title="来源"
      value={query.source}
      onchange={(e) =>
        onpatch({ source: e.currentTarget.value as MediaQueryState['source'], page: 1 })}
    >
      <option value="">全部来源</option>
      <option value="local">本地媒体</option>
      <option value="network">网络媒体</option>
    </select>

    <select
      class="ctl"
      title="标签类型"
      value={query.tagTypeId ?? ''}
      onchange={(e) =>
        onpatch({
          tagTypeId: e.currentTarget.value === '' ? null : Number(e.currentTarget.value),
          tags: [],
          page: 1
        })}
    >
      <option value="">全部标签类型</option>
      {#each tagTypes as t (t.id)}
        <option value={t.id}>{t.name}</option>
      {/each}
    </select>

    <select
      class="ctl"
      title="标签"
      value={query.tags[0] ?? ''}
      onchange={(e) =>
        onpatch({
          tags: e.currentTarget.value ? [e.currentTarget.value] : [],
          page: 1
        })}
    >
      <option value="">全部标签</option>
      {#each visibleTags as t (t.id)}
        <option value={t.id}>{t.name}</option>
      {/each}
    </select>

    <span class="spacer"></span>

    <select
      class="ctl"
      title="排序"
      value={query.sort}
      onchange={(e) => onpatch({ sort: e.currentTarget.value as MediaQueryState['sort'] })}
    >
      {#each SORT_FIELDS as f (f)}
        <option value={f}>{SORT_LABELS[f] ?? f}</option>
      {/each}
    </select>

    <button
      type="button"
      class="ctl icon"
      title={query.order === 'desc' ? '降序（点击切升序）' : '升序（点击切降序）'}
      onclick={() => onpatch({ order: query.order === 'desc' ? 'asc' : 'desc' })}
    >
      {query.order === 'desc' ? '↓' : '↑'}
    </button>

    <div class="seg" role="group" aria-label="视图">
      <button
        type="button"
        class:active={query.display === 'table'}
        title="表格视图"
        onclick={() => onpatch({ display: 'table' })}>☰</button
      >
      <button
        type="button"
        class:active={query.display === 'grid'}
        title="网格视图"
        onclick={() => onpatch({ display: 'grid' })}>▦</button
      >
    </div>

    <button type="button" class="ctl icon" title="刷新" onclick={onreload}>↻</button>
    <button type="button" class="ctl" onclick={onreset} title="清除全部筛选">重置</button>
  </div>

  <div class="row views">
    {#each SAVED_VIEWS as v (v.id)}
      <button
        type="button"
        class="view-chip"
        class:active={query.view === v.id}
        title={v.hint}
        onclick={() => onpatch({ view: v.id, page: 1 })}
      >
        {v.label}
      </button>
    {/each}
    <span class="spacer"></span>

    <!-- 治理工具：重构期间这三个入口随旧组件一起消失了，这里恢复 -->
    {#if onopenDuplicates}
      <button type="button" class="tool" onclick={onopenDuplicates} title="按内容哈希 / 同名 / 同大小查重">
        查重
      </button>
    {/if}
    {#if onopenReconcile}
      <button
        type="button"
        class="tool"
        onclick={onopenReconcile}
        title="把「文件缺失」的记录与磁盘上同名文件对账合并"
      >
        缺失对账
      </button>
    {/if}
    {#if onopenNetworkImport}
      <button type="button" class="tool" onclick={onopenNetworkImport} title="导入网络媒体（URL / 聚合站）">
        网络导入
      </button>
    {/if}

    <!-- 我的筛选：保存当前筛选组合，作为可复用入口 -->
    <div class="colpick">
      <button
        type="button"
        class="tool"
        class:active={savedFilters.items.length > 0}
        aria-expanded={filtersOpen}
        onclick={() => (filtersOpen = !filtersOpen)}
        title="保存当前筛选条件，之后一键恢复"
      >
        我的筛选{savedFilters.items.length > 0 ? ` (${savedFilters.items.length})` : ''}
      </button>
      {#if filtersOpen}
        <div class="col-backdrop" role="presentation" onclick={() => closeFilters()}></div>
        <div class="col-menu saved-menu" role="group" aria-label="我的筛选">
          {#if savedFilters.items.length === 0}
            <p class="saved-empty">还没有保存的筛选。<br />调好条件后点下面的「保存当前筛选」。</p>
          {:else}
            {#each savedFilters.items as f (f.id)}
              <div class="saved-row">
                <button
                  type="button"
                  class="saved-apply"
                  title="应用这个筛选"
                  onclick={() => {
                    onpatch(applyFilter(query, f.filter));
                    closeFilters();
                  }}
                >
                  {f.name}
                </button>
                <button
                  type="button"
                  class="saved-del"
                  title="删除"
                  aria-label={`删除筛选 ${f.name}`}
                  onclick={() => savedFilters.remove(f.id)}
                >
                  ✕
                </button>
              </div>
            {/each}
          {/if}

          {#if !savingOpen}
            <button type="button" class="col-reset" onclick={() => (savingOpen = true)}>
              保存当前筛选…
            </button>
          {:else}
            <div class="saved-form">
              <input
                type="text"
                bind:value={savingText}
                placeholder="给这个筛选起个名字"
                maxlength="24"
                onkeydown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    commitSave();
                  } else if (e.key === 'Escape') {
                    e.preventDefault();
                    savingOpen = false;
                    savingText = '';
                  }
                }}
              />
              <button type="button" class="col-reset" onclick={commitSave}>保存</button>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <!-- 列显示/隐藏：与表格共享 lib/media/columnPrefs（持久化到 localStorage）。
         放在计数左边——计数是右端锚点，放它后面会被挤到边缘裁掉。 -->
    <div class="colpick">
      <button
        type="button"
        class="tool"
        class:active={columnPrefs.hidden.size > 0}
        aria-expanded={colsOpen}
        onclick={() => (colsOpen = !colsOpen)}
        title="选择显示哪些列"
      >
        列{columnPrefs.hidden.size > 0 ? ` (${columnPrefs.hidden.size} 隐藏)` : ''}
      </button>
      {#if colsOpen}
        <div class="col-backdrop" role="presentation" onclick={() => (colsOpen = false)}></div>
        <div class="col-menu" role="group" aria-label="列显示">
          {#each HIDEABLE_COLUMNS as col (col.id)}
            <label class="col-item">
              <input
                type="checkbox"
                checked={columnPrefs.isVisible(col.id)}
                onchange={() => columnPrefs.toggle(col.id)}
              />
              <span>{col.label}</span>
            </label>
          {/each}
          <button type="button" class="col-reset" onclick={() => columnPrefs.reset()}>
            恢复默认
          </button>
        </div>
      {/if}
    </div>

    <span class="count" class:busy={loading}>
      {loading ? '加载中…' : `${total} 项`}
    </span>
  </div>
</div>

<style>
  .toolbar {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px 16px 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .row.views {
    padding-bottom: 10px;
    border-bottom: 1px solid var(--rule);
  }
  .spacer {
    flex: 1;
  }
  .search {
    flex: 1 1 200px;
    min-width: 140px;
    max-width: 320px;
    font: inherit;
    font-size: 13px;
    padding: 6px 10px;
    border-radius: var(--radius);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink);
  }
  .search:focus {
    outline: none;
    border-color: var(--accent);
  }
  .ctl {
    font: inherit;
    font-size: 12.5px;
    padding: 6px 9px;
    border-radius: var(--radius);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    cursor: pointer;
    max-width: 160px;
  }
  .ctl:hover {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .ctl.icon {
    min-width: 30px;
    text-align: center;
    padding: 6px 8px;
  }
  .seg {
    display: inline-flex;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    overflow: hidden;
  }
  .seg button {
    font: inherit;
    font-size: 13px;
    padding: 5px 10px;
    border: none;
    background: transparent;
    color: var(--ink-tertiary);
    cursor: pointer;
  }
  .seg button.active {
    background: var(--accent-soft);
    color: var(--accent);
  }
  .view-chip {
    font: inherit;
    font-size: 12.5px;
    padding: 5px 11px;
    border-radius: var(--radius-full);
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--ink-secondary);
    cursor: pointer;
  }
  .view-chip:hover {
    border-color: var(--ink-faint);
    color: var(--ink);
  }
  .view-chip.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
  }
  .tool {
    font: inherit;
    font-size: 12px;
    padding: 4px 9px;
    border-radius: var(--radius-xs);
    border: 1px dashed var(--rule);
    background: transparent;
    color: var(--ink-tertiary);
    cursor: pointer;
    white-space: nowrap;
  }
  .tool:hover {
    color: var(--accent);
    border-color: var(--accent);
    border-style: solid;
  }
  .tool.active {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 45%, transparent);
    border-style: solid;
    background: var(--accent-soft);
  }
  .colpick {
    position: relative;
  }
  .col-backdrop {
    position: fixed;
    inset: 0;
    z-index: 40;
  }
  .col-menu {
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    z-index: 41;
    min-width: 168px;
    padding: 6px;
    border-radius: var(--radius-md);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    box-shadow: var(--shadow-md);
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .col-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 8px;
    border-radius: var(--radius-xs);
    font-size: 12.5px;
    color: var(--ink-secondary);
    cursor: pointer;
  }
  .col-item:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }
  .col-item input {
    accent-color: var(--accent);
    margin: 0;
  }
  .col-reset {
    margin-top: 4px;
    padding: 5px 8px;
    font: inherit;
    font-size: 12px;
    text-align: left;
    border: none;
    border-top: 1px solid var(--rule-light);
    background: transparent;
    color: var(--ink-tertiary);
    cursor: pointer;
  }
  .col-reset:hover {
    color: var(--accent);
  }
  /* 我的筛选：比「列」面板宽一些，能放下名称 + 删除 */
  .saved-menu {
    min-width: 236px;
  }
  .saved-empty {
    margin: 6px 8px 8px;
    font-size: 12px;
    line-height: 1.6;
    color: var(--ink-faint);
  }
  .saved-row {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .saved-apply {
    flex: 1;
    min-width: 0;
    text-align: left;
    font: inherit;
    font-size: 12.5px;
    padding: 5px 8px;
    border: none;
    border-radius: var(--radius-xs);
    background: transparent;
    color: var(--ink-secondary);
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .saved-apply:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }
  .saved-del {
    flex: none;
    font: inherit;
    font-size: 11px;
    padding: 3px 6px;
    border: none;
    border-radius: var(--radius-xs);
    background: transparent;
    color: var(--ink-faint);
    cursor: pointer;
  }
  .saved-del:hover {
    color: var(--danger);
    background: var(--bg-hover);
  }
  .saved-form {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 6px 2px;
  }
  .saved-form input {
    flex: 1;
    min-width: 0;
    font: inherit;
    font-size: 12.5px;
    padding: 4px 7px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--accent);
    background: var(--bg-elevated);
    color: var(--ink);
  }
  .saved-form input:focus {
    outline: none;
  }
  .count {
    font-size: 12.5px;
    color: var(--ink-tertiary);
    font-variant-numeric: tabular-nums;
  }
  .count.busy {
    color: var(--accent);
  }
</style>
