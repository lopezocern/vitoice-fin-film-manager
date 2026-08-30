<script lang="ts">
  // 标签管理页：卡片网格视图，左侧类型面板 + 右侧卡片网格 + 关联媒体列表
  import { onMount, untrack } from 'svelte';
  import { client, ApiError } from '$lib/api/client';
  import { mediaApi, type Media } from '$lib/api/media';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
  import { tagManageStore } from '$lib/stores/tagManage.svelte';
  import { tagOps } from '$lib/stores/tagOps.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import type { Tag } from '$lib/api/tags';

  interface TagType {
    id: number;
    name: string;
    color: string;
    is_builtin: boolean;
    sort_order: number;
    created_at: string;
  }

  interface TagNode {
    id: number;
    name: string;
    tag_type_id: number;
    parent_id: number | null;
    description: string | null;
    color: string | null;
    sort_order: number;
    created_at: string;
    updated_at: string;
    children: TagNode[];
    media_count?: number | null;
  }

  // ---- 状态 ----
  let tagTypes = $state<TagType[]>([]);
  // 从共享 store 读取选中类型（由 Sidebar 写入）
  const selectedTypeId = $derived(tagManageStore.selectedTypeId);
  let tagTree = $state<TagNode[]>([]);
  let loadingTags = $state(false);
  let error = $state<string | null>(null);

  // 卡片选择 & 关联媒体
  let selectedTagId = $state<number | null>(null);
  let selectedTagMedia = $state<Media[]>([]);
  let mediaLoading = $state(false);

  // 多选模式 & 批量操作
  let multiSelectMode = $state(false);
  let selectedTagIds = $state<Set<number>>(new Set());
  let batchLoading = $state(false);
  let batchDeleteOpen = $state(false);
  let batchMoveOpen = $state(false);
  let batchColorOpen = $state(false);
  let batchMoveTargetTypeId = $state<number | null>(null);

  // 搜索 & 排序
  let searchQuery = $state('');
  let sortBy = $state<'name' | 'created_at'>('name');

  // 各标签关联媒体数量
  let tagMediaCounts = $state<Record<number, number>>({});

  // 新建标签
  let showAddTag = $state(false);
  let newTagName = $state('');

  // 新建标签类型（页面内左侧面板，设计稿）
  let showAddType = $state(false);
  let newTypeName = $state('');

  async function addType(): Promise<void> {
    const name = newTypeName.trim();
    if (!name) return;
    try {
      const created = await client.post<{ id: number }>('/tag-types', {
        name,
        is_builtin: false,
        sort_order: tagTypes.length,
      });
      await loadTypes();
      if (created?.id) tagManageStore.selectType(created.id);
      showAddType = false;
      newTypeName = '';
      showToast('标签类型已创建');
    } catch {
      showToast('创建标签类型失败', 'err');
    }
  }
  function cancelAddType(): void {
    showAddType = false;
    newTypeName = '';
  }

  // 重命名（标签行内编辑）
  let renamingId = $state<number | null>(null);
  let renamingName = $state('');

  // 删除确认
  let deleteTagOpen = $state(false);
  let deleteTagTarget = $state<TagNode | null>(null);

  // 右键菜单 - 标签
  let tagContextMenu = $state<{ x: number; y: number; tag: TagNode } | null>(null);

  // 标签编辑弹窗
  let editTagOpen = $state(false);
  let editTagTarget = $state<TagNode | null>(null);
  let editTagName = $state('');
  let editTagColor = $state<string | null>(null);
  let editTagDescription = $state('');

  // toast
  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  function showToast(msg: string, type: 'ok' | 'err' = 'ok'): void {
    toast = { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2600);
  }

  const PALETTE = [
    '#635bff', '#f59e0b', '#34c759', '#ff3b30', '#ff2d55',
    '#af52de', '#5ac8fa', '#ff9500', '#8e8e93', '#00c7be'
  ];

  // 标签类型显示名映射
  const typeNameDisplay: Record<string, string> = {
    'actor': '演员',
    'genre': '类型',
    'theme': '主题',
    'custom': '自定义',
    'collection': '合集',
    'studio': '工作室',
    'av_actress': '女优',
    'av_genre': '限制内容类型',
    'av_studio': '厂商',
    'av_series': '系列',
    'av_director': '导演',
  };
  const displayTypeName = (name: string): string => typeNameDisplay[name] ?? name;

  // ---- 派生 ----
  const selectedType = $derived(
    tagTypes.find((t) => t.id === selectedTypeId) ?? null
  );

  // 扁平化树，用于卡片网格
  const flatTags = $derived.by(() => {
    const out: TagNode[] = [];
    const walk = (nodes: TagNode[]) => {
      for (const n of nodes) {
        out.push(n);
        if (n.children.length > 0) walk(n.children);
      }
    };
    walk(tagTree);
    return out;
  });

  // 每个标签类型的标签数量（左侧类型面板计数，设计稿 tag-groups）
  // 使用 librariesStore.tags 全量标签树（跨类型），而非当前类型的 tagTree，
  // 否则其他类型的计数恒为 0。
  const typeTagCounts = $derived.by(() => {
    const counts = new Map<number, number>();
    for (const t of tagTypes) counts.set(t.id, 0);
    const walk = (nodes: Tag[]) => {
      for (const n of nodes) {
        if (n.tag_type_id != null && counts.has(n.tag_type_id)) {
          counts.set(n.tag_type_id, (counts.get(n.tag_type_id) ?? 0) + 1);
        }
        if (n.children && n.children.length > 0) walk(n.children);
      }
    };
    walk(librariesStore.tags);
    return counts;
  });

  // 过滤 + 排序后的卡片列表
  const displayTags = $derived.by(() => {
    let list = flatTags;
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter((t) => t.name.toLowerCase().includes(q));
    }
    list = [...list];
    if (sortBy === 'name') {
      list.sort((a, b) => a.name.localeCompare(b.name, 'zh'));
    } else {
      list.sort((a, b) => a.created_at.localeCompare(b.created_at));
    }
    return list;
  });

  const selectedTag = $derived(
    flatTags.find((t) => t.id === selectedTagId) ?? null
  );

  // 多选已选数量
  const selectedCount = $derived(selectedTagIds.size);

  // ---- 加载 ----
  async function loadTypes(): Promise<void> {
    try {
      // noCache：标签类型是配置类数据，删除/重命名后必须立即反映（30s GET 缓存
      // 会让"删了再进来"仍显示旧数据）
      const list = await client.get<TagType[]>('/tag-types', undefined, undefined, true);
      tagTypes = list ?? [];
    } catch (e) {
      error = e instanceof ApiError ? '加载标签类型失败' : '加载失败，请检查后端服务';
    }
  }

  async function loadTags(typeId: number): Promise<void> {
    loadingTags = true;
    selectedTagId = null;
    selectedTagMedia = [];
    selectedTagIds = new Set();
    searchQuery = '';
    try {
      // noCache：删除标签/打标后计数与树结构必须实时（同上，避免 30s 缓存旧数据）
      const list = await client.get<TagNode[]>('/tags', { tag_type_id: typeId }, undefined, true);
      tagTree = list ?? [];
      // Build media counts from backend response (media_count field)
      const counts: Record<number, number> = {};
      const walk = (nodes: TagNode[]) => {
        for (const n of nodes) {
          counts[n.id] = n.media_count ?? 0;
          if (n.children.length > 0) walk(n.children);
        }
      };
      walk(tagTree);
      tagMediaCounts = counts;
    } catch {
      tagTree = [];
    } finally {
      loadingTags = false;
    }
  }

  // 监听 Sidebar 中类型选择变化，自动加载对应标签。
  // untrack 包裹：loadTags 同步写入了 loadingTags 等本地 $state，若被本 effect
  // 追踪为依赖，本地 state 变化会自我重跑造成无限循环。
  $effect(() => {
    const typeId = tagManageStore.selectedTypeId;
    untrack(() => {
      if (typeId !== null) {
        loadTags(typeId);
      } else {
        tagTree = [];
        selectedTagId = null;
        selectedTagMedia = [];
      }
    });
  });

  // 删除标签/打标/移动库等操作（tagOps → librariesStore.reload）后 revision++，
  // 刷新当前类型的标签树——否则删除的标签仍显示在网格里，要切走再切回才消失。
  $effect(() => {
    const rev = librariesStore.revision;
    const typeId = tagManageStore.selectedTypeId;
    if (rev > 0 && typeId !== null) {
      untrack(() => loadTags(typeId));
    }
  });

  // 监听 Sidebar 中标签点击，同步选中并加载关联媒体。
  // untrack 包裹 selectTag：selectTag 同步写入了本地 $state（selectedTagId/
  // renamingId/loadMediaForTag 的 mediaLoading），若被本 effect 追踪为依赖，
  // 本地 selectedTagId 会在 tagId/null 间反复切换从而自我重跑，造成无限循环。
  $effect(() => {
    const tagId = tagManageStore.selectedTagId;
    if (tagId !== null) {
      untrack(() => selectTag(tagId));
    }
  });

  function selectTag(tagId: number): void {
    if (selectedTagId === tagId) {
      // 取消选中
      selectedTagId = null;
      selectedTagMedia = [];
      return;
    }
    selectedTagId = tagId;
    renamingId = null;
    loadMediaForTag(tagId);
  }

  async function loadMediaForTag(tagId: number): Promise<void> {
    mediaLoading = true;
    try {
      const res = await mediaApi.list({ tags: [String(tagId)], page_size: 50 });
      selectedTagMedia = res.items;
      tagMediaCounts = { ...tagMediaCounts, [tagId]: res.total };
    } catch {
      selectedTagMedia = [];
    } finally {
      mediaLoading = false;
    }
  }

  // ---- Tag 操作 ----
  async function addTag(): Promise<void> {
    if (selectedTypeId === null) return;
    const name = newTagName.trim();
    if (!name) return;
    try {
      const created = await client.post<TagNode>('/tags', {
        name,
        tag_type_id: selectedTypeId,
        parent_id: null,
        sort_order: 0
      });
      tagTree = [...tagTree, created];
      newTagName = '';
      showAddTag = false;
      showToast('已创建标签');
      tagMediaCounts = { ...tagMediaCounts, [created.id]: 0 };
    } catch {
      showToast('创建标签失败', 'err');
    }
  }

  function startRename(node: TagNode): void {
    renamingId = node.id;
    renamingName = node.name;
  }

  async function saveRename(node: TagNode): Promise<void> {
    const name = renamingName.trim();
    if (!name) {
      renamingId = null;
      return;
    }
    try {
      await client.put(`/tags/${node.id}`, { name });
      const update = (nodes: TagNode[]): TagNode[] =>
        nodes.map((n) =>
          n.id === node.id ? { ...n, name } : { ...n, children: update(n.children) }
        );
      tagTree = update(tagTree);
      renamingId = null;
    } catch {
      showToast('重命名失败', 'err');
    }
  }

  function cancelRename(): void {
    renamingId = null;
  }

  function askDeleteTag(node: TagNode): void {
    deleteTagTarget = node;
    deleteTagOpen = true;
  }

  async function confirmDeleteTag(): Promise<void> {
    if (!deleteTagTarget) return;
    const target = deleteTagTarget;
    try {
      await client.delete(`/tags/${target.id}`);
      const remove = (nodes: TagNode[]): TagNode[] =>
        nodes
          .filter((n) => n.id !== target.id)
          .map((n) => ({ ...n, children: remove(n.children) }));
      tagTree = remove(tagTree);
      if (selectedTagId === target.id) {
        selectedTagId = null;
        selectedTagMedia = [];
      }
      // 同步侧边栏标签树/计数：本地更新只影响本视图，其他组件依赖
      // librariesStore（reload → revision++ → 各监听者刷新）
      void librariesStore.reload();
      showToast('已删除标签');
    } catch {
      showToast('删除失败', 'err');
    } finally {
      deleteTagTarget = null;
      deleteTagOpen = false;
    }
  }

  function cancelAddTag(): void {
    showAddTag = false;
    newTagName = '';
  }

  // ---- 多选模式 & 批量操作 ----
  function toggleMultiSelect(): void {
    multiSelectMode = !multiSelectMode;
    if (!multiSelectMode) {
      selectedTagIds = new Set();
    } else {
      // 进入多选模式时清除单选，保证互斥
      selectedTagId = null;
      selectedTagMedia = [];
    }
  }

  function toggleTagSelection(id: number): void {
    const next = new Set(selectedTagIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    selectedTagIds = next;
  }

  function clearBatchSelection(): void {
    selectedTagIds = new Set();
  }

  function askBatchDelete(): void {
    if (selectedTagIds.size === 0) return;
    batchDeleteOpen = true;
  }

  async function confirmBatchDelete(): Promise<void> {
    if (selectedTagIds.size === 0) {
      batchDeleteOpen = false;
      return;
    }
    const ids = [...selectedTagIds];
    batchLoading = true;
    const remove = (nodes: TagNode[], id: number): TagNode[] =>
      nodes
        .filter((n) => n.id !== id)
        .map((n) => ({ ...n, children: remove(n.children, id) }));
    let success = 0;
    let failed = 0;
    const deletedIds = new Set<number>();
    for (const id of ids) {
      try {
        await client.delete(`/tags/${id}`);
        success++;
        deletedIds.add(id);
      } catch {
        failed++;
      }
    }
    if (deletedIds.size > 0) {
      let tree = tagTree;
      for (const id of deletedIds) {
        tree = remove(tree, id);
      }
      tagTree = tree;
      // 清理已删除标签的 media count
      const newCounts: Record<number, number> = {};
      for (const [k, v] of Object.entries(tagMediaCounts)) {
        if (!deletedIds.has(Number(k))) newCounts[Number(k)] = v;
      }
      tagMediaCounts = newCounts;
    }
    batchLoading = false;
    batchDeleteOpen = false;
    selectedTagIds = new Set();
    if (success > 0) {
      // 同步侧边栏标签树/计数（同上）
      void librariesStore.reload();
      showToast(`已删除 ${success} 个标签${failed > 0 ? `，${failed} 个失败` : ''}`, failed > 0 ? 'err' : 'ok');
    } else {
      showToast('删除失败', 'err');
    }
  }

  function askBatchMove(): void {
    if (selectedTagIds.size === 0) return;
    batchMoveTargetTypeId = selectedTypeId;
    batchMoveOpen = true;
  }

  async function confirmBatchMove(): Promise<void> {
    const currentTypeId = selectedTypeId;
    if (selectedTagIds.size === 0 || batchMoveTargetTypeId === null || currentTypeId === null) {
      batchMoveOpen = false;
      return;
    }
    const ids = [...selectedTagIds];
    const targetTypeId = batchMoveTargetTypeId;
    batchLoading = true;
    let success = 0;
    let failed = 0;
    for (const id of ids) {
      try {
        await client.put(`/tags/${id}`, { tag_type_id: targetTypeId });
        success++;
      } catch {
        failed++;
      }
    }
    batchLoading = false;
    batchMoveOpen = false;
    selectedTagIds = new Set();
    batchMoveTargetTypeId = null;
    const typeName = tagTypes.find((t) => t.id === targetTypeId)?.name ?? '';
    if (success > 0) {
      showToast(`已移动 ${success} 个标签到「${typeName}」${failed > 0 ? `，${failed} 个失败` : ''}`, failed > 0 ? 'err' : 'ok');
      // 刷新当前类型标签列表（移动到其他类型的标签会从当前列表移除）
      loadTags(currentTypeId);
    } else {
      showToast('移动失败', 'err');
    }
  }

  function askBatchColor(): void {
    if (selectedTagIds.size === 0) return;
    batchColorOpen = true;
  }

  async function confirmBatchColor(color: string): Promise<void> {
    if (selectedTagIds.size === 0) {
      batchColorOpen = false;
      return;
    }
    const ids = [...selectedTagIds];
    batchLoading = true;
    let success = 0;
    let failed = 0;
    const successIds = new Set<number>();
    for (const id of ids) {
      try {
        await client.put(`/tags/${id}`, { color });
        success++;
        successIds.add(id);
      } catch {
        failed++;
      }
    }
    if (successIds.size > 0) {
      const update = (nodes: TagNode[]): TagNode[] =>
        nodes.map((n) =>
          successIds.has(n.id) ? { ...n, color } : { ...n, children: update(n.children) }
        );
      tagTree = update(tagTree);
    }
    batchLoading = false;
    batchColorOpen = false;
    selectedTagIds = new Set();
    if (success > 0) {
      showToast(`已修改 ${success} 个标签的颜色${failed > 0 ? `，${failed} 个失败` : ''}`, failed > 0 ? 'err' : 'ok');
    } else {
      showToast('修改颜色失败', 'err');
    }
  }

  function cancelBatchMove(): void {
    if (batchLoading) return;
    batchMoveOpen = false;
    batchMoveTargetTypeId = null;
  }

  function cancelBatchColor(): void {
    if (batchLoading) return;
    batchColorOpen = false;
  }

  // ---- 标签右键菜单 ----
  function onTagContextMenu(e: MouseEvent, tag: TagNode): void {
    e.preventDefault();
    e.stopPropagation();
    const x = Math.min(e.clientX, window.innerWidth - 240);
    const y = Math.min(e.clientY, window.innerHeight - 280);
    tagContextMenu = { x, y, tag };
  }

  function closeTagContextMenu(): void {
    tagContextMenu = null;
  }

  function contextEditTag(): void {
    if (!tagContextMenu) return;
    const tag = tagContextMenu.tag;
    editTagTarget = tag;
    editTagName = tag.name;
    editTagColor = tag.color;
    editTagDescription = tag.description ?? '';
    editTagOpen = true;
    tagContextMenu = null;
  }

  function contextRenameTag(): void {
    if (!tagContextMenu) return;
    startRename(tagContextMenu.tag);
    tagContextMenu = null;
  }

  function contextChangeTagColor(color: string): void {
    if (!tagContextMenu) return;
    const tag = tagContextMenu.tag;
    tagContextMenu = null;
    updateTagColor(tag, color);
  }

  function contextDeleteTag(): void {
    if (!tagContextMenu) return;
    askDeleteTag(tagContextMenu.tag);
    tagContextMenu = null;
  }

  // 添加子标签：用 tagOps 状态驱动内联输入（与侧边栏标签树一致）
  function contextAddChildTag(): void {
    if (!tagContextMenu) return;
    const tag = tagContextMenu.tag;
    tagContextMenu = null;
    tagOps.startAddChild({ id: String(tag.id), name: tag.name, tag_type_id: tag.tag_type_id } as Tag);
    tagOps.addingChildTo = String(tag.id);
  }

  // 移动到类型：用 tagOps 状态驱动内联选择器
  function contextMoveTypeTag(): void {
    if (!tagContextMenu) return;
    const tag = tagContextMenu.tag;
    tagContextMenu = null;
    tagOps.startMoveType({ id: String(tag.id), name: tag.name, tag_type_id: tag.tag_type_id } as Tag);
    tagOps.moveTypeFor = String(tag.id);
  }

  async function updateTagColor(tag: TagNode, color: string): Promise<void> {
    try {
      await client.put(`/tags/${tag.id}`, { color });
      const update = (nodes: TagNode[]): TagNode[] =>
        nodes.map((n) =>
          n.id === tag.id ? { ...n, color } : { ...n, children: update(n.children) }
        );
      tagTree = update(tagTree);
      showToast('已修改颜色');
    } catch {
      showToast('修改颜色失败', 'err');
    }
  }

  // ---- 标签编辑弹窗 ----
  async function saveEditTag(): Promise<void> {
    if (!editTagTarget) return;
    const name = editTagName.trim();
    if (!name) return;
    try {
      await client.put(`/tags/${editTagTarget.id}`, {
        name,
        color: editTagColor,
        description: editTagDescription
      });
      const target = editTagTarget;
      const newName = name;
      const newColor = editTagColor;
      const newDesc = editTagDescription;
      const update = (nodes: TagNode[]): TagNode[] =>
        nodes.map((n) =>
          n.id === target.id
            ? { ...n, name: newName, color: newColor, description: newDesc }
            : { ...n, children: update(n.children) }
        );
      tagTree = update(tagTree);
      editTagOpen = false;
      editTagTarget = null;
      showToast('已保存标签');
    } catch {
      showToast('保存失败', 'err');
    }
  }

  function cancelEditTag(): void {
    editTagOpen = false;
    editTagTarget = null;
  }

  // ---- 右键菜单关闭（点击外部 / Escape） ----
  $effect(() => {
    if (tagContextMenu) {
      const onDown = () => {
        tagContextMenu = null;
      };
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          tagContextMenu = null;
        }
      };
      window.addEventListener('click', onDown);
      window.addEventListener('keydown', onKey);
      return () => {
        window.removeEventListener('click', onDown);
        window.removeEventListener('keydown', onKey);
      };
    }
  });

  function getThumbUrl(m: Media): string {
    if (m.thumbnail) return mediaApi.thumbnailUrl(m.id, m.updated_at);
    if (m.poster) return mediaApi.posterUrl(m.id, m.updated_at);
    return '';
  }

  onMount(loadTypes);
</script>

<div class="tags-page">
  <!-- 页面头部（设计稿 section-head） -->
  <div class="tags-head">
    <div>
      <h2>标签治理</h2>
      <p>维护标签体系、合并重复标签和检查孤立标签</p>
    </div>
    <button class="button primary" onclick={() => (showAddType = true)}>＋ 新建标签类型</button>
  </div>

  <div class="tag-admin">
  <!-- 左侧：标签类型列表（设计稿 tag-groups） -->
  <aside class="tag-groups">
    <div class="side-label">标签类型</div>
    {#each [...tagTypes].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)) as type (type.id)}
      <button
        class="tag-group"
        class:active={selectedTypeId === type.id}
        onclick={() => { tagManageStore.selectType(selectedTypeId === type.id ? null : type.id); }}
        oncontextmenu={(e) => { e.preventDefault(); e.stopPropagation(); tagOps.openTypeContextMenu(e, { id: type.id, name: type.name, color: type.color ?? null, is_builtin: type.is_builtin, sort_order: type.sort_order }); }}
      >
        <span class="tag-group-dot" style={type.color ? `background:${type.color}` : ''}></span>
        <span class="tag-group-name">{displayTypeName(type.name)}</span>
        <span class="tag-group-count">{typeTagCounts.get(type.id) ?? 0}</span>
      </button>
    {/each}
    {#if showAddType}
      <div class="add-type-row">
        <input
          type="text"
          class="add-type-input"
          placeholder="类型名称"
          bind:value={newTypeName}
          onkeydown={(e) => { if (e.key === 'Enter') addType(); if (e.key === 'Escape') cancelAddType(); }}
        />
        <div class="add-type-actions">
          <button class="mini-btn primary" onclick={addType} disabled={!newTypeName.trim()}>创建</button>
          <button class="mini-btn ghost" onclick={cancelAddType}>取消</button>
        </div>
      </div>
    {/if}
  </aside>

  <!-- 右侧：卡片网格（设计稿 tag-content） -->
  <section class="tag-content">
    <!-- 工具栏（设计稿 view-toolbar） -->
    <div class="tag-toolbar">
      <span class="toolbar-title">类型标签</span>
      <span class="toolbar-meta">{flatTags.length} 个标签</span>
      <span class="toolbar-spacer"></span>
      <div class="search-input-wrap">
        <svg class="search-icon" viewBox="0 0 16 16" width="14" height="14" fill="none">
          <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" stroke-width="1.5"/>
          <line x1="10" y1="10" x2="14" y2="14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <input
          type="text"
          class="search-input"
          placeholder="搜索标签…"
          bind:value={searchQuery}
        />
      </div>
      <select class="sort-select" bind:value={sortBy}>
        <option value="name">名称排序</option>
        <option value="created_at">创建时间</option>
      </select>
      {#if selectedTypeId !== null}
        <button class="mini-btn" onclick={() => { showAddTag = true; }}>＋ 新建标签</button>
        <button
          class="mini-btn"
          class:active={multiSelectMode}
          onclick={toggleMultiSelect}
          disabled={batchLoading}
        >
          {multiSelectMode ? '退出批量' : '批量操作'}
        </button>
      {/if}
    </div>

      {#if showAddTag && selectedTypeId !== null}
        <div class="add-tag-row">
          <input
            type="text"
            class="add-tag-input"
            placeholder="标签名称"
            bind:value={newTagName}
            onkeydown={(e) => { if (e.key === 'Enter') addTag(); if (e.key === 'Escape') cancelAddTag(); }}
          />
          <button class="mini-btn primary" onclick={addTag} disabled={!newTagName.trim()}>创建</button>
          <button class="mini-btn ghost" onclick={cancelAddTag}>取消</button>
        </div>
      {/if}

    <!-- 批量操作工具条 -->
    {#if multiSelectMode}
      <div class="batch-toolbar">
        <span class="batch-count">已选 {selectedCount} 项</span>
        <div class="batch-actions">
          <button
            class="batch-btn"
            onclick={clearBatchSelection}
            disabled={batchLoading || selectedCount === 0}
          >取消选择</button>
          <button
            class="batch-btn danger"
            onclick={askBatchDelete}
            disabled={batchLoading || selectedCount === 0}
          >批量删除</button>
          <button
            class="batch-btn"
            onclick={askBatchMove}
            disabled={batchLoading || selectedCount === 0}
          >批量移动类型</button>
          <button
            class="batch-btn"
            onclick={askBatchColor}
            disabled={batchLoading || selectedCount === 0}
          >批量改色</button>
        </div>
        {#if batchLoading}
          <span class="batch-loading-text">处理中…</span>
        {/if}
      </div>
    {/if}

    <!-- 卡片网格 -->
    <div class="card-area">
      {#if loadingTags}
        <div class="state-msg">加载中…</div>
      {:else if selectedTypeId === null}
        <div class="state-msg empty">
          <div class="empty-icon">&#x1F3F7;</div>
          <div class="empty-text">请从侧边栏选择一个标签类型</div>
        </div>
      {:else if displayTags.length === 0}
        <div class="state-msg empty">
          <div class="empty-icon">&#x1F3F7;</div>
          <div class="empty-text">{searchQuery ? '无匹配标签' : '该类型下暂无标签'}</div>
          {#if !searchQuery}
            <button class="link-btn" onclick={() => (showAddTag = true)}>新建标签</button>
          {/if}
        </div>
      {:else}
        <div class="card-grid">
          {#each displayTags as tag (tag.id)}
            <button
              class="tag-card"
              class:selected={selectedTagId === tag.id || (multiSelectMode && selectedTagIds.has(tag.id))}
              class:renaming={renamingId === tag.id}
              class:multi={multiSelectMode}
              onclick={() => {
                if (renamingId !== null) return;
                if (multiSelectMode) {
                  toggleTagSelection(tag.id);
                } else {
                  selectTag(tag.id);
                }
              }}
              oncontextmenu={(e) => onTagContextMenu(e, tag)}
            >
              {#if multiSelectMode}
                <span class="card-checkbox" class:checked={selectedTagIds.has(tag.id)}>
                  {#if selectedTagIds.has(tag.id)}
                    <svg viewBox="0 0 12 12" width="8" height="8" aria-hidden="true">
                      <path d="M2 6l3 3 5-6" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                  {/if}
                </span>
              {/if}

              {#if selectedTagId === tag.id && renamingId !== tag.id && !multiSelectMode}
                <span class="selected-badge">已选中</span>
              {/if}

              {#if renamingId === tag.id}
                <input
                  type="text"
                  class="rename-input"
                  bind:value={renamingName}
                  onclick={(e) => e.stopPropagation()}
                  onkeydown={(e) => {
                    if (e.key === 'Enter') { e.stopPropagation(); saveRename(tag); }
                    if (e.key === 'Escape') { e.stopPropagation(); cancelRename(); }
                  }}
                />
                <div class="rename-actions" onclick={(e) => e.stopPropagation()}>
                  <button class="icon-btn" onclick={() => saveRename(tag)}>✓</button>
                  <button class="icon-btn" onclick={cancelRename}>✕</button>
                </div>
              {:else}
                <span class="card-color-dot" style={`background:${tag.color ?? selectedType?.color ?? '#8e8e93'}`}></span>
                <span class="card-name">{tag.name}</span>
                <span class="card-subtitle">{tagMediaCounts[tag.id] ?? 0} 个媒体 · {selectedType?.is_builtin ? '系统标签' : '用户标签'}</span>
              {/if}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- 添加子标签（tagOps 内联输入，右键菜单触发） -->
    {#if tagOps.addingChildTo}
      {@const parent = flatTags.find((t) => String(t.id) === tagOps.addingChildTo)}
      {#if parent}
        <div class="inline-ops-row">
          <div class="inline-ops-label">为「{parent.name}」添加子标签：</div>
          <input
            class="inline-ops-input"
            placeholder="子标签名称"
            bind:value={tagOps.newChildName}
            onkeydown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); void tagOps.confirmAddChild(parent as unknown as Tag); }
              if (e.key === 'Escape') { e.preventDefault(); tagOps.addingChildTo = null; }
            }}
            onblur={() => { if (tagOps.addingChildTo) void tagOps.confirmAddChild(parent as unknown as Tag); }}
          />
          <button class="mini-btn ghost" onclick={() => { tagOps.addingChildTo = null; tagOps.newChildName = ''; }}>取消</button>
        </div>
      {/if}
    {/if}

    <!-- 移动到类型（tagOps 内联选择器，右键菜单触发） -->
    {#if tagOps.moveTypeFor}
      {@const moveTag = flatTags.find((t) => String(t.id) === tagOps.moveTypeFor)}
      {#if moveTag}
        <div class="inline-ops-row">
          <div class="inline-ops-label">将「{moveTag.name}」移动到：</div>
          <div class="inline-ops-types">
            {#each tagTypes as tt (tt.id)}
              <button
                class="inline-type-option"
                class:active={tt.id === moveTag.tag_type_id}
                onclick={() => void tagOps.confirmMoveType(moveTag as unknown as Tag, tt.id)}
              >
                <span class="type-dot" style={`background:${tt.color}`}></span>
                <span>{displayTypeName(tt.name)}</span>
              </button>
            {/each}
          </div>
          <button class="mini-btn ghost" onclick={() => { tagOps.moveTypeFor = null; }}>取消</button>
        </div>
      {/if}
    {/if}

    <!-- 选中标签的关联媒体列表 -->
    {#if selectedTag && selectedTagId !== null && !multiSelectMode && renamingId !== selectedTagId}
      <div class="media-section">
        <div class="media-section-head">
          <h2 class="media-title-head">「{selectedTag.name}」关联的媒体</h2>
          <div class="media-head-actions">
            <button class="action-btn" onclick={() => startRename(selectedTag)}>重命名</button>
            <button class="action-btn danger" onclick={() => askDeleteTag(selectedTag)}>删除</button>
          </div>
        </div>

        <div class="media-list-wrap">
          {#if mediaLoading}
            <div class="state-msg">加载中…</div>
          {:else if selectedTagMedia.length === 0}
            <div class="state-msg subtle">暂无关联媒体</div>
          {:else}
            <div class="media-items">
              {#each selectedTagMedia as m (m.id)}
                <div class="media-item">
                  {#if m.thumbnail || m.poster}
                    <img class="media-thumb" src={getThumbUrl(m)} alt="" />
                  {:else}
                    <div class="media-thumb placeholder"></div>
                  {/if}
                  <span class="media-title">{m.title || m.filename}</span>
                  {#if m.year}
                    <span class="media-year">{m.year}</span>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    {/if}
  </section>
  </div>
</div>

<!-- 删除标签确认 -->
<ConfirmDialog
  bind:open={deleteTagOpen}
  title="删除标签"
  description={deleteTagTarget ? `确定删除「${deleteTagTarget.name}」？\n\n该操作将影响已使用此标签的媒体记录。` : ''}
  confirmText="删除"
  danger={true}
  onconfirm={confirmDeleteTag}
  oncancel={() => { deleteTagTarget = null; deleteTagOpen = false; }}
/>

<!-- 标签右键菜单 -->
{#if tagContextMenu}
  <div
    class="ctx-menu"
    style={`left:${tagContextMenu.x}px;top:${tagContextMenu.y}px`}
    onclick={(e) => e.stopPropagation()}
  >
    <button class="ctx-item" onclick={contextEditTag}>编辑标签</button>
    <button class="ctx-item" onclick={contextRenameTag}>重命名</button>
    <button class="ctx-item" onclick={contextAddChildTag}>添加子标签</button>
    <button class="ctx-item" onclick={contextMoveTypeTag}>移动到类型</button>
    <div class="ctx-section">
      <div class="ctx-label">修改颜色</div>
      <div class="ctx-palette">
        {#each PALETTE as c (c)}
          <button
            class="ctx-color"
            class:active={tagContextMenu.tag.color === c}
            style={`background:${c}`}
            onclick={() => contextChangeTagColor(c)}
          ></button>
        {/each}
      </div>
    </div>
    <div class="ctx-divider"></div>
    <button class="ctx-item danger" onclick={contextDeleteTag}>删除</button>
  </div>
{/if}

<!-- 标签编辑弹窗 -->
{#if editTagOpen}
  <div class="modal-backdrop" onclick={(e) => { if (e.target === e.currentTarget) cancelEditTag(); }}>
    <div class="edit-modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => { if (e.key === 'Escape') cancelEditTag(); }}>
      <h2 class="edit-modal-title">编辑标签</h2>
      <div class="edit-field">
        <label class="edit-label" for="edit-tag-name">名称</label>
        <input
          id="edit-tag-name"
          class="edit-input"
          type="text"
          bind:value={editTagName}
          onkeydown={(e) => { if (e.key === 'Enter') saveEditTag(); if (e.key === 'Escape') cancelEditTag(); }}
        />
      </div>
      <div class="edit-field">
        <span class="edit-label">颜色</span>
        <div class="edit-palette">
          {#each PALETTE as c (c)}
            <button
              class="dot-swatch"
              class:active={editTagColor === c}
              style={`background:${c}`}
              onclick={() => (editTagColor = c)}
            ></button>
          {/each}
          <button
            class="dot-swatch none-swatch"
            class:active={editTagColor === null}
            onclick={() => (editTagColor = null)}
            title="无颜色"
          ></button>
        </div>
      </div>
      <div class="edit-field">
        <label class="edit-label" for="edit-tag-desc">描述</label>
        <textarea
          id="edit-tag-desc"
          class="edit-textarea"
          bind:value={editTagDescription}
          rows="3"
          placeholder="添加描述…"
        ></textarea>
      </div>
      <div class="edit-actions">
        <button class="mini-btn ghost" onclick={cancelEditTag}>取消</button>
        <button class="mini-btn primary" onclick={saveEditTag} disabled={!editTagName.trim()}>保存</button>
      </div>
    </div>
  </div>
{/if}

<!-- 批量删除确认 -->
<ConfirmDialog
  bind:open={batchDeleteOpen}
  title="批量删除标签"
  description={`确定删除选中的 ${selectedCount} 个标签？\n\n该操作将影响已使用这些标签的媒体记录，且不可撤销。`}
  confirmText={batchLoading ? '删除中…' : '删除'}
  danger={true}
  disableConfirm={batchLoading}
  onconfirm={confirmBatchDelete}
  oncancel={() => { if (!batchLoading) batchDeleteOpen = false; }}
/>

<!-- 批量移动类型 -->
{#if batchMoveOpen}
  <div class="modal-backdrop" onclick={(e) => { if (e.target === e.currentTarget) cancelBatchMove(); }}>
    <div class="edit-modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => { if (e.key === 'Escape') cancelBatchMove(); }}>
      <h2 class="edit-modal-title">批量移动到类型</h2>
      <div class="edit-field">
        <span class="edit-label">选择目标类型（已选 {selectedCount} 项）</span>
        <div class="move-type-list">
          {#each tagTypes as t (t.id)}
            <button
              class="move-type-item"
              class:active={batchMoveTargetTypeId === t.id}
              class:current={t.id === selectedTypeId}
              onclick={() => (batchMoveTargetTypeId = t.id)}
              disabled={batchLoading}
            >
              <span class="type-dot" style={`background:${t.color}`}></span>
              <span class="type-name">{t.name}</span>
              {#if t.id === selectedTypeId}
                <span class="move-current-tag">当前</span>
              {/if}
            </button>
          {/each}
        </div>
      </div>
      <div class="edit-actions">
        <button class="mini-btn ghost" onclick={cancelBatchMove} disabled={batchLoading}>取消</button>
        <button
          class="mini-btn primary"
          onclick={confirmBatchMove}
          disabled={batchLoading || batchMoveTargetTypeId === null}
        >{batchLoading ? '处理中…' : '移动'}</button>
      </div>
    </div>
  </div>
{/if}

<!-- 批量修改颜色 -->
{#if batchColorOpen}
  <div class="modal-backdrop" onclick={(e) => { if (e.target === e.currentTarget) cancelBatchColor(); }}>
    <div class="edit-modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => { if (e.key === 'Escape') cancelBatchColor(); }}>
      <h2 class="edit-modal-title">批量修改颜色</h2>
      <div class="edit-field">
        <span class="edit-label">选择颜色（已选 {selectedCount} 项）</span>
        <div class="edit-palette">
          {#each PALETTE as c (c)}
            <button
              class="dot-swatch"
              style={`background:${c}`}
              onclick={() => confirmBatchColor(c)}
              disabled={batchLoading}
              title={batchLoading ? '处理中…' : '应用此颜色'}
            ></button>
          {/each}
        </div>
        {#if batchLoading}
          <div class="batch-modal-loading">处理中…</div>
        {/if}
      </div>
      <div class="edit-actions">
        <button class="mini-btn ghost" onclick={cancelBatchColor} disabled={batchLoading}>取消</button>
      </div>
    </div>
  </div>
{/if}

{#if toast}
  <div class="toast" class:ok={toast.type === 'ok'} class:err={toast.type === 'err'}>{toast.msg}</div>
{/if}

<style>
  .tags-page {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    padding: 22px 26px 40px;
    overflow: auto;
  }

  /* ===== 页面头部（设计稿 section-head）===== */
  .tags-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 18px;
  }
  .tags-head h2 { margin: 0; font-size: 23px; line-height: 1.2; color: var(--ink); }
  .tags-head p { margin: 6px 0 0; color: var(--ink-secondary); font-size: 13px; }
  .button.primary {
    min-height: 33px;
    padding: 0 12px;
    border: 1px solid var(--accent);
    border-radius: 6px;
    background: var(--accent);
    color: #061812;
    font-family: inherit;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
  }
  .button.primary:hover { filter: brightness(1.08); }

  /* ===== 主容器（设计稿 tag-admin）===== */
  .tag-admin {
    display: grid;
    grid-template-columns: 240px minmax(0, 1fr);
    min-height: 0;
    flex: 1;
    border: 1px solid var(--rule);
    border-radius: 8px;
    overflow: hidden;
    background: var(--bg-elevated);
  }

  /* ===== 左侧类型面板（设计稿 tag-groups）===== */
  .tag-groups {
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 12px 9px;
    border-right: 1px solid var(--rule);
    background: var(--bg-surface, var(--bg));
    overflow: auto;
  }
  .side-label {
    padding: 5px 9px 7px;
    color: var(--ink-tertiary);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .tag-group {
    min-height: 35px;
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 0 9px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--ink-secondary);
    font-family: inherit;
    font-size: 12px;
    text-align: left;
    cursor: pointer;
  }
  .tag-group:hover { background: var(--bg-hover); color: var(--ink); }
  .tag-group.active { background: var(--accent-soft); color: var(--accent); }
  .tag-group-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
    flex: 0 0 auto;
  }
  .tag-group-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tag-group-count {
    color: var(--ink-tertiary);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
  }
  .add-type-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 8px;
    padding: 8px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--bg-elevated);
  }
  .add-type-actions { display: flex; gap: 6px; }
  .add-type-input {
    width: 100%;
    height: 30px;
    padding: 0 8px;
    border: 1px solid var(--rule);
    border-radius: 5px;
    background: var(--bg);
    color: var(--ink);
    font-family: inherit;
    font-size: 12px;
    outline: 0;
  }
  .add-type-input:focus { border-color: var(--accent); }

  /* ===== 右侧内容（设计稿 tag-content）===== */
  .tag-content {
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 14px;
    overflow: hidden;
  }
  .tag-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }
  .toolbar-title { font-size: 13px; font-weight: 700; color: var(--ink); }
  .toolbar-meta { color: var(--ink-tertiary); font-size: 12px; }
  .toolbar-spacer { flex: 1; }
  .mini-btn {
    min-height: 28px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: 5px;
    background: var(--bg-elevated);
    color: var(--ink);
    font-family: inherit;
    font-size: 11px;
    cursor: pointer;
  }
  .mini-btn:hover { border-color: var(--accent); color: var(--accent); }
  .mini-btn.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }
  .mini-btn.primary { border-color: var(--accent); background: var(--accent); color: #061812; font-weight: 700; }
  .mini-btn.ghost { background: transparent; }
  .mini-btn:disabled { opacity: 0.45; cursor: default; }
  .mini-btn.primary { border-color: var(--accent); background: var(--accent); color: #061812; font-weight: 700; }
  .mini-btn.ghost { background: transparent; }
  .mini-btn:disabled { opacity: 0.45; cursor: default; }

  /* ===== 左侧类型面板（已移除，类型管理在 Sidebar） ===== */
  .type-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .type-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: left;
  }

  .dot-swatch {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 2px solid transparent;
    cursor: pointer;
    padding: 0;
    transition: transform 150ms;
  }

  .dot-swatch.active {
    border-color: var(--ink);
    transform: scale(1.15);
  }

  /* ===== 搜索输入 ===== */
  .search-input-wrap {
    position: relative;
    display: flex;
    align-items: center;
    flex: 0 1 220px;
  }

  .search-icon {
    position: absolute;
    left: 10px;
    color: var(--muted);
    pointer-events: none;
  }

  .search-input {
    width: 100%;
    height: 32px;
    padding: 0 12px 0 30px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 12.5px;
    font-family: inherit;
    transition: border-color 150ms;
  }

  .search-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .sort-select {
    height: 32px;
    padding: 0 26px 0 10px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 12px;
    font-family: inherit;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236e6e73'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 8px center;
    cursor: pointer;
  }

  .add-tag-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg-soft);
    border-radius: 6px;
  }

  .add-tag-input {
    flex: 1;
    height: 30px;
    padding: 0 10px;
    border: 1px solid var(--accent);
    border-radius: 4px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
  }

  .add-tag-input:focus {
    outline: none;
    box-shadow: 0 0 0 2px var(--accent-soft);
  }

  .mini-btn {
    height: 30px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 12px;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: all 150ms;
    white-space: nowrap;
  }

  .mini-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  .mini-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .mini-btn.ghost {
    background: transparent;
    border-color: transparent;
  }

  .mini-btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .mini-btn.primary:hover:not(:disabled) {
    filter: brightness(1.08);
  }

  /* ---- 卡片区域 ---- */
  .card-area {
    flex: 1;
    min-height: 0;
    padding: 16px 20px;
    overflow-y: auto;
  }

  .card-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 10px;
  }

  .tag-card {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 14px 8px 12px;
    border: 1.5px solid var(--rule);
    border-radius: 8px;
    background: var(--bg2);
    cursor: pointer;
    transition: all 150ms;
    font-family: inherit;
    text-align: center;
  }

  .tag-card:hover {
    border-color: var(--accent-40);
    background: var(--bg-soft);
  }

  .tag-card.selected {
    border: 2px solid var(--accent);
    background: var(--accent-soft);
  }

  .tag-card.renaming {
    cursor: default;
    border-color: var(--accent);
  }

  .selected-badge {
    position: absolute;
    top: -1px;
    right: -1px;
    background: var(--accent);
    color: #fff;
    font-size: 9px;
    font-weight: 600;
    padding: 1px 5px 2px;
    border-radius: 0 6px 0 6px;
    line-height: 1.2;
  }

  .card-name {
    font-size: 13px;
    font-weight: 700;
    color: var(--ink);
    line-height: 1.3;
    word-break: break-word;
    max-width: 100%;
  }

  .card-subtitle {
    font-size: 11px;
    color: var(--muted);
    line-height: 1.2;
  }

  .card-color-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
    opacity: 0.6;
  }

  /* ---- 行内重命名 ---- */
  .rename-input {
    width: 100%;
    height: 26px;
    padding: 0 6px;
    border: 1px solid var(--accent);
    border-radius: 4px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 12px;
    font-family: inherit;
    text-align: center;
  }

  .rename-input:focus {
    outline: none;
    box-shadow: 0 0 0 2px var(--accent-soft);
  }

  .rename-actions {
    display: flex;
    gap: 4px;
  }

  .icon-btn {
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: none;
    color: var(--muted);
    font-size: 13px;
    cursor: pointer;
    transition: all 150ms;
  }

  .icon-btn:hover {
    background: var(--bg-soft);
    color: var(--ink);
  }

  /* ---- 媒体列表 ---- */
  .media-section {
    border-top: 1px solid var(--rule);
    flex-shrink: 0;
    max-height: 320px;
    display: flex;
    flex-direction: column;
  }

  .media-section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 20px;
    border-bottom: 1px solid var(--rule);
    flex-shrink: 0;
  }

  .media-title-head {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
  }

  .media-head-actions {
    display: flex;
    gap: 8px;
  }

  .action-btn {
    height: 28px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
    transition: all 150ms;
  }

  .action-btn:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  .action-btn.danger {
    color: #ff3b30;
    border-color: transparent;
    background: none;
  }

  .action-btn.danger:hover {
    background: rgba(255, 59, 48, 0.08);
    color: #ff3b30;
  }

  .media-list-wrap {
    flex: 1;
    overflow-y: auto;
    padding: 8px 20px 12px;
  }

  .media-items {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .media-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 10px;
    border-radius: 6px;
    transition: background 150ms;
  }

  .media-item:hover {
    background: var(--bg-soft);
  }

  .media-thumb {
    width: 24px;
    height: 24px;
    border-radius: 3px;
    object-fit: cover;
    flex-shrink: 0;
    background: var(--bg-soft);
  }

  .media-thumb.placeholder {
    background: var(--bg-soft);
    border: 1px solid var(--rule);
  }

  .media-title {
    flex: 1;
    font-size: 12.5px;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .media-year {
    font-size: 11.5px;
    color: var(--muted);
    flex-shrink: 0;
  }

  /* ---- 通用状态 ---- */
  .state-msg {
    padding: 40px 0;
    text-align: center;
    font-size: 13px;
    color: var(--muted);
  }

  .state-msg.subtle {
    font-size: 12.5px;
    padding: 24px 0;
  }

  .state-msg.empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }

  .empty-icon {
    font-size: 28px;
    opacity: 0.5;
  }

  .empty-text {
    font-size: 13px;
    color: var(--ink);
    opacity: 0.6;
  }

  .link-btn {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12.5px;
    padding: 4px 8px;
    cursor: pointer;
    transition: opacity 150ms;
    font-family: inherit;
  }

  .link-btn:hover {
    opacity: 0.7;
  }

  /* ---- Toast ---- */
  .toast {
    position: fixed;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 18px;
    border-radius: 20px;
    font-size: 13px;
    z-index: 2000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    color: #fff;
    animation: toast-in 200ms ease;
  }

  .toast.ok {
    background: var(--ok);
  }

  .toast.err {
    background: #ff3b30;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translate(-50%, 10px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  /* ---- 右键菜单 ---- */
  .ctx-menu {
    position: fixed;
    z-index: 3000;
    min-width: 160px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
    padding: 4px;
    animation: ctx-pop 120ms ease;
  }

  @keyframes ctx-pop {
    from { opacity: 0; transform: scale(0.96); }
    to { opacity: 1; transform: scale(1); }
  }

  .ctx-item {
    display: flex;
    align-items: center;
    width: 100%;
    padding: 7px 12px;
    border: none;
    background: none;
    border-radius: 4px;
    color: var(--ink);
    font-size: 12.5px;
    font-family: inherit;
    text-align: left;
    cursor: pointer;
    transition: background 120ms;
  }

  .ctx-item:hover {
    background: var(--bg-soft);
  }

  .ctx-item.danger {
    color: #ff3b30;
  }

  .ctx-item.danger:hover {
    background: rgba(255, 59, 48, 0.1);
  }

  .ctx-section {
    padding: 4px 8px;
  }

  .ctx-label {
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 6px;
    padding: 0 4px;
  }

  .ctx-palette {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 0 4px 2px;
  }

  .ctx-color {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 2px solid transparent;
    cursor: pointer;
    padding: 0;
    transition: transform 120ms;
  }

  .ctx-color:hover {
    transform: scale(1.2);
  }

  .ctx-color.active {
    border-color: var(--ink);
  }

  .ctx-divider {
    height: 1px;
    background: var(--rule);
    margin: 4px 0;
  }

  /* ---- 标签编辑弹窗 ---- */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.32);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2500;
    animation: modal-fade 200ms ease;
  }

  @keyframes modal-fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .edit-modal {
    width: 100%;
    max-width: 360px;
    background: var(--bg2);
    border-radius: 12px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
    padding: 20px 24px;
    animation: modal-pop 200ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  @keyframes modal-pop {
    from { opacity: 0; transform: translateY(-8px) scale(0.96); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .edit-modal-title {
    margin: 0 0 16px;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
  }

  .edit-field {
    margin-bottom: 14px;
  }

  .edit-label {
    display: block;
    margin-bottom: 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
  }

  .edit-input {
    width: 100%;
    height: 34px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 150ms;
  }

  .edit-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .edit-palette {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }

  .none-swatch {
    background: var(--bg-soft) !important;
    border: 2px dashed var(--rule);
    position: relative;
  }

  .none-swatch::after {
    content: '×';
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    color: var(--muted);
  }

  .none-swatch.active {
    border-color: var(--ink);
  }

  .edit-textarea {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    resize: vertical;
    transition: border-color 150ms;
  }

  .edit-textarea:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .edit-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 4px;
  }

  /* ===== 批量操作 ===== */

  .batch-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 20px;
    background: var(--accent-soft);
    border-bottom: 1px solid var(--rule);
    flex-shrink: 0;
    flex-wrap: wrap;
  }

  .batch-count {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--ink);
    white-space: nowrap;
  }

  .batch-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  .batch-btn {
    height: 28px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: 4px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
    transition: all 150ms;
    white-space: nowrap;
  }

  .batch-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  .batch-btn.danger {
    color: #ff3b30;
    border-color: transparent;
    background: none;
  }

  .batch-btn.danger:hover:not(:disabled) {
    background: rgba(255, 59, 48, 0.08);
    color: #ff3b30;
  }

  .batch-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .batch-loading-text {
    font-size: 12px;
    color: var(--accent);
    margin-left: auto;
    white-space: nowrap;
  }

  /* ---- 多选卡片复选框 ---- */
  .tag-card.multi {
    padding-top: 20px;
  }

  .card-checkbox {
    position: absolute;
    top: 6px;
    left: 6px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 1.5px solid var(--rule);
    background: var(--bg2);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1;
    transition: all 150ms;
    pointer-events: none;
  }

  .card-checkbox.checked {
    background: var(--accent);
    border-color: var(--accent);
  }

  /* ---- 批量移动类型列表 ---- */
  .move-type-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 240px;
    overflow-y: auto;
  }

  .move-type-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--bg2);
    color: var(--ink);
    font-size: 12.5px;
    font-family: inherit;
    cursor: pointer;
    transition: all 150ms;
    text-align: left;
  }

  .move-type-item:hover:not(:disabled) {
    border-color: var(--accent);
  }

  .move-type-item.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    font-weight: 600;
  }

  .move-type-item.current {
    opacity: 0.7;
  }

  .move-type-item:disabled {
    cursor: not-allowed;
  }

  .move-type-item .type-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .move-current-tag {
    font-size: 10px;
    color: var(--muted);
    padding: 1px 6px;
    border: 1px solid var(--rule);
    border-radius: 8px;
    flex-shrink: 0;
  }

  .batch-modal-loading {
    margin-top: 8px;
    font-size: 12px;
    color: var(--accent);
  }

  /* ---- 行内操作：添加子标签 / 移动类型（右键菜单触发，tagOps 驱动） ---- */
  .inline-ops-row {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin: 12px 20px;
    padding: 10px 12px;
    border: 1px solid var(--accent-soft);
    border-radius: 6px;
    background: var(--accent-soft);
  }
  .inline-ops-label {
    color: var(--ink-secondary);
    font-size: 12px;
    font-weight: 600;
    white-space: nowrap;
  }
  .inline-ops-input {
    flex: 1;
    min-width: 180px;
    height: 30px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: 5px;
    background: var(--bg-elevated);
    color: var(--ink);
    font-family: inherit;
    font-size: 12px;
    outline: 0;
  }
  .inline-ops-input:focus {
    border-color: var(--accent);
  }
  .inline-ops-types {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .inline-type-option {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: 5px;
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    font-family: inherit;
    font-size: 11px;
    cursor: pointer;
  }
  .inline-type-option:hover,
  .inline-type-option.active {
    border-color: var(--accent);
    color: var(--accent);
  }
</style>
