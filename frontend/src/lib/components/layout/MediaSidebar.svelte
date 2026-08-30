<script lang="ts">
  // MediaSidebar — the default sidebar for media routes (/media, /import, etc.).
  // Contains: library list, tag groups (with AV isolation filtering), quick
  // access entries, and smart folders.
  import { goto } from '$app/navigation';
  import { navigation, type NavNode } from '$lib/stores/navigation.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { sidebar } from '$lib/stores/sidebar.svelte';
  import { tagOps } from '$lib/stores/tagOps.svelte';
  import { flattenTags } from '$lib/api/tags';
  import { safeColor, displayTypeName } from './sidebarShared';

  // 从共享 store 读取
  const libraries = $derived(librariesStore.libraries);
  // 受限开关关闭时本地即时隐藏受限库（is_restricted 标记已在本地数据中，
  // 无需等后端 reload 完成，切换设置后侧边栏立即生效）
  const visibleLibraries = $derived(
    settingsStore.showRestricted
      ? libraries
      : libraries.filter((l) => !l.is_restricted)
  );
  const tags = $derived(librariesStore.tags);
  const tagTypes = $derived(librariesStore.tagTypes);
  const smartFolders = $derived(librariesStore.smartFolders);
  const totalCount = $derived(librariesStore.totalCount);
  const favoriteCount = $derived(librariesStore.favoriteCount);
  const loading = $derived(librariesStore.loading);
  const collapsed = $derived(sidebar.collapsed);

  function navigate(node: NavNode): void {
    navigation.set(node);
    if (location.pathname !== '/media') {
      goto('/media');
    }
  }

  function isActive(type: NavNode['type'], value: string): boolean {
    return navigation.current.type === type && navigation.current.value === value;
  }

  // ---- 默认侧边栏标签分组（按 tag_type_id 分组，可收缩） ----
  // null = 初始状态（全部收起）；Set = 用户显式操作后的状态（仅展开集合中的分组）。
  // 展开/收起状态持久化到 localStorage——跨会话、跨组件重建保持一致。
  const OPEN_TAG_GROUPS_KEY = 'vitoice.sidebar.openTagGroups';

  function loadOpenTagGroups(): Set<number> | null {
    try {
      if (typeof localStorage === 'undefined') return null;
      const raw = localStorage.getItem(OPEN_TAG_GROUPS_KEY);
      if (!raw) return null;
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return null;
      const set = new Set<number>();
      for (const v of arr) {
        if (typeof v === 'number' && Number.isFinite(v)) set.add(v);
      }
      return set;
    } catch {
      return null;
    }
  }

  function saveOpenTagGroups(set: Set<number> | null): void {
    try {
      if (typeof localStorage === 'undefined') return;
      if (set === null || set.size === 0) {
        localStorage.removeItem(OPEN_TAG_GROUPS_KEY);
      } else {
        localStorage.setItem(OPEN_TAG_GROUPS_KEY, JSON.stringify([...set]));
      }
    } catch {
      /* ignore storage errors */
    }
  }

  let sidebarOpenTagGroups = $state<Set<number> | null>(loadOpenTagGroups());

  // AV 隔离：根据当前浏览的库类型过滤标签
  const currentLibrary = $derived(
    navigation.current.type === 'library'
      ? libraries.find((l) => l.id === navigation.current.value) ?? null
      : null
  );
  const isAvLibrary = $derived(currentLibrary?.scrape_mode === 'av');
  const isNonAvLibrary = $derived(currentLibrary !== null && !isAvLibrary);

  const avTypeIds = $derived(
    new Set(
      tagTypes
        .filter((tt) => tt.name.startsWith('av_'))
        .map((tt) => tt.id)
    )
  );

  // 根据当前库类型过滤标签（先扁平化树形数据）
  const filteredTags = $derived.by(() => {
    const flat = flattenTags(tags);
    if (avTypeIds.size === 0) return flat;
    if (isAvLibrary) {
      return flat.filter((t) => avTypeIds.has(t.tag_type_id ?? -1));
    }
    if (isNonAvLibrary) {
      return flat.filter((t) => !avTypeIds.has(t.tag_type_id ?? -1));
    }
    // 跨库视图（全部媒体/收藏/最近等）：显示所有标签
    return flat;
  });

  const groupedTags = $derived.by(() => {
    const map = new Map<number, typeof tags>();
    for (const t of filteredTags) {
      const tid = (t as any).tag_type_id ?? 0;
      if (!map.has(tid)) map.set(tid, []);
      map.get(tid)!.push(t);
    }
    // 按 tagTypes 的 sort_order 排序，未知类型排到最后
    const typeOrder = (id: number): number => {
      const tt = tagTypes.find(x => x.id === id);
      return tt?.sort_order ?? 9999;
    };
    return Array.from(map.entries())
      .sort((a, b) => typeOrder(a[0]) - typeOrder(b[0]))
      .map(([typeId, items]) => ({
        typeId,
        typeName: displayTypeName(tagTypes.find(tt => tt.id === typeId)?.name ?? '其他'),
        typeColor: tagTypes.find(tt => tt.id === typeId)?.color ?? null,
        items,
        open: sidebarOpenTagGroups !== null && sidebarOpenTagGroups.has(typeId),
      }));
  });

  function toggleTagGroup(typeId: number) {
    const next = new Set(sidebarOpenTagGroups ?? []);
    if (next.has(typeId)) next.delete(typeId); else next.add(typeId);
    sidebarOpenTagGroups = next;
    saveOpenTagGroups(next);
  }
</script>

<div class="sidebar-scroll">
  <!-- 第 1 段：资源库 -->
  <section class="section">
    <div class="section-head" data-tip="资源库">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">资源库</span>{/if}
      {#if !collapsed}
        <button
          class="add-btn"
          title="新建资源库"
          aria-label="新建资源库"
          onclick={() => goto('/import')}
        >
          <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8">
            <line x1="8" y1="3" x2="8" y2="13" stroke-linecap="round"></line>
            <line x1="3" y1="8" x2="13" y2="8" stroke-linecap="round"></line>
          </svg>
        </button>
      {/if}
    </div>
    <button
      class="item"
      class:active={isActive('all', 'all')}
      data-tip="全部媒体"
      onclick={() => navigate({ type: 'all', value: 'all', label: '全部媒体' })}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <rect x="2" y="2.5" width="12" height="11" rx="1.5"></rect>
        <path d="M2 6h12M6 2.5v11" stroke-opacity="0.4"></path>
      </svg>
      {#if !collapsed}
        <span class="item-label">全部媒体</span>
        <span class="count">{totalCount}</span>
      {/if}
    </button>
    {#each visibleLibraries as lib (lib.id)}
      <button
        class="item"
        class:active={isActive('library', lib.id)}
        data-tip={lib.name}
        onclick={() => navigate({ type: 'library', value: lib.id, label: lib.name })}
      >
        <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
        </svg>
        {#if !collapsed}
          <span class="item-label">{lib.name}</span>
          {#if lib.media_count != null}<span class="count">{lib.media_count}</span>{/if}
        {/if}
      </button>
    {/each}
    {#if collapsed}
      <button
        class="item"
        data-tip="新建资源库"
        aria-label="新建资源库"
        title="新建资源库"
        onclick={() => goto('/import')}
        style="color: var(--accent);"
      >
        <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6">
          <line x1="8" y1="3" x2="8" y2="13" stroke-linecap="round"></line>
          <line x1="3" y1="8" x2="13" y2="8" stroke-linecap="round"></line>
        </svg>
      </button>
    {/if}
  </section>

  <!-- 第 2 段：快捷入口 -->
  <section class="section">
    <div class="section-head" data-tip="快捷入口">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M8 1.5l1.8 4.2 4.2.3-3.3 2.8 1.1 4.1L8 11l-3.8 2.3 1.1-4.1L2 6.5l4.2-.3L8 1.5z" stroke-linejoin="round"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">快捷入口</span>{/if}
    </div>
    <button
      class="item"
      class:active={isActive('continue', 'continue')}
      data-tip="继续观看"
      onclick={() => navigate({ type: 'continue', value: 'continue', label: '继续观看' })}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="8" cy="8" r="6"></circle>
        <path d="M6.5 5.5v5l4-2.5-4-2.5z" fill="currentColor" stroke="none"></path>
      </svg>
      {#if !collapsed}<span class="item-label">继续观看</span>{/if}
    </button>
    <button
      class="item"
      class:active={isActive('recent', 'recent')}
      data-tip="最近添加"
      onclick={() => navigate({ type: 'recent', value: 'recent', label: '最近添加' })}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="8" cy="8" r="6"></circle>
        <path d="M8 4.5V8l2.2 1.4" stroke-linecap="round" stroke-linejoin="round"></path>
        <path d="M11 2.5l.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8.8-1.7z" fill="currentColor" stroke="none" opacity="0.8"></path>
      </svg>
      {#if !collapsed}<span class="item-label">最近添加</span><span class="count">{totalCount}</span>{/if}
    </button>
    <button
      class="item"
      class:active={isActive('favorite', 'favorite')}
      data-tip="我的收藏"
      onclick={() => navigate({ type: 'favorite', value: 'favorite', label: '我的收藏' })}
    >
      <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M8 13.5s-5-3-5-7a2.8 2.8 0 0 1 5-1.5A2.8 2.8 0 0 1 13 6.5c0 4-5 7-5 7z" stroke-linejoin="round"></path>
      </svg>
      {#if !collapsed}<span class="item-label">我的收藏</span><span class="count">{favoriteCount}</span>{/if}
    </button>
  </section>

  <!-- 第 3 段：智能文件夹 -->
  <section class="section">
    <div class="section-head" data-tip="智能文件夹">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 4a1 1 0 0 1 1-1h3.5l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4z"></path>
        <path d="M8 6.5l1 2 2 .2-1.5 1.4.4 2L8 11.2 6.1 12.1l.4-2L5 8.7l2-.2 1-2z" fill="currentColor" stroke="none" opacity="0.7"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">智能文件夹</span>{/if}
    </div>
    {#if smartFolders.length === 0 && !loading}
      {#if !collapsed}<div class="empty-hint">暂无智能文件夹</div>{:else}
        <div class="item disabled" data-tip="暂无智能文件夹">
          <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
            <path d="M2 4a1 1 0 0 1 1-1h3.5l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4z"></path>
          </svg>
        </div>
      {/if}
    {:else}
      {#each smartFolders as folder (folder.id)}
        <button
          class="item"
          class:active={isActive('smartfolder', String(folder.id))}
          data-tip={folder.name}
          onclick={() => navigate({ type: 'smartfolder', value: String(folder.id), label: folder.name })}
        >
          <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" style={safeColor(folder.color) ? `color:${safeColor(folder.color)}` : ''}>
            <path d="M2 4a1 1 0 0 1 1-1h3.5l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4z"></path>
            <path d="M8 6.5l1 2 2 .2-1.5 1.4.4 2L8 11.2 6.1 12.1l.4-2L5 8.7l2-.2 1-2z" fill="currentColor" stroke="none" opacity="0.7"></path>
          </svg>
          {#if !collapsed}
            <span class="item-label">{folder.name}</span>
            {#if folder.preview_count != null}<span class="count">{folder.preview_count}</span>{/if}
          {/if}
        </button>
      {/each}
    {/if}
  </section>

  <!-- 第 4 段：标签 -->
  <section class="section">
    <div class="section-head" data-tip="标签">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 2h6.5L14 7.5 8.5 13 2 6.5V2z" stroke-linejoin="round"></path>
        <circle cx="5" cy="5" r="1" fill="currentColor" stroke="none"></circle>
      </svg>
      {#if !collapsed}<span class="sec-title">标签{isAvLibrary ? ' (限制内容)' : ''}</span>{/if}
    </div>
    {#if filteredTags.length === 0 && !loading}
      {#if !collapsed}<div class="empty-hint">暂无标签</div>{:else}
        <div class="item disabled" data-tip="暂无标签">
          <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
            <path d="M2 2h6.5L14 7.5 8.5 13 2 6.5V2z" stroke-linejoin="round"></path>
          </svg>
        </div>
      {/if}
    {:else if collapsed}
      <!-- 收起态：保持扁平图标列表 -->
      {#each filteredTags as tag (tag.id)}
        <button
          class="item"
          class:active={isActive('tag', tag.id)}
          data-tip={tag.name}
          onclick={() => navigate({ type: 'tag', value: tag.id, label: tag.name })}
        >
          <span class="tag-dot" style={safeColor(tag.color) ? `background:${safeColor(tag.color)}` : ''}></span>
        </button>
      {/each}
    {:else}
      <!-- 展开态：按标签类型分组，可收缩，支持右键改名 -->
      <div class="tag-groups">
        {#each groupedTags as group (group.typeId)}
          <div class="tag-group">
            {#if tagOps.renamingTypeId === group.typeId}
              <div class="tag-group-head renaming">
                <span class="tag-group-arrow"></span>
                <input
                  class="mt-rename-input"
                  bind:value={tagOps.renamingTypeName}
                  onkeydown={(e) => {
                    if (e.key === 'Enter') tagOps.saveTypeRename();
                    if (e.key === 'Escape') { e.stopPropagation(); tagOps.renamingTypeId = null; }
                  }}
                  onblur={() => tagOps.saveTypeRename()}
                >
              </div>
            {:else}
              <button
                class="tag-group-head"
                onclick={() => toggleTagGroup(group.typeId)}
                oncontextmenu={() => { /* 媒体页/配置页等禁用右键菜单（管理页才有） */ }}
              >
                <span class="tag-group-arrow">{group.open ? '▾' : '▸'}</span>
                <span
                  class="tag-group-dot"
                  style={safeColor(group.typeColor) ? `background:${safeColor(group.typeColor)}` : ''}
                ></span>
                <span class="tag-group-label">{group.typeName}</span>
                <span class="tag-group-count">{group.items.length}</span>
              </button>
            {/if}
            {#if group.open}
              <div class="tag-group-items">
                {#each group.items as tag (tag.id)}
                  {#if tagOps.renamingTagId === tag.id}
                    <div class="item tag-item renaming">
                      <span class="tag-dot" style={safeColor(tag.color) ? `background:${safeColor(tag.color)}` : ''}></span>
                      <input
                        class="mt-rename-input"
                        bind:value={tagOps.renamingTagName}
                        onkeydown={(e) => {
                          if (e.key === 'Enter') tagOps.saveTagRename(tag);
                          if (e.key === 'Escape') tagOps.renamingTagId = null;
                        }}
                        onblur={() => tagOps.saveTagRename(tag)}
                      >
                    </div>
                  {:else}
                    <button
                      class="item tag-item"
                      class:active={isActive('tag', tag.id)}
                      data-tip={tag.name}
                      onclick={() => navigate({ type: 'tag', value: tag.id, label: tag.name })}
                      oncontextmenu={() => { /* 媒体页/配置页等禁用右键菜单（管理页才有） */ }}
                    >
                      <span class="tag-dot" style={safeColor(tag.color) ? `background:${safeColor(tag.color)}` : ''}></span>
                      <span class="item-label">{tag.name}</span>
                      {#if tag.count != null}<span class="count">{tag.count}</span>{/if}
                    </button>
                  {/if}
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </section>
</div>

<style>
  /* ---- 默认侧边栏标签分组 ---- */
  .tag-groups {
    padding: 2px 0;
  }
  .tag-group {
    margin-bottom: 1px;
  }
  .tag-group-head {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding: 5px 14px 5px 8px;
    border: none;
    background: none;
    color: var(--ink-secondary);
    font-size: 11.5px;
    font-weight: 600;
    text-align: left;
    cursor: pointer;
    border-radius: var(--radius);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
  }
  .tag-group-head:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }
  .tag-group-arrow {
    width: 12px;
    text-align: center;
    color: var(--ink-tertiary);
    font-size: 10px;
    flex-shrink: 0;
  }
  .tag-group-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background: var(--neutral);
    flex-shrink: 0;
    box-shadow: 0 0 0 1px var(--rule);
  }
  .tag-group-label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tag-group-count {
    font-size: 10px;
    font-weight: 500;
    color: var(--ink-tertiary);
    background: var(--bg-surface);
    padding: 1px 6px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }
  .tag-group-items {
    padding-left: 10px;
  }
  .tag-item {
    padding-left: 18px;
  }
</style>
