<script lang="ts">
  // 媒体管理视图 — 管理页 media Tab
  // 工具栏筛选 + 批量操作 + 列表/网格视图 + 分页 + 列宽调整
  // 批量操作统一走 POST /media/batch 后端端点，避免前端 for 循环逐个请求

  import { tick, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page as pageStore } from '$app/stores';
  import { mediaApi, type Media, type MediaSortField, type AIRescrapeResponse, isAvMedia, hasNetworkSource } from '$lib/api/media';
  import { imageFallback } from '$lib/utils/image-fallback';
  import { extractFancode } from '$lib/utils/network-media';
  import { adultNetworkApi } from '$lib/api/networkSources';
  import { librariesApi, type Library, type TreeNode } from '$lib/api/libraries';
  import { flattenTags, type Tag } from '$lib/api/tags';
  import { client } from '$lib/api/client';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { manageFilterStore } from '$lib/stores/manageFilter.svelte';
  import { tasks } from '$lib/stores/tasks.svelte';
  import { formatTime, formatSize, formatResolution } from '$lib/utils/format';
  import TagSelector from '$lib/components/common/TagSelector.svelte';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
  import RatingStars from '$lib/components/common/RatingStars.svelte';
  import NetworkImportDialog from '$lib/components/manage/NetworkImportDialog.svelte';
  import EditMediaDialog from '$lib/components/manage/EditMediaDialog.svelte';
  import DuplicatesDialog from '$lib/components/manage/DuplicatesDialog.svelte';

  // ---- 父组件传入的共享数据（库、标签） ----
  let {
    libraries = [],
    tags = [],
    tagTypes = []
  }: {
    libraries?: Library[];
    tags?: Tag[];
    tagTypes?: { id: number; name: string; color?: string | null; sort_order?: number }[];
  } = $props();

  // ---- 本地筛选/排序/视图状态（独立于 /media） ----
  type StatusFilter = '' | 'rated' | 'unrated' | 'favorite' | 'untagged' | 'problem' | 'missing' | 'unmatched';

  let filterLib = $state('');
  let filterDir = $state('');
  let filterType = $state('');
  let filterTags = $state<string[]>([]);
  let filterStatus = $state<StatusFilter>('');
  let filterSource = $state('');
  let sortField = $state<MediaSortField>('created_at');
  let sortOrder = $state<'asc' | 'desc'>('desc');
  let view = $state<'list' | 'grid'>('list');
  let didRestoreScroll = false;

  let page = $state(1);
  let pageSize = $state(50);

  let items = $state<Media[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let error = $state<string | null>(null);

  let selected = $state<Set<string>>(new Set());

  // 弹窗状态
  let tagSelectorOpen = $state(false);
  let ratingDialogOpen = $state(false);
  let moveLibDialogOpen = $state(false);
  let deleteDialogOpen = $state(false);
  let networkImportOpen = $state(false);
  let duplicatesOpen = $state(false);
  let editDialogOpen = $state(false);
  let editMediaTarget = $state<Media | null>(null);
  let batchRating = $state(0);
  let targetLibraryId = $state('');

  // 批量重命名
  let renameDialogOpen = $state(false);
  let renameTemplate = $state('{title}');
  let renameStartIndex = $state(1);
  let renamePreviews = $state<{ id: number; old_name: string; new_name: string; error: string | null }[]>([]);
  let renamePreviewLoading = $state(false);
  let renameApplying = $state(false);

  // 移动到目录
  let moveDirDialogOpen = $state(false);
  let moveDirLibId = $state('');
  let moveDirTree = $state<TreeNode[]>([]);
  let moveDirTargetPath = $state('');
  let moveDirExpanded = $state<Set<string>>(new Set());
  let moveDirChildren = $state<Map<string, TreeNode[]>>(new Map());
  let moveDirLoading = $state(false);
  let moveDirMoving = $state(false);

  // 操作反馈（带撤销：删除类操作 10 秒内可一键恢复）
  let toast = $state<{ msg: string; type: 'ok' | 'err'; undoIds?: number[] } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  let undoing = $state(false);

  function showToast(msg: string, type: 'ok' | 'err' = 'ok', undoIds?: number[]): void {
    toast = undoIds && undoIds.length > 0 ? { msg, type, undoIds } : { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), undoIds && undoIds.length > 0 ? 10000 : 3000);
  }

  /** 撤销刚移入回收站的媒体（逐个调恢复端点） */
  async function undoDelete(): Promise<void> {
    const ids = toast?.undoIds ?? [];
    if (ids.length === 0 || undoing) return;
    undoing = true;
    let restored = 0;
    let failed = 0;
    for (const id of ids) {
      try {
        await client.post(`/recycle-bin/${id}/restore`);
        restored++;
      } catch {
        failed++;
      }
    }
    undoing = false;
    toast = null;
    if (restored > 0) {
      showToast(`已从回收站恢复 ${restored} 项${failed > 0 ? `，${failed} 项恢复失败` : ''}`, failed > 0 ? 'err' : 'ok');
    } else {
      showToast('恢复失败，请到回收站页手动处理', 'err');
    }
    librariesStore.notifyChanged();
    clearSelection();
    loadMedia();
  }

  // ---- 单项右键菜单 ----
  let itemContextMenu = $state<{ x: number; y: number; media: Media } | null>(null);
  let aiRescrapingId = $state<string | null>(null);

  function onItemContextMenu(e: MouseEvent, media: Media): void {
    e.preventDefault();
    e.stopPropagation();
    itemContextMenu = { x: e.clientX, y: e.clientY, media };
  }

  function closeItemContextMenu(): void {
    itemContextMenu = null;
  }

  // 单项 AI 辅助刮削
  async function itemAiRescrape(media: Media): Promise<void> {
    const mid = media.id;
    closeItemContextMenu();
    aiRescrapingId = mid;
    try {
      const result: AIRescrapeResponse = await mediaApi.aiRescrape(mid);
      if (result.success) {
        showToast(`AI 辅助刮削成功: ${result.matched_title ?? ''}`);
      } else {
        showToast(
          result.suggested_title
            ? `AI 建议「${result.suggested_title}」但 TMDB 未匹配`
            : 'AI 未能生成有效建议',
          'err'
        );
      }
      // 刷新列表以显示最新数据
      loadMedia();
    } catch (e) {
      const status = (e as { status?: number })?.status;
      let msg = 'AI 辅助刮削失败';
      if (status === 400) {
        const detail = (e as { body?: { detail?: string } })?.body?.detail;
        msg = detail || '请检查 AI / TMDB 配置';
      } else if (status === 502) {
        const detail = (e as { body?: { detail?: string } })?.body?.detail;
        msg = detail || 'AI 或 TMDB 调用失败，请检查配置或网络';
      }
      showToast(msg, 'err');
    } finally {
      aiRescrapingId = null;
    }
  }

  // 单项刮削（TMDB）
  async function itemScrape(media: Media): Promise<void> {
    const mid = media.id;
    closeItemContextMenu();
    aiRescrapingId = mid;
    try {
      await mediaApi.scrape(mid);
      showToast('刮削完成');
      loadMedia();
    } catch (e) {
      const status = (e as { status?: number })?.status;
      let msg = '刮削失败';
      if (status === 400) msg = '请先配置 TMDB API Key';
      else if (status === 404) msg = '未在 TMDB 匹配到对应作品';
      else if (status === 502) msg = 'TMDB 接口请求失败';
      showToast(msg, 'err');
    } finally {
      aiRescrapingId = null;
    }
  }

  // 单项缩略图集生成（4×4 16 帧，手动触发）
  let sheetingId = $state<string | null>(null);

  async function itemContactSheet(media: Media): Promise<void> {
    const mid = media.id;
    closeItemContextMenu();
    sheetingId = mid;
    try {
      await mediaApi.generateContactSheet(mid);
      showToast('缩略图集已生成（可在详情页查看）');
    } catch (e) {
      const detail = (e as { body?: { detail?: string } })?.body?.detail;
      showToast(detail || '缩略图集生成失败', 'err');
    } finally {
      sheetingId = null;
    }
  }

  // 文件丢失 → 转为网络视频：先确保有可播放的网络源（有番号优先聚合解析），
  // 再调用后端 convert-to-network 完成状态转换（OFFLINE → NETWORK，清除 file_missing）。
  let convertingNetId = $state<string | null>(null);

  async function itemConvertToNetwork(media: Media): Promise<void> {
    const mid = media.id;
    closeItemContextMenu();
    if (convertingNetId) return;
    // 1. 确保有源：无源且标题含番号 → 先聚合解析补源
    if (!hasNetworkSource(media)) {
      const fc = extractFancode(media.title || media.filename || '');
      if (fc) {
        convertingNetId = mid;
        try {
          const res = await adultNetworkApi.refresh(mid, fc);
          if (res.refresh && res.refresh.status !== 'ok') {
            showToast(res.refresh.message || '解析失败，请稍后再试', 'err');
            return;
          }
        } catch (e) {
          const status = (e as { status?: number })?.status;
          const detail = (e as { body?: { detail?: string } })?.body?.detail;
          if (status === 403) showToast(detail || '成人网络源功能未开启（设置 → 内容管理）', 'err');
          else showToast(detail || '解析失败', 'err');
          return;
        } finally {
          convertingNetId = null;
        }
        await loadMedia();
        const fresh = items.find((m) => m.id === mid);
        if (!fresh || !hasNetworkSource(fresh)) {
          showToast('解析未获得可用源，请先手动添加源链接', 'err');
          return;
        }
      } else {
        showToast('暂无网络源：请先在详情页通过「添加链接」添加源链接', 'err');
        return;
      }
    }
    // 2. 转换
    convertingNetId = mid;
    try {
      await mediaApi.convertToNetwork(mid);
      showToast('已转为网络视频');
      loadMedia();
    } catch (e) {
      const detail = (e as { body?: { detail?: string } })?.body?.detail;
      showToast(detail || '转为网络视频失败', 'err');
    } finally {
      convertingNetId = null;
    }
  }

  // 点击外部关闭右键菜单
  function onItemMenuWindowClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    if (itemContextMenu && !target.closest('.item-ctx-menu')) {
      itemContextMenu = null;
    }
  }

  $effect(() => {
    if (itemContextMenu) {
      window.addEventListener('click', onItemMenuWindowClick);
      return () => window.removeEventListener('click', onItemMenuWindowClick);
    }
  });

  // 从 URL 同步 lib、dir、source、status 筛选（侧边栏目录树点击 / 仪表盘卡片跳转触发）
  // 修复：只在 URL 参数【实际变化】时同步一次（记住上次 URL 快照）。否则用户手动
  // 点状态/来源筛选时（URL 无对应参数），本 effect 会用空串把用户选择覆盖掉，
  // 导致"状态过滤完全失效"。
  // 首次挂载（lastUrlFilterParams === null）：URL 显式参数优先（外部入口），
  // 其余筛选（类型/标签/排序/分页等）从 manageFilterStore 恢复——详情页返回时
  // 组件重建，筛选不再丢失。
  let lastUrlFilterParams: string | null = null;
  $effect(() => {
    const url = $pageStore.url;
    const urlKey = [
      url.searchParams.get('lib') ?? '',
      url.searchParams.get('dir') ?? '',
      url.searchParams.get('source') ?? '',
      url.searchParams.get('status') ?? '',
    ].join('|');
    if (lastUrlFilterParams === urlKey) return;
    const firstRun = lastUrlFilterParams === null;
    lastUrlFilterParams = urlKey;
    if (firstRun) {
      const prev = manageFilterStore.state;
      // 默认库：URL 参数 → 会话 store → 第一个资源库。
      // 从媒体中心/外部入口进入批量治理时，URL 通常不带 lib，此时应默认选中
      // 第一个库作为过滤项，而不是"全部库"（用户预期进入即带当前库上下文）。
      // 来源筛选（local/network/missing）是跨库视角：带 source 参数进入时不默认选第一个库，
      // 否则会把它库的匹配项过滤掉（如"文件丢失"只分布在某几个库），导致右侧列表为空，
      // 与侧边栏/问题中心的全局计数不一致。仅无 source 才回落到会话 store 或默认库。
      const hasSourceParam = url.searchParams.has('source');
      filterLib = url.searchParams.get('lib')
        || (!hasSourceParam ? (prev.filterLib || (libraries.length > 0 ? libraries[0].id : '')) : '');
      filterDir = url.searchParams.get('dir') || prev.filterDir;
      filterSource = url.searchParams.get('source') || prev.filterSource;
      filterStatus = (url.searchParams.get('status') || prev.filterStatus) as StatusFilter;
      filterType = prev.filterType;
      filterTags = [...prev.filterTags];
      filterTagType = prev.filterTagType;
      sortField = prev.sortField;
      sortOrder = prev.sortOrder;
      view = prev.view;
      page = prev.page;
      pageSize = prev.pageSize;
    } else {
      filterLib = url.searchParams.get('lib') || '';
      filterDir = url.searchParams.get('dir') || '';
      filterSource = url.searchParams.get('source') || '';
      filterStatus = (url.searchParams.get('status') || '') as StatusFilter;
    }
    untrack(() => loadMedia());
  });

  // 持久化筛选/排序/分页/视图到会话 store（进入详情返回管理页时恢复）
  $effect(() => {
    manageFilterStore.save({
      filterLib,
      filterDir,
      filterType,
      filterTags: [...filterTags],
      filterTagType,
      filterStatus,
      filterSource,
      sortField,
      sortOrder,
      view,
      page,
      pageSize,
    });
  });

  // 资源库加载完成兜底：首次挂载时 libraries 可能尚未就绪，且 URL/store 都未
  // 指定库（从媒体中心/外部入口进入批量治理），补设第一个库为默认过滤项。
  // 仅当用户从未显式选择过库（filterLib 仍为空且未点过库下拉）时生效；
  // 用户显式选"全部库"后 filterLib 会被设为 ''，但通过 URL 同步 effect 的
  // lastUrlFilterParams 已更新，不会在此被覆盖（本 effect 只在 didDefaultLib
  // 首次置位时补一次，之后不再干预）。
  let didDefaultLib = false;
  let userPickedLib = false;
  $effect(() => {
    if (didDefaultLib) return;
    if (libraries.length === 0) return;
    if (!userPickedLib && filterLib === '' && filterSource === '') {
      filterLib = libraries[0].id;
    }
    didDefaultLib = true;
  });

  function onContentScroll(e: Event): void {
    manageFilterStore.save({ scrollTop: (e.currentTarget as HTMLElement).scrollTop });
  }

  // ---- 派生 ----
  const libraryMap = $derived(
    Object.fromEntries(libraries.map((l) => [l.id, l.name]))
  );

  // tags prop 现在传原始树（含 children 层级）；扁平列表用于批量打标等场景
  const flatTags = $derived(flattenTags(tags));

  const tagMap = $derived(
    Object.fromEntries(flatTags.map((t) => [t.id, t.name]))
  );

  const selectedCount = $derived(selected.size);
  const allOnPageSelected = $derived(
    items.length > 0 && items.every((m) => selected.has(m.id))
  );
  const someOnPageSelected = $derived(
    items.some((m) => selected.has(m.id)) && !allOnPageSelected
  );

  const totalPages = $derived(Math.max(1, Math.ceil(total / pageSize)));

  // 用于批量打标时显示当前已有标签
  const selectedItems = $derived(items.filter((m) => selected.has(m.id)));

  // ---- 筛选下拉 ----
  let openMenu = $state<string | null>(null);

  function toggleMenu(name: string): void {
    openMenu = openMenu === name ? null : name;
  }

  // ---- 下拉键盘导航：chip ↑/Enter 打开聚焦首项，菜单内 ↑↓ 移动 / Enter 选择 / Esc 关闭 ----
  let menuActiveIdx = $state(-1);

  function focusFirstMenuItem(name: string): void {
    requestAnimationFrame(() => {
      const first = document.querySelector<HTMLElement>(
        `.chip-wrap[data-menu="${name}"] .menu-item`
      );
      if (first) {
        first.focus();
        menuActiveIdx = 0;
      }
    });
  }

  function onChipKeydown(e: KeyboardEvent, name: string): void {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (openMenu !== name) toggleMenu(name);
      focusFirstMenuItem(name);
    } else if (e.key === 'Escape') {
      closeMenus();
    }
  }

  function onMenuKeydown(e: KeyboardEvent): void {
    const menu = e.currentTarget as HTMLElement;
    const opts = Array.from(menu.querySelectorAll<HTMLElement>('.menu-item'));
    if (opts.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      menuActiveIdx = (menuActiveIdx + 1) % opts.length;
      opts[menuActiveIdx]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      menuActiveIdx = (menuActiveIdx - 1 + opts.length) % opts.length;
      opts[menuActiveIdx]?.focus();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (menuActiveIdx >= 0 && menuActiveIdx < opts.length) opts[menuActiveIdx].click();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeMenus();
    }
  }

  function closeMenus(): void {
    openMenu = null;
  }

  function onWindowClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    if (!target.closest('.chip-wrap')) closeMenus();
  }

  $effect(() => {
    if (openMenu) {
      window.addEventListener('click', onWindowClick);
      return () => window.removeEventListener('click', onWindowClick);
    }
  });

  // 标签筛选下拉菜单中复选状态切换（保持打开以便多选）
  function toggleFilterTag(id: string): void {
    filterTags = filterTags.includes(id)
      ? filterTags.filter((t) => t !== id)
      : [...filterTags, id];
  }

  // ---- 标签树形展开 + 分类筛选 ----
  let filterTagType = $state<number | ''>('');
  let expandedTags = $state<Set<string>>(new Set());
  let tagTreeTouched = $state(false);

  // 首次加载时默认展开所有含子节点的标签；用户手动折叠后不再自动展开
  $effect(() => {
    if (tags.length === 0 || tagTreeTouched) return;
    const withKids = new Set<string>();
    const walk = (ns: Tag[]) => {
      for (const n of ns) {
        if (n.children?.length) {
          withKids.add(n.id);
          walk(n.children);
        }
      }
    };
    walk(tags);
    expandedTags = withKids;
  });

  function toggleExpandTag(id: string): void {
    tagTreeTouched = true;
    const next = new Set(expandedTags);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    expandedTags = next;
  }

  function pickTagTypeFilter(typeId: number | ''): void {
    filterTagType = filterTagType === typeId ? '' : typeId;
  }

  // 按分类过滤标签树：匹配分类的节点整棵保留；不匹配但子节点匹配的，子节点提升为根
  function filterTreeByType(nodes: Tag[], typeId: number): Tag[] {
    const out: Tag[] = [];
    for (const n of nodes) {
      if (n.tag_type_id === typeId) {
        out.push(n);
      } else if (n.children?.length) {
        const kids = filterTreeByType(n.children, typeId);
        if (kids.length) out.push(...kids);
      }
    }
    return out;
  }

  const visibleTagRoots = $derived.by(() => {
    if (filterTagType === '') return tags;
    return filterTreeByType(tags, filterTagType);
  });

  const statusOptions: { value: StatusFilter; label: string }[] = [
    { value: '', label: '全部状态' },
    { value: 'problem', label: '存在问题' },
    { value: 'missing', label: '文件缺失' },
    { value: 'unmatched', label: '待处理' },
    { value: 'rated', label: '已评分' },
    { value: 'unrated', label: '未评分' },
    { value: 'favorite', label: '收藏' },
    { value: 'untagged', label: '无标签' }
  ];

  const sortOptions: { value: MediaSortField; label: string }[] = [
    { value: 'created_at', label: '添加时间' },
    { value: 'filename', label: '标题' },
    { value: 'size', label: '大小' },
    { value: 'duration', label: '时长' },
    { value: 'rating', label: '评分' }
  ];

  const typeOptions: { value: string; label: string }[] = [
    { value: '', label: '全部类型' },
    { value: 'video', label: '视频' },
    { value: 'audio', label: '音频' },
    { value: 'image', label: '图片' }
  ];

  // ---- 构建请求参数 ----
  function buildParams(): Record<string, unknown> {
    const p: Record<string, unknown> = {
      sort: sortField,
      order: sortOrder,
      page,
      page_size: pageSize
    };
    if (filterLib) p.library_id = filterLib;
    if (filterDir) p.dir = filterDir;
    if (filterType) p.type = filterType;
    if (filterTags.length) p.tags = filterTags;
    if (filterStatus === 'favorite') p.favorite = true;
    if (filterStatus === 'rated') p.rating_min = 1;
    if (filterStatus === 'unrated') p.rating_max = 0;
    // 文件缺失走后端精确参数；problem / unmatched 由客户端二次过滤
    if (filterStatus === 'missing') p.file_missing = true;
    // 来源筛选：local / network 走 source 参数；missing 走 file_missing
    if (filterSource === 'local') p.source = 'local';
    if (filterSource === 'network') p.source = 'network';
    if (filterSource === 'missing') p.file_missing = true;
    return p;
  }

  // 客户端二次过滤（untagged / problem / unmatched 等无法精确表达的状态）
  function applyClientFilters(list: Media[]): Media[] {
    if (filterStatus === 'untagged') {
      return list.filter((m) => !m.tags || m.tags.length === 0);
    }
    if (filterStatus === 'problem') {
      return list.filter((m) => m.file_missing || !m.poster || !m.scrape_data);
    }
    if (filterStatus === 'unmatched') {
      return list.filter((m) => !m.poster && !m.scrape_data);
    }
    return list;
  }

  async function restoreScrollPosition(): Promise<void> {
    if (didRestoreScroll) return;
    didRestoreScroll = true;
    const top = manageFilterStore.state.scrollTop;
    if (top <= 0) return;
    await tick();
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = document.querySelector<HTMLElement>('.manage-content');
        if (el) el.scrollTop = top;
      });
    });
  }

  // ---- 加载数据 ----
  let reqId = 0;

  async function loadMedia(): Promise<void> {
    const myId = ++reqId;
    loading = true;
    error = null;
    try {
      const params = buildParams();
      // 客户端过滤时拉取更多数据（后端 page_size 上限 200）
      if (filterStatus === 'untagged' || filterStatus === 'problem' || filterStatus === 'unmatched') {
        params.page = 1;
        params.page_size = 200;
      }
      const res = await mediaApi.list(params as Parameters<typeof mediaApi.list>[0]);
      if (myId !== reqId) return;
      items = applyClientFilters(res.items ?? []);
      total = filterStatus === 'untagged' || filterStatus === 'problem' || filterStatus === 'unmatched' ? items.length : res.total ?? 0;
      void restoreScrollPosition();
    } catch (e) {
      if (myId !== reqId) return;
      error = '加载媒体失败，请检查后端服务是否运行';
      items = [];
      total = 0;
    } finally {
      if (myId === reqId) loading = false;
    }
  }

  // 数据加载由上方"首次 URL effect"负责（URL 优先 + store 恢复后统一 load），
  // 避免挂载时先按默认筛选发一次无效请求再被覆盖。

  // 限制内容开关变化时重新加载媒体数据
  let prevRestrictedManage: boolean | null = null;
  $effect(() => {
    const current = settingsStore.showRestricted;
    if (prevRestrictedManage !== null && prevRestrictedManage !== current) {
      loadMedia();
    }
    prevRestrictedManage = current;
  });

  // 响应式加载：筛选/排序/分页变化时重新加载
  // 用 untrack 包裹 loadMedia，避免其同步部分读写的 $state 被追踪为本 effect 依赖。
  let lastSig = '';
  let lastFilterSigCache = '';
  let lastRev = librariesStore.revision;
  $effect(() => {
    const f = { lib: filterLib, type: filterType, tags: filterTags, status: filterStatus, source: filterSource };
    const s = { field: sortField, order: sortOrder };
    const p = page;
    const ps = pageSize;
    // 追踪侧边栏数据版本：打标/删除标签等操作(tagOps→reload)后立即刷新列表
    const rev = librariesStore.revision;
    if (rev !== lastRev) {
      lastRev = rev;
      untrack(() => loadMedia());
      return;
    }
    const sig = JSON.stringify({ f, s, p, ps });
    if (sig !== lastSig) {
      lastSig = sig;
      // 筛选/排序变化时重置到第 1 页
      const filterSig = JSON.stringify({ f, s });
      const lastFilterSig = lastFilterSigCache;
      lastFilterSigCache = filterSig;
      if (filterSig !== lastFilterSig && p !== 1) {
        page = 1;
        return;
      }
      untrack(() => loadMedia());
    }
  });

  // ---- 选择 ----
  function toggleSelect(id: string): void {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
  }

  function toggleSelectAll(): void {
    if (allOnPageSelected) {
      const next = new Set(selected);
      for (const m of items) next.delete(m.id);
      selected = next;
    } else {
      const next = new Set(selected);
      for (const m of items) next.add(m.id);
      selected = next;
    }
  }

  function clearSelection(): void {
    selected = new Set();
  }

  // ---- 行交互 ----
  function onRowClick(e: MouseEvent, media: Media): void {
    // 点击复选框/按钮时不跳转
    const target = e.target as HTMLElement;
    if (target.closest('.checkbox-cell') || target.closest('button')) return;
    const scrollEl = document.querySelector<HTMLElement>('.manage-content');
    if (scrollEl) manageFilterStore.save({ scrollTop: scrollEl.scrollTop });
    goto(`/detail/${media.id}`);
  }

  // ---- 批量操作（统一走 POST /media/batch 后端端点） ----
  // 后端响应结构
  interface BatchResponse {
    action: string;
    total: number;
    success_count: number;
    failed: { id: number; error: string }[];
    task_id: number | null;
    export_url: string | null;
    message: string;
  }

  // 选中媒体的数字 ID 列表（后端要求 media_ids: list[int]）
  function selectedNumericIds(): number[] {
    return selectedItems.map((m) => Number(m.id)).filter((n) => !isNaN(n));
  }

  // 批量打标：对选中媒体追加标签（后端自动跳过已存在的标签）
  async function batchAddTags(tagIds: string[]): Promise<void> {
    if (tagIds.length === 0) return;
    tagSelectorOpen = false;
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;
    const numericTagIds = tagIds.map((id) => Number(id)).filter((n) => !isNaN(n));
    try {
      const resp = await client.post<BatchResponse>('/media/batch', {
        action: 'tag',
        media_ids: mediaIds,
        params: { tag_ids: numericTagIds }
      });
      const fail = resp.failed.length;
      showToast(
        `已为 ${resp.success_count} 项媒体添加标签${fail ? `，${fail} 项失败` : ''}`,
        fail ? 'err' : 'ok'
      );
    } catch {
      showToast('批量打标失败', 'err');
    }
    clearSelection();
    loadMedia();
  }

  // 批量评分
  async function batchSetRating(rating: number): Promise<void> {
    ratingDialogOpen = false;
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;
    try {
      const resp = await client.post<BatchResponse>('/media/batch', {
        action: 'rating',
        media_ids: mediaIds,
        params: { rating }
      });
      const fail = resp.failed.length;
      showToast(
        `已为 ${resp.success_count} 项媒体设置评分${fail ? `，${fail} 项失败` : ''}`,
        fail ? 'err' : 'ok'
      );
    } catch {
      showToast('批量评分失败', 'err');
    }
    clearSelection();
    loadMedia();
  }

  // 批量刮削（TMDB）— 后端异步创建任务并返回 task_id
  let batchScraping = $state(false);
  async function batchScrape(): Promise<void> {
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;
    batchScraping = true;
    try {
      const resp = await client.post<BatchResponse>('/media/batch', {
        action: 'scrape',
        media_ids: mediaIds,
        params: {}
      });
      if (resp.task_id != null) {
        showToast(`已创建刮削任务，共 ${resp.total} 项媒体待处理`);
        void tasks.refresh(); // 立即更新顶栏任务徽标
      } else {
        const fail = resp.failed.length;
        showToast(
          `刮削完成：${resp.success_count} 项成功${fail ? `，${fail} 项失败` : ''}`,
          fail ? 'err' : 'ok'
        );
      }
    } catch {
      showToast('批量刮削失败', 'err');
    }
    batchScraping = false;
    clearSelection();
    loadMedia();
  }

  // 批量生成缩略图集（4×4 16 帧）— 后端异步任务
  let batchSheeting = $state(false);
  async function batchContactSheet(): Promise<void> {
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;
    batchSheeting = true;
    try {
      const resp = await client.post<BatchResponse>('/media/batch', {
        action: 'contact_sheet',
        media_ids: mediaIds,
        params: {}
      });
      if (resp.task_id != null) {
        showToast(`已创建缩略图集任务，共 ${resp.total} 项媒体待处理`);
        void tasks.refresh(); // 立即更新顶栏任务徽标
      } else {
        const fail = resp.failed.length;
        showToast(
          `缩略图集生成完成：${resp.success_count} 项成功${fail ? `，${fail} 项失败` : ''}`,
          fail ? 'err' : 'ok'
        );
      }
    } catch {
      showToast('批量生成缩略图集失败', 'err');
    }
    batchSheeting = false;
    clearSelection();
    loadMedia();
  }

  // 移动到库
  async function batchMoveLibrary(): Promise<void> {
    if (!targetLibraryId) return;
    moveLibDialogOpen = false;
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;
    try {
      const resp = await client.post<BatchResponse>('/media/batch', {
        action: 'move',
        media_ids: mediaIds,
        params: { target_library_id: Number(targetLibraryId) }
      });
      const fail = resp.failed.length;
      showToast(
        `已移动 ${resp.success_count} 项媒体${fail ? `，${fail} 项失败` : ''}`,
        fail ? 'err' : 'ok'
      );
    } catch {
      showToast('批量移动失败', 'err');
    }
    targetLibraryId = '';
    clearSelection();
    loadMedia();
  }

  // 单条"删除"（右键）→ 软删除进回收站，磁盘文件不动，
  // 回收站二次确认时可选「仅删除本地文件」或「彻底删除」。
  // 对 file_missing 记录同样可用（删除记录本身）。
  async function recycleLocalFile(m: Media): Promise<void> {
    try {
      await mediaApi.delete(String(m.id));
      librariesStore.notifyChanged(); // 立即触发可见列表刷新（revision 变化）
      showToast('已移入回收站（磁盘文件未删除，可到回收站二次确认）');
    } catch {
      showToast('移入回收站失败', 'err');
    }
    loadMedia();
  }

  // 批量删除（走回收站，软删除）
  async function batchDelete(): Promise<void> {
    deleteDialogOpen = false;
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;
    try {
      const resp = await client.post<BatchResponse>('/media/batch', {
        action: 'delete',
        media_ids: mediaIds,
        params: { permanent: false }
      });
      const fail = resp.failed.length;
      const failedIds = new Set(resp.failed.map((f) => f.id));
      const undoIds = mediaIds.filter((id) => !failedIds.has(id));
      librariesStore.notifyChanged(); // 立即触发可见列表刷新
      showToast(
        `已移入回收站 ${resp.success_count} 项（磁盘文件未删除）${fail ? `，${fail} 项失败` : ''}`,
        fail ? 'err' : 'ok',
        undoIds
      );
    } catch {
      showToast('批量删除失败', 'err');
    }
    clearSelection();
    loadMedia();
  }

  // 导出选中项元数据（客户端组装，保留更丰富的字段）
  function batchExport(): void {
    const data = selectedItems.map((m) => ({
      id: m.id,
      filename: m.filename,
      type: m.type,
      library: libraryMap[m.library_id] ?? m.library_id,
      path: m.path,
      size: m.size,
      duration: m.duration,
      width: m.width,
      height: m.height,
      rating: m.rating,
      favorite: m.favorite,
      tags: (m.tags ?? []).map((id) => tagMap[id] ?? id),
      created_at: m.created_at,
      updated_at: m.updated_at
    }));
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vitoice-export-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast(`已导出 ${data.length} 项媒体元数据`);
  }

  // ---- 批量重命名 ----
  let renameAutoSuffix = $state(true);

  async function generateRenamePreview(): Promise<void> {
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;
    renamePreviewLoading = true;
    renamePreviews = [];
    try {
      const resp = await client.post<{ previews: { id: number; old_name: string; new_name: string; error: string | null }[] }>(
        '/media/batch/rename-preview',
        {
          action: 'rename',
          media_ids: mediaIds,
          params: { template: renameTemplate, start_index: renameStartIndex, auto_suffix: renameAutoSuffix },
        }
      );
      renamePreviews = resp.previews;
    } catch (e: any) {
      const detail = e?.body?.detail ?? e?.message ?? '预览失败';
      showToast(detail, 'err');
    } finally {
      renamePreviewLoading = false;
    }
  }

  async function batchRenameApply(): Promise<void> {
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;
    // Check for errors in preview
    const errorCount = renamePreviews.filter((p) => p.error).length;
    if (errorCount > 0) {
      showToast(`预览中有 ${errorCount} 项错误，请先修复`, 'err');
      return;
    }
    renameApplying = true;
    try {
      const resp = await client.post<BatchResponse>('/media/batch', {
        action: 'rename',
        media_ids: mediaIds,
        params: { template: renameTemplate, start_index: renameStartIndex, auto_suffix: renameAutoSuffix },
      });
      const fail = resp.failed.length;
      showToast(
        `已重命名 ${resp.success_count} 项媒体${fail ? `，${fail} 项失败` : ''}`,
        fail ? 'err' : 'ok'
      );
      renameDialogOpen = false;
    } catch (e: any) {
      const detail = e?.body?.detail ?? e?.message ?? '重命名失败';
      showToast(detail, 'err');
    } finally {
      renameApplying = false;
    }
    clearSelection();
    loadMedia();
  }

  function openRenameDialog(): void {
    renameTemplate = '{title}';
    renameStartIndex = 1;
    renameAutoSuffix = true;
    renamePreviews = [];
    renameDialogOpen = true;
  }

  // 模板变量列表（用于提示）
  const renameTemplateVars = [
    { token: '{title}', desc: '标题' },
    { token: '{year}', desc: '年份' },
    { token: '{filename}', desc: '原文件名(无扩展名)' },
    { token: '{index}', desc: '序号' },
    { token: '{index:2}', desc: '序号(2位补零)' },
    { token: '{library}', desc: '库名' },
    { token: '{rating}', desc: '评分' },
    { token: '{date}', desc: '当前日期' },
  ];

  // ---- 移动到目录 ----
  // 扁平化目录树（仅目录），用于对话框中渲染
  const moveDirFlatTree = $derived.by(() => {
    const result: { node: TreeNode; depth: number; expanded: boolean }[] = [];
    const walk = (nodes: TreeNode[], depth: number) => {
      for (const node of nodes) {
        if (node.node_type !== 'directory') continue;
        const expanded = moveDirExpanded.has(node.rel_path);
        result.push({ node, depth, expanded });
        if (expanded) {
          const children = moveDirChildren.get(node.rel_path);
          if (children) walk(children, depth + 1);
        }
      }
    };
    walk(moveDirTree, 0);
    return result;
  });

  function openMoveDirDialog(): void {
    // 默认使用当前筛选库或第一个选中项的库
    moveDirLibId = filterLib || selectedItems[0]?.library_id || '';
    moveDirTargetPath = '';
    moveDirTree = [];
    moveDirExpanded = new Set();
    moveDirChildren = new Map();
    moveDirDialogOpen = true;
    if (moveDirLibId) loadMoveDirTree(moveDirLibId);
  }

  async function loadMoveDirTree(libId: string): Promise<void> {
    moveDirLoading = true;
    moveDirTargetPath = '';
    moveDirExpanded = new Set();
    moveDirChildren = new Map();
    try {
      const nodes = await librariesApi.tree(libId, '');
      moveDirTree = nodes.filter((n) => n.node_type === 'directory');
    } catch {
      showToast('加载目录失败', 'err');
      moveDirTree = [];
    } finally {
      moveDirLoading = false;
    }
  }

  async function toggleMoveDirExpand(relPath: string): Promise<void> {
    const next = new Set(moveDirExpanded);
    if (next.has(relPath)) {
      next.delete(relPath);
    } else {
      next.add(relPath);
      if (!moveDirChildren.has(relPath)) {
        try {
          const nodes = await librariesApi.tree(moveDirLibId, relPath);
          moveDirChildren = new Map(moveDirChildren).set(
            relPath,
            nodes.filter((n) => n.node_type === 'directory')
          );
        } catch {
          // 静默失败
        }
      }
    }
    moveDirExpanded = next;
  }

  async function batchMoveDirectory(): Promise<void> {
    if (!moveDirLibId) return;
    const mediaIds = selectedNumericIds();
    if (mediaIds.length === 0) return;

    // 确定源库 ID：取选中项中第一个的 library_id
    const sourceLibId = selectedItems[0]?.library_id ?? moveDirLibId;

    moveDirMoving = true;
    try {
      await librariesApi.moveFiles(
        sourceLibId,
        mediaIds.map(String),
        moveDirLibId,
        moveDirTargetPath
      );
      showToast(`已移动 ${mediaIds.length} 项媒体到指定目录`);
      moveDirDialogOpen = false;
    } catch (e: any) {
      const detail = e?.body?.detail ?? e?.message ?? '移动失败';
      showToast(detail, 'err');
    } finally {
      moveDirMoving = false;
    }
    clearSelection();
    loadMedia();
  }

  // 分页
  function gotoPage(p: number | string): void {
    const n = typeof p === 'string' ? parseInt(p, 10) : p;
    if (isNaN(n) || n < 1 || n > totalPages || n === page) return;
    page = n;
    document.querySelector('.manage-content')?.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function onPageSizeChange(e: Event): void {
    pageSize = Number((e.target as HTMLSelectElement).value);
    page = 1;
  }

  function pageList(current: number, tp: number, maxVisible: number): (number | string)[] {
    if (tp <= maxVisible) return Array.from({ length: tp }, (_, i) => i + 1);
    const pages: (number | string)[] = [1];
    // 当前页左右窗口:总窗口 = 首尾各1 + 当前页1 + 左右 half*2
    const half = Math.max(1, Math.floor((maxVisible - 3) / 2));
    let left = Math.max(2, current - half);
    let right = Math.min(tp - 1, current + half);
    // 窗口靠近边缘时向另一侧扩展,保持窗口饱满
    if (right - left + 1 < maxVisible - 2) {
      const slack = maxVisible - 2 - (right - left + 1);
      if (left === 2) right = Math.min(tp - 1, right + slack);
      else if (right === tp - 1) left = Math.max(2, left - slack);
    }
    if (left > 2) pages.push('…');
    for (let i = left; i <= right; i++) pages.push(i);
    if (right < tp - 1) pages.push('…');
    pages.push(tp);
    return pages;
  }

  // ---- 自适应可见页数 ----
  // 分页区空间充足时默认展示最多 15 个页码;窗口变窄时按实际宽度缩减
  // (最小 5 个,保证导航可用)。用 ResizeObserver 监听容器宽度实时重算。
  let pagerEl = $state<HTMLElement | null>(null);
  let pagerWidth = $state(0);

  // 估算常量(px):页码按钮+间距、前后导航、省略号、右侧"每页+总数"区、容器 padding/gap
  const PG_BTN_W = 36;
  const PG_NAV_W = 64; // 上一页+下一页
  const PG_ELLIPSIS_W = 32; // 两个省略号
  const PG_RIGHT_W = 190; // 右侧每页下拉区(管理页含"共 N 项"文本,比 media 页宽)
  const PG_PADDING = 68; // padding + gap

  const maxVisiblePages = $derived(
    pagerWidth === 0
      ? 15 // 首次渲染未测量时按宽屏处理
      : Math.max(
          5,
          Math.min(15, Math.floor((pagerWidth - PG_PADDING - PG_RIGHT_W - PG_NAV_W - PG_ELLIPSIS_W) / PG_BTN_W))
        )
  );

  $effect(() => {
    const el = pagerEl;
    if (!el) return;
    const measure = () => {
      pagerWidth = el.clientWidth;
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  });

  // 排序切换
  function pickSort(field: MediaSortField): void {
    if (sortField === field) {
      sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      sortField = field;
      sortOrder = 'desc';
    }
    closeMenus();
  }

  function pickType(value: string): void {
    filterType = value;
    closeMenus();
  }
  function pickLib(value: string): void {
    userPickedLib = true;
    filterLib = value;
    filterDir = '';  // 切换库时清除目录筛选
    closeMenus();
    // 同步 URL：侧边栏高亮和书签共享需要 URL 反映当前状态
    goto(`/manage?tab=media${value ? `&lib=${value}` : ''}`, { replaceState: true });
  }
  function pickStatus(value: StatusFilter): void {
    filterStatus = value;
    closeMenus();
  }

  // 面包屑导航：拆分当前目录路径为可点击的层级段
  const dirSegments = $derived.by(() => {
    if (!filterDir) return [];
    // 兼容 Windows 反斜杠和正斜杠
    const parts = filterDir.split(/[/\\]/).filter(Boolean);
    const segs: { label: string; path: string }[] = [];
    let acc = '';
    for (const p of parts) {
      acc = acc ? `${acc}\\${p}` : p;
      segs.push({ label: p, path: acc });
    }
    return segs;
  });

  function navigateToDir(path: string): void {
    // 面包屑点击：跳转到对应目录层级
    if (path) {
      goto(`/manage?tab=media&lib=${filterLib}&dir=${encodeURIComponent(path)}`, { replaceState: true });
    } else {
      // 点击库根目录
      goto(`/manage?tab=media&lib=${filterLib}`, { replaceState: true });
    }
  }

  // 标签下拉显示文本
  const libLabel = $derived(
    filterLib ? libraryMap[filterLib] ?? '库' : '库'
  );
  const typeLabel = $derived(
    typeOptions.find((o) => o.value === filterType)?.label ?? '类型'
  );
  const tagLabel = $derived.by(() => {
    // 直接展示已选标签名（最多 2 个 + 剩余数量），让用户一眼看清选了哪些
    const names = filterTags
      .map((id) => tagMap[id])
      .filter((n): n is string => !!n);
    const nameStr = names.length
      ? names.slice(0, 2).join('、') + (names.length > 2 ? ` +${names.length - 2}` : '')
      : '';
    if (filterTags.length > 0 && filterTagType !== '') {
      const tt = tagTypes.find((x) => x.id === filterTagType);
      return nameStr ? `${nameStr} · ${tt?.name ?? '分类'}` : `标签 · ${tt?.name ?? '分类'}`;
    }
    if (filterTags.length > 0) return nameStr ? `标签: ${nameStr}` : '标签';
    if (filterTagType !== '') {
      const tt = tagTypes.find((x) => x.id === filterTagType);
      return `分类 · ${tt?.name ?? ''}`;
    }
    return '标签';
  });
  const statusLabel = $derived(
    statusOptions.find((o) => o.value === filterStatus)?.label ?? '状态'
  );
  const sortLabel = $derived(
    `${sortOptions.find((o) => o.value === sortField)?.label ?? '排序'} ${sortOrder === 'asc' ? '↑' : '↓'}`
  );

  const activeFilterCount = $derived(
    (filterLib ? 1 : 0) +
      (filterDir ? 1 : 0) +
      (filterType ? 1 : 0) +
      filterTags.length +
      (filterTagType !== '' ? 1 : 0) +
      (filterStatus ? 1 : 0) +
      (filterSource ? 1 : 0)
  );

  function clearAllFilters(): void {
    filterLib = '';
    filterDir = '';
    filterType = '';
    filterTags = [];
    filterTagType = '';
    filterStatus = '';
    filterSource = '';
    closeMenus();
    // 清空会话级恢复状态：下次返回管理页不再带旧筛选
    manageFilterStore.clear();
    // 同步 URL：清除所有筛选参数
    goto('/manage?tab=media', { replaceState: true });
  }

  // 全局键盘处理（关闭弹窗）
  function onGlobalKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      if (renameDialogOpen) { e.preventDefault(); renameDialogOpen = false; }
      else if (moveDirDialogOpen) { e.preventDefault(); moveDirDialogOpen = false; }
      else if (ratingDialogOpen) { e.preventDefault(); ratingDialogOpen = false; }
      else if (moveLibDialogOpen) { e.preventDefault(); moveLibDialogOpen = false; }
      else if (openMenu) { e.preventDefault(); closeMenus(); }
    }
  }

  // ---- 列宽调整（仅列表视图） ----
  const DEFAULT_COL_WIDTHS: Record<string, number> = {
    title: 220,
    lib: 80,
    duration: 70,
    res: 80,
    size: 70,
    rating: 80,
    tags: 150
  };
  const COL_MIN = 40;
  const COL_MAX = 500;
  const COL_WIDTHS_KEY = 'manage-col-widths';

  let colWidths = $state<Record<string, number>>(
    { ...DEFAULT_COL_WIDTHS, ...(JSON.parse(localStorage.getItem(COL_WIDTHS_KEY) || '{}') as Record<string, number>) }
  );

  let resizing = $state<{ col: string; startX: number; startWidth: number } | null>(null);

  // 列网格模板：checkbox(36) + thumb(56) 固定，其余可调。
  // 标题列和标签列用 minmax(Xpx, Nfr) 实现自适应：最小宽度由用户调整决定，
  // 剩余空间按 fr 比例分配，避免右侧出现大块空白。
  const gridTemplate = $derived(
    `36px 56px minmax(${colWidths.title ?? 220}px, 2fr) ${colWidths.lib ?? 80}px ${colWidths.duration ?? 70}px ${colWidths.res ?? 80}px ${colWidths.size ?? 70}px ${colWidths.rating ?? 80}px minmax(${colWidths.tags ?? 150}px, 1fr)`
  );

  function startResize(e: MouseEvent, col: string): void {
    e.preventDefault();
    e.stopPropagation();
    resizing = { col, startX: e.clientX, startWidth: colWidths[col] ?? DEFAULT_COL_WIDTHS[col] };
  }

  function onResizeMove(e: MouseEvent): void {
    if (!resizing) return;
    const delta = e.clientX - resizing.startX;
    let w = resizing.startWidth + delta;
    if (w < COL_MIN) w = COL_MIN;
    if (w > COL_MAX) w = COL_MAX;
    colWidths = { ...colWidths, [resizing.col]: w };
  }

  function onResizeUp(): void {
    if (!resizing) return;
    resizing = null;
    localStorage.setItem(COL_WIDTHS_KEY, JSON.stringify(colWidths));
  }

  $effect(() => {
    if (resizing) {
      window.addEventListener('mousemove', onResizeMove);
      window.addEventListener('mouseup', onResizeUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      return () => {
        window.removeEventListener('mousemove', onResizeMove);
        window.removeEventListener('mouseup', onResizeUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };
    }
  });

  function resetColumnWidths(): void {
    colWidths = { ...DEFAULT_COL_WIDTHS };
    localStorage.setItem(COL_WIDTHS_KEY, JSON.stringify(colWidths));
    showToast('已重置列宽');
  }
</script>

<svelte:window onkeydown={onGlobalKeydown} />

<!-- 工具栏（固定顶部） -->
<div class="toolbar">
  <div class="chips">
    <!-- 库 ▾ -->
    <div class="chip-wrap">
      <button class="chip" class:active={!!filterLib} onclick={() => toggleMenu('lib')}>
        <span>{libLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'lib'}
        <div class="menu">
          <button class="menu-item" class:active={!filterLib} onclick={() => pickLib('')}>全部库</button>
          {#each libraries as l (l.id)}
            <button class="menu-item" class:active={filterLib === l.id} onclick={() => pickLib(l.id)}>
              {l.name}
              {#if l.media_count != null}<span class="muted">{l.media_count}</span>{/if}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- 类型 ▾ -->
    <div class="chip-wrap">
      <button class="chip" class:active={!!filterType} onclick={() => toggleMenu('type')}>
        <span>{typeLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'type'}
        <div class="menu">
          {#each typeOptions as o (o.value)}
            <button class="menu-item" class:active={filterType === o.value} onclick={() => pickType(o.value)}>{o.label}</button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- 标签 ▾ -->
    <div class="chip-wrap">
      <button class="chip" class:active={filterTags.length > 0 || filterTagType !== ''} onclick={() => toggleMenu('tags')}>
        <span>{tagLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'tags'}
        <div class="menu menu-tags">
          {#if tags.length === 0}
            <div class="menu-empty">暂无标签</div>
          {:else}
            <!-- 分类筛选条 -->
            <div class="tag-type-bar">
              <button
                class="type-chip"
                class:active={filterTagType === ''}
                onclick={() => pickTagTypeFilter('')}
              >全部</button>
              {#each tagTypes as tt (tt.id)}
                <button
                  class="type-chip"
                  class:active={filterTagType === tt.id}
                  onclick={() => pickTagTypeFilter(tt.id)}
                >
                  {#if tt.color}<span class="dot" style={`background:${tt.color}`}></span>{/if}
                  {tt.name}
                </button>
              {/each}
            </div>
            <!-- 标签树 -->
            <div class="tag-tree">
              {#snippet tagNode(t: Tag, depth: number)}
                <div class="tree-row" style={`padding-left:${6 + depth * 16}px`}>
                  {#if t.children?.length}
                    <button class="tree-toggle" onclick={() => toggleExpandTag(t.id)} title={expandedTags.has(t.id) ? '收起' : '展开'}>
                      {expandedTags.has(t.id) ? '▾' : '▸'}
                    </button>
                  {:else}
                    <span class="tree-toggle-spacer"></span>
                  {/if}
                  <button
                    class="tree-item"
                    class:active={filterTags.includes(t.id)}
                    onclick={() => toggleFilterTag(t.id)}
                  >
                    <span class="tree-check">{filterTags.includes(t.id) ? '✓' : ''}</span>
                    <span class="dot" style={t.color ? `background:${t.color}` : ''}></span>
                    <span class="label">{t.name}</span>
                    {#if t.count != null}<span class="muted">{t.count}</span>{/if}
                  </button>
                </div>
                {#if t.children?.length && expandedTags.has(t.id)}
                  {#each t.children as c (c.id)}
                    {@render tagNode(c, depth + 1)}
                  {/each}
                {/if}
              {/snippet}
              {#each visibleTagRoots as root (root.id)}
                {@render tagNode(root, 0)}
              {/each}
            </div>
          {/if}
          <div class="menu-foot">
            <button class="link" onclick={() => { filterTags = []; filterTagType = ''; }}>清除</button>
            <button class="link primary" onclick={closeMenus}>完成</button>
          </div>
        </div>
      {/if}
    </div>

    <!-- 状态 ▾ -->
    <div class="chip-wrap" data-menu="status">
      <button
        class="chip"
        class:active={!!filterStatus}
        onclick={() => toggleMenu('status')}
        onkeydown={(e) => onChipKeydown(e, 'status')}
        aria-haspopup="listbox"
        aria-expanded={openMenu === 'status'}
      >
        <span>{statusLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'status'}
        <div class="menu" onkeydown={onMenuKeydown} role="listbox" aria-label="状态筛选" tabindex="-1">
          {#each statusOptions as o (o.value)}
            <button
              class="menu-item"
              class:active={filterStatus === o.value}
              role="option"
              aria-selected={filterStatus === o.value}
              onclick={() => pickStatus(o.value)}
            >{o.label}</button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- 排序 ▾（排序总是生效，不做"激活"高亮，避免误认为筛选未生效） -->
    <div class="chip-wrap" data-menu="sort">
      <button
        class="chip"
        onclick={() => toggleMenu('sort')}
        onkeydown={(e) => onChipKeydown(e, 'sort')}
        aria-haspopup="listbox"
        aria-expanded={openMenu === 'sort'}
      >
        <span>{sortLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'sort'}
        <div class="menu" onkeydown={onMenuKeydown} role="listbox" aria-label="排序" tabindex="-1">
          {#each sortOptions as o (o.value)}
            <button
              class="menu-item"
              class:active={sortField === o.value}
              role="option"
              aria-selected={sortField === o.value}
              onclick={() => pickSort(o.value)}
            >
              <span>{o.label}</span>
              {#if sortField === o.value}<span class="muted">{sortOrder === 'asc' ? '↑' : '↓'}</span>{/if}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    {#if activeFilterCount > 0}
      <button class="clear" onclick={clearAllFilters}>清除筛选 ({activeFilterCount})</button>
    {/if}
  </div>

  <div class="toolbar-actions">
    {#if view === 'list'}
      <button class="reset-cols-btn" onclick={resetColumnWidths} title="重置列宽">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
          <path d="M3 4v4h4" />
        </svg>
        <span>重置列宽</span>
      </button>
    {/if}
    <button class="import-btn" onclick={() => goto('/import')}>
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6">
        <path d="M8 2v8M4.5 6.5L8 10l3.5-3.5" stroke-linecap="round" stroke-linejoin="round"></path>
        <path d="M2 12v1.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V12" stroke-linecap="round"></path>
      </svg>
      <span>导入媒体库</span>
    </button>
    <button class="import-btn" onclick={() => (networkImportOpen = true)} title="从网络 URL 导入媒体">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="2" y1="12" x2="22" y2="12"/>
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
      </svg>
      <span>网络导入</span>
    </button>
    <button class="import-btn" onclick={() => { duplicatesOpen = true; }} title="按内容哈希/文件名/大小查找重复文件">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <rect x="8" y="3" width="13" height="13" rx="2"/>
        <path d="M16 16v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2h3"/>
      </svg>
      <span>查重</span>
    </button>
  </div>
  <div class="view-switch">
    <button class="vs-btn" class:active={view === 'list'} title="列表视图" onclick={() => (view = 'list')}>
      <svg viewBox="0 0 24 24" width="14" height="14"><path d="M3 5h18v2H3V5zm0 6h18v2H3v-2zm0 6h18v2H3v-2z" fill="currentColor"/></svg>
      <span>列表</span>
    </button>
    <button class="vs-btn" class:active={view === 'grid'} title="网格视图" onclick={() => (view = 'grid')}>
      <svg viewBox="0 0 24 24" width="14" height="14"><path d="M3 3h8v8H3V3zm10 0h8v8h-8V3zM3 13h8v8H3v-8zm10 0h8v8h-8v-8z" fill="currentColor"/></svg>
      <span>网格</span>
    </button>
  </div>
</div>

<!-- 批量操作条（选中 ≥1 项时从顶部滑出） -->
<div class="batch-bar" class:show={selectedCount > 0}>
  <div class="batch-left">
    <label class="select-all-wrap">
      <input type="checkbox" checked={allOnPageSelected} indeterminate={someOnPageSelected} onchange={toggleSelectAll} />
      <span>已选 <strong>{selectedCount}</strong> 项</span>
    </label>
    <button class="clear-sel" onclick={clearSelection}>取消选择</button>
  </div>
  <div class="batch-actions">
    <button class="batch-btn" onclick={() => (tagSelectorOpen = true)}>
      <svg viewBox="0 0 24 24" width="14" height="14"><path d="M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42z" fill="currentColor"/></svg>
      批量打标
    </button>
    <button class="batch-btn" onclick={() => { batchRating = 0; ratingDialogOpen = true; }}>
      <svg viewBox="0 0 24 24" width="14" height="14"><path d="M12 2l2.95 5.98 6.6.96-4.77 4.65 1.13 6.57L12 17.55l-5.91 3.11 1.13-6.57L2.45 9.44l6.6-.96L12 2z" fill="currentColor"/></svg>
      批量评分
    </button>
    <button class="batch-btn" onclick={() => (moveLibDialogOpen = true)}>
      <svg viewBox="0 0 24 24" width="14" height="14"><path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-2 6h-4v3h-2v-3H8l4-4 4 4z" fill="currentColor"/></svg>
      移动到库
    </button>
    <button class="batch-btn" onclick={openMoveDirDialog}>
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
        <path d="M12 11v6M9 14l3 3 3-3" />
      </svg>
      移动到目录
    </button>
    <button class="batch-btn" onclick={openRenameDialog}>
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
      </svg>
      批量重命名
    </button>
    <button class="batch-btn" onclick={() => (deleteDialogOpen = true)}>
      <svg viewBox="0 0 24 24" width="14" height="14"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/></svg>
      删除
    </button>
    <button class="batch-btn" onclick={batchExport}>
      <svg viewBox="0 0 24 24" width="14" height="14"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" fill="currentColor"/></svg>
      导出
    </button>
    <button class="batch-btn" onclick={batchScrape} disabled={batchScraping}>
      {#if batchScraping}
        刮削中…
      {:else}
        <svg viewBox="0 0 24 24" width="14" height="14"><path d="M20.2 6 3 11l-.9-2.4c-.3-.9.2-1.9 1-2.2l14-4.5c.9-.3 1.9.2 2.2 1zM6.2 5.3l3.1 3.9M12.4 3.4l3.1 4M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        批量刮削
      {/if}
    </button>
    <button class="batch-btn" onclick={batchContactSheet} disabled={batchSheeting} title="为选中媒体生成 4×4 缩略图集（1920×1080）">
      {#if batchSheeting}
        生成中…
      {:else}
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="8" height="8" rx="1" />
          <rect x="13" y="3" width="8" height="8" rx="1" />
          <rect x="3" y="13" width="8" height="8" rx="1" />
          <rect x="13" y="13" width="8" height="8" rx="1" />
        </svg>
        缩略图集
      {/if}
    </button>
  </div>
</div>

<!-- 面包屑导航（侧边栏目录树点击后显示当前位置） -->
{#if filterLib || filterDir}
  <div class="breadcrumb">
    <button class="crumb" onclick={() => navigateToDir('')}>
      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"></path>
      </svg>
      <span>{filterLib ? libraryMap[filterLib] ?? '未知库' : '全部库'}</span>
    </button>
    {#each dirSegments as seg, i}
      <span class="crumb-sep">/</span>
      <button class="crumb" class:active={i === dirSegments.length - 1} onclick={() => navigateToDir(seg.path)}>
        {seg.label}
      </button>
    {/each}
    {#if filterDir}
      <button class="crumb-clear" title="清除目录筛选" onclick={() => navigateToDir('')}>
        <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M4 4l8 8M12 4l-8 8" stroke-linecap="round"></path>
        </svg>
      </button>
    {/if}
  </div>
{/if}

<!-- 内容区 -->
<div class="manage-content" onscroll={onContentScroll}>
  {#if loading && items.length > 0}
    <div class="reload-indicator" role="status" aria-label="加载中"></div>
  {/if}
  {#if loading && items.length === 0}
    <div class="state">加载中…</div>
  {:else if error}
    <div class="state error">{error}</div>
  {:else if items.length === 0}
    <div class="state empty">
      <div class="empty-icon">📭</div>
      <div class="empty-text">没有匹配的媒体</div>
      <div class="empty-hint">尝试调整筛选条件</div>
    </div>
  {:else if view === 'list'}
    <!-- 密集列表 -->
    <div class="list-view">
      <div class="list-head" class:resizing={!!resizing} style={`grid-template-columns:${gridTemplate}`}>
        <div class="checkbox-cell">
          <input type="checkbox" checked={allOnPageSelected} indeterminate={someOnPageSelected} onchange={toggleSelectAll} />
        </div>
        <div class="col col-thumb"></div>
        <div class="col col-title">
          <span>标题</span>
          <span class="col-resize" onmousedown={(e) => startResize(e, 'title')}></span>
        </div>
        <div class="col col-lib">
          <span>库</span>
          <span class="col-resize" onmousedown={(e) => startResize(e, 'lib')}></span>
        </div>
        <div class="col col-duration">
          <span>时长</span>
          <span class="col-resize" onmousedown={(e) => startResize(e, 'duration')}></span>
        </div>
        <div class="col col-res">
          <span>分辨率</span>
          <span class="col-resize" onmousedown={(e) => startResize(e, 'res')}></span>
        </div>
        <div class="col col-size">
          <span>大小</span>
          <span class="col-resize" onmousedown={(e) => startResize(e, 'size')}></span>
        </div>
        <div class="col col-rating">
          <span>评分</span>
          <span class="col-resize" onmousedown={(e) => startResize(e, 'rating')}></span>
        </div>
        <div class="col col-tags">
          <span>标签</span>
          <span class="col-resize" onmousedown={(e) => startResize(e, 'tags')}></span>
        </div>
      </div>
      <div class="list-body">
        {#each items as media (media.id)}
          <div
            class="row"
            class:selected={selected.has(media.id)}
            style={`grid-template-columns:${gridTemplate}`}
            onclick={(e) => onRowClick(e, media)}
            oncontextmenu={(e) => onItemContextMenu(e, media)}
            role="button"
            tabindex="0"
            onkeydown={(e) => { if (e.key === 'Enter' && (e.target as HTMLElement).tagName !== 'INPUT') goto(`/detail/${media.id}`); }}
          >
            <div class="checkbox-cell">
              <input
                type="checkbox"
                checked={selected.has(media.id)}
                onchange={() => toggleSelect(media.id)}
                onclick={(e) => e.stopPropagation()}
              />
            </div>
            <div class="col col-thumb">
              <div class="mini-thumb">
                {#if media.poster}
                  <img src={mediaApi.posterUrl(media.id, media.updated_at)} alt="" loading="lazy" onerror={(e) => imageFallback(e, media)} />
                {:else if media.thumbnail}
                  <img src={mediaApi.thumbnailUrl(media.id, media.updated_at)} alt="" loading="lazy" onerror={(e) => imageFallback(e, media)} />
                {:else}
                  <span class="fb">{media.type === 'video' ? '▶' : media.type === 'audio' ? '♪' : '▣'}</span>
                {/if}
              </div>
            </div>
            <div class="col col-title" title={media.filename}>
              <span class="title-text" class:missing={media.file_missing}>{media.filename}</span>
              {#if !media.file_missing && (media.source_type === 'network' || media.source_type === 'both')}
                <span class="src-badge net" title={media.source_type === 'both' ? '本地 + 网络源' : '网络媒体'}>
                  {media.source_type === 'both' ? '本+网' : '网'}
                </span>
              {/if}
              {#if media.file_missing}
                <span class="src-badge" class:has-net={hasNetworkSource(media)} title={hasNetworkSource(media) ? '本地文件丢失 — 可从网络源播放' : '本地文件丢失'}>
                  {hasNetworkSource(media) ? '🔗' : '⚠'}
                </span>
              {/if}
              {#if media.title && media.title !== media.filename}
                <span class="title-sub">{media.title}</span>
              {/if}
              {#if media.favorite}<span class="fav">♥</span>{/if}
            </div>
            <div class="col col-lib">{libraryMap[media.library_id] ?? '—'}</div>
            <div class="col col-duration">{media.duration ? formatTime(media.duration) : '—'}</div>
            <div class="col col-res">{formatResolution(media.width, media.height)}</div>
            <div class="col col-size">{formatSize(media.size)}</div>
            <div class="col col-rating">
              <RatingStars value={media.rating} size={12} readonly />
            </div>
            <div class="col col-tags">
              {#if media.tags && media.tags.length}
                <div class="tag-list">
                  {#each media.tags.slice(0, 3) as tid (tid)}
                    <span class="tag">{tagMap[tid] ?? tid}</span>
                  {/each}
                  {#if media.tags.length > 3}<span class="tag more">+{media.tags.length - 3}</span>{/if}
                </div>
              {:else}—{/if}
            </div>
          </div>
        {/each}
      </div>
    </div>
  {:else}
    <!-- 网格视图 -->
    <div class="grid-view">
      {#each items as media (media.id)}
        <div
          class="grid-card"
          class:selected={selected.has(media.id)}
          onclick={(e) => onRowClick(e, media)}
          oncontextmenu={(e) => onItemContextMenu(e, media)}
          role="button"
          tabindex="0"
          onkeydown={(e) => { if (e.key === 'Enter' && (e.target as HTMLElement).tagName !== 'INPUT') goto(`/detail/${media.id}`); }}
        >
          <div class="grid-thumb" class:av-poster={isAvMedia(media)}>
            {#if media.poster}
              <img src={mediaApi.posterUrl(media.id, media.updated_at)} alt="" loading="lazy" onerror={(e) => imageFallback(e, media)} />
            {:else if media.thumbnail}
              <img src={mediaApi.thumbnailUrl(media.id, media.updated_at)} alt="" loading="lazy" onerror={(e) => imageFallback(e, media)} />
            {:else}
              <span class="fb">{media.type === 'video' ? '▶' : media.type === 'audio' ? '♪' : '▣'}</span>
            {/if}
            <label class="grid-check">
              <input
                type="checkbox"
                checked={selected.has(media.id)}
                onchange={() => toggleSelect(media.id)}
                onclick={(e) => e.stopPropagation()}
              />
            </label>
            {#if media.file_missing}
              <span class="grid-missing-badge" class:has-net={hasNetworkSource(media)} title={hasNetworkSource(media) ? '本地文件丢失 — 可从网络源播放' : '本地文件丢失'}>
                {hasNetworkSource(media) ? '🔗' : '⚠'}
              </span>
            {/if}
            {#if !media.file_missing && (media.source_type === 'network' || media.source_type === 'both')}
              <span class="grid-net-badge" title={media.source_type === 'both' ? '本地 + 网络源' : '网络媒体'}>
                {media.source_type === 'both' ? '本+网' : '网'}
              </span>
            {/if}
            {#if media.duration}
              <span class="duration">{formatTime(media.duration)}</span>
            {/if}
          </div>
          <div class="grid-info">
            <div class="grid-title" title={media.filename}>{media.filename}</div>
            <div class="grid-meta">
              <RatingStars value={media.rating} size={11} readonly />
              <span class="muted">{formatSize(media.size)}</span>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- 分页 -->
{#if items.length > 0}
  <div class="pager" bind:this={pagerEl}>
    <div class="pager-left">
      <button class="pg-btn" disabled={page <= 1} onclick={() => gotoPage(page - 1)} aria-label="上一页">‹</button>
      {#each pageList(page, totalPages, maxVisiblePages) as p}
        {#if p === '…'}
          <span class="pg-ellipsis">…</span>
        {:else}
          <button class="pg-btn" class:active={p === page} aria-current={p === page ? 'page' : undefined} onclick={() => gotoPage(p)}>{p}</button>
        {/if}
      {/each}
      <button class="pg-btn" disabled={page >= totalPages} onclick={() => gotoPage(page + 1)} aria-label="下一页">›</button>
    </div>
    <div class="pager-right">
      <span>共 {total.toLocaleString('zh-CN')} 项</span>
      <span>每页</span>
      <select value={pageSize} onchange={onPageSizeChange}>
        <option value={30}>30</option>
        <option value={50}>50</option>
        <option value={100}>100</option>
        <option value={200}>200</option>
      </select>
    </div>
  </div>
{/if}

<!-- 标签选择器 -->
<TagSelector
  bind:open={tagSelectorOpen}
  {tags}
  multiple={true}
  title="批量打标"
  onselect={(ids) => batchAddTags(ids)}
  oncancel={() => (tagSelectorOpen = false)}
/>

<!-- 批量评分对话框 -->
{#if ratingDialogOpen}
  <div class="backdrop" onclick={(e) => { if (e.target === e.currentTarget) ratingDialogOpen = false; }} onkeydown={(e) => { if (e.key === 'Escape' || e.key === 'Enter') { e.preventDefault(); ratingDialogOpen = false; } }} role="button" tabindex="-1" aria-label="关闭">
    <div class="rating-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h2>批量评分</h2>
      <p class="dialog-desc">为已选 {selectedCount} 项媒体设置评分</p>
      <div class="rating-picker">
        <RatingStars bind:value={batchRating} size={32} allowClear={true} onrate={(v) => (batchRating = v)} />
        <span class="rating-value">{batchRating > 0 ? `${batchRating} 星` : '未设置'}</span>
      </div>
      <div class="rating-dialog-foot">
        <button class="btn btn-cancel" onclick={() => (ratingDialogOpen = false)}>取消</button>
        <button class="btn btn-primary" onclick={() => batchSetRating(batchRating)}>确认</button>
      </div>
    </div>
  </div>
{/if}

<!-- 移动到库对话框 -->
{#if moveLibDialogOpen}
  <div class="backdrop" onclick={(e) => { if (e.target === e.currentTarget) moveLibDialogOpen = false; }} onkeydown={(e) => { if (e.key === 'Escape' || e.key === 'Enter') { e.preventDefault(); moveLibDialogOpen = false; } }} role="button" tabindex="-1" aria-label="关闭">
    <div class="move-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h2>移动到库</h2>
      <p class="dialog-desc">将已选 {selectedCount} 项媒体移动到指定库</p>
      <div class="lib-select-wrap">
        <select bind:value={targetLibraryId} class="lib-select">
          <option value="">请选择目标库...</option>
          {#each libraries as l (l.id)}
            <option value={l.id}>{l.name}</option>
          {/each}
        </select>
      </div>
      <div class="move-dialog-foot">
        <button class="btn btn-cancel" onclick={() => (moveLibDialogOpen = false)}>取消</button>
        <button class="btn btn-primary" disabled={!targetLibraryId} onclick={batchMoveLibrary}>移动</button>
      </div>
    </div>
  </div>
{/if}

<!-- 批量重命名对话框 -->
{#if renameDialogOpen}
  <div class="backdrop" onclick={(e) => { if (e.target === e.currentTarget) renameDialogOpen = false; }} role="button" tabindex="-1" aria-label="关闭">
    <div class="rename-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h2>批量重命名</h2>
      <p class="dialog-desc">使用模板批量重命名已选 {selectedCount} 项媒体的文件名（扩展名自动保留）</p>

      <div class="rename-template-section">
        <label class="rename-label" for="rename-template">命名模板</label>
        <input
          id="rename-template"
          type="text"
          class="rename-input"
          bind:value={renameTemplate}
          placeholder={'例如: {title} ({year})'}
          onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); generateRenamePreview(); } }}
        />
        <div class="rename-vars">
          {#each renameTemplateVars as v (v.token)}
            <button
              class="rename-var-chip"
              onclick={() => { renameTemplate = renameTemplate + v.token; }}
              title={v.desc}
            >
              {v.token}
              <span class="rename-var-desc">{v.desc}</span>
            </button>
          {/each}
        </div>
      </div>

      <div class="rename-start-section">
        <label class="rename-label" for="rename-index">起始序号</label>
        <input
          id="rename-index"
          type="number"
          class="rename-index-input"
          bind:value={renameStartIndex}
          min="0"
          max="9999"
        />
      </div>

      <div class="rename-suffix-section">
        <label class="rename-checkbox">
          <input type="checkbox" bind:checked={renameAutoSuffix} />
          目标文件名冲突时自动追加序号 (1)(2)…
        </label>
      </div>

      <div class="rename-preview-section">
        <div class="rename-preview-head">
          <span>预览</span>
          <button class="btn btn-sm" onclick={generateRenamePreview} disabled={renamePreviewLoading}>
            {renamePreviewLoading ? '生成中…' : '刷新预览'}
          </button>
        </div>
        <div class="rename-preview-table">
          {#if renamePreviews.length === 0}
            <div class="rename-preview-empty">点击"刷新预览"查看重命名结果</div>
          {:else}
            <div class="rename-preview-row rename-preview-header">
              <span class="rp-old">原文件名</span>
              <span class="rp-arrow">→</span>
              <span class="rp-new">新文件名</span>
            </div>
            {#each renamePreviews as p (p.id)}
              <div class="rename-preview-row" class:error={p.error}>
                <span class="rp-old" title={p.old_name}>{p.old_name}</span>
                <span class="rp-arrow">→</span>
                <span class="rp-new" title={p.error || p.new_name}>
                  {p.error ? `⚠ ${p.error}` : p.new_name}
                </span>
              </div>
            {/each}
          {/if}
        </div>
      </div>

      <div class="move-dialog-foot">
        <button class="btn btn-cancel" onclick={() => (renameDialogOpen = false)}>取消</button>
        <button
          class="btn btn-primary"
          disabled={renameApplying || renamePreviews.some((p) => p.error)}
          onclick={batchRenameApply}
        >
          {renameApplying ? '重命名中…' : `应用重命名 (${renamePreviews.filter((p) => !p.error).length})`}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- 移动到目录对话框 -->
{#if moveDirDialogOpen}
  <div class="backdrop" onclick={(e) => { if (e.target === e.currentTarget) moveDirDialogOpen = false; }} role="button" tabindex="-1" aria-label="关闭">
    <div class="move-dir-dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h2>移动到目录</h2>
      <p class="dialog-desc">将已选 {selectedCount} 项媒体移动到指定目录</p>

      <div class="lib-select-wrap">
        <select
          bind:value={moveDirLibId}
          onchange={() => { if (moveDirLibId) loadMoveDirTree(moveDirLibId); }}
          class="lib-select"
        >
          <option value="">请选择目标库...</option>
          {#each libraries as l (l.id)}
            <option value={l.id}>{l.name}</option>
          {/each}
        </select>
      </div>

      {#if moveDirLoading}
        <div class="dir-loading">加载目录中…</div>
      {:else if moveDirLibId}
        <div class="dir-browser">
          <div
            class="dir-item"
            class:active={moveDirTargetPath === ''}
            onclick={() => (moveDirTargetPath = '')}
            role="button"
            tabindex="0"
            onkeydown={(e) => { if (e.key === 'Enter') moveDirTargetPath = ''; }}
          >
            <span class="dir-icon">📁</span>
            <span class="dir-name">根目录</span>
            {#if moveDirTargetPath === ''}<span class="dir-check">✓</span>{/if}
          </div>
          {#each moveDirFlatTree as entry (entry.node.rel_path)}
            <div
              class="dir-item"
              class:active={moveDirTargetPath === entry.node.rel_path}
              style={`padding-left:${12 + entry.depth * 20}px`}
              onclick={() => (moveDirTargetPath = entry.node.rel_path)}
              role="button"
              tabindex="0"
              onkeydown={(e) => { if (e.key === 'Enter') moveDirTargetPath = entry.node.rel_path; }}
            >
              <span
                class="dir-toggle"
                class:expanded={entry.expanded}
                onclick={(e) => { e.stopPropagation(); toggleMoveDirExpand(entry.node.rel_path); }}
                role="button"
                tabindex="-1"
              >
                {entry.expanded ? '▾' : '▸'}
              </span>
              <span class="dir-icon">📁</span>
              <span class="dir-name" title={entry.node.name}>{entry.node.name}</span>
              {#if moveDirTargetPath === entry.node.rel_path}<span class="dir-check">✓</span>{/if}
            </div>
          {/each}
          {#if moveDirTree.length === 0}
            <div class="dir-empty">该库暂无子目录</div>
          {/if}
        </div>
      {:else}
        <div class="dir-empty">请先选择目标库</div>
      {/if}

      <div class="move-dialog-foot">
        <button class="btn btn-cancel" onclick={() => (moveDirDialogOpen = false)}>取消</button>
        <button class="btn btn-primary" disabled={!moveDirLibId || moveDirMoving} onclick={batchMoveDirectory}>
          {moveDirMoving ? '移动中…' : '移动'}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- 删除确认对话框 -->
<ConfirmDialog
  bind:open={deleteDialogOpen}
  title="删除已选媒体"
  description={`将删除已选 ${selectedCount} 项媒体。\n\n媒体将被移入回收站，30 天内可在回收站中恢复。超过 30 天将被永久删除。`}
  confirmText="删除"
  danger={true}
  onconfirm={batchDelete}
  oncancel={() => (deleteDialogOpen = false)}
/>

<!-- 单项右键菜单 -->
{#if itemContextMenu}
  <div
    class="item-ctx-menu"
    style={`left:${Math.min(itemContextMenu.x, window.innerWidth - 200)}px; top:${Math.min(itemContextMenu.y, window.innerHeight - 200)}px`}
  >
    <button class="item-ctx-item" onclick={() => { const m = itemContextMenu!.media; closeItemContextMenu(); goto(`/detail/${m.id}`); }}>
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
      </svg>
      查看详情
    </button>
    <button class="item-ctx-item" onclick={() => { editMediaTarget = itemContextMenu!.media; closeItemContextMenu(); editDialogOpen = true; }}>
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
      </svg>
      编辑
    </button>
    <button class="item-ctx-item" onclick={() => itemScrape(itemContextMenu!.media)} disabled={aiRescrapingId === itemContextMenu!.media.id}>
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20.2 6 3 11l-.9-2.4c-.3-.9.2-1.9 1-2.2l14-4.5c.9-.3 1.9.2 2.2 1zM6.2 5.3l3.1 3.9M12.4 3.4l3.1 4M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      </svg>
      {aiRescrapingId === itemContextMenu!.media.id ? '处理中…' : '重新刮削'}
    </button>
    {#if !itemContextMenu!.media.file_missing}
      <button
        class="item-ctx-item"
        title="抽取 16 帧合成 4×4 缩略图集（1920×1080，详情页可查看）"
        onclick={() => { const m = itemContextMenu!.media; itemContactSheet(m); }}
        disabled={sheetingId === itemContextMenu!.media.id}
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="8" height="8" rx="1" />
          <rect x="13" y="3" width="8" height="8" rx="1" />
          <rect x="3" y="13" width="8" height="8" rx="1" />
          <rect x="13" y="13" width="8" height="8" rx="1" />
        </svg>
        {sheetingId === itemContextMenu!.media.id ? '生成中…' : '生成缩略图集'}
      </button>
    {/if}
    {#if itemContextMenu!.media.file_missing}
      <button
        class="item-ctx-item convert-item"
        disabled={convertingNetId === itemContextMenu!.media.id}
        title="本地文件已丢失：为媒体添加网络源并转为纯网络视频（保留记录/标签/元数据）"
        onclick={() => { const m = itemContextMenu!.media; itemConvertToNetwork(m); }}
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
        </svg>
        {convertingNetId === itemContextMenu!.media.id ? '转换中…' : '转为网络视频'}
      </button>
    {/if}
    <button
      class="item-ctx-item danger"
      title={itemContextMenu!.media.file_missing ? '删除记录（本地文件已丢失，仅移除记录）' : '移入回收站（磁盘文件保留，可到回收站二次确认）'}
      onclick={() => { const m = itemContextMenu!.media; closeItemContextMenu(); void recycleLocalFile(m); }}
    >
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6zM19 4h-3.5l-1-1h-5l-1 1H5v2h14z" />
      </svg>
      移入回收站
    </button>
    <button class="item-ctx-item ai-item" onclick={() => itemAiRescrape(itemContextMenu!.media)} disabled={aiRescrapingId === itemContextMenu!.media.id}>
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
      </svg>
      {aiRescrapingId === itemContextMenu!.media.id ? 'AI 处理中…' : 'AI 辅助刮削'}
    </button>
  </div>
{/if}

<!-- Toast -->
{#if toast}
  <div class="toast" class:ok={toast.type === 'ok'} class:err={toast.type === 'err'}>
    <span>{toast.msg}</span>
    {#if toast.undoIds && toast.undoIds.length > 0}
      <button class="toast-undo" disabled={undoing} onclick={undoDelete}>
        {undoing ? '恢复中…' : '撤销'}
      </button>
    {/if}
  </div>
{/if}

<!-- 网络媒体导入对话框 -->
<NetworkImportDialog bind:open={networkImportOpen} onsuccess={loadMedia} />

<!-- 重复文件检测向导 -->
<DuplicatesDialog bind:open={duplicatesOpen} />

<!-- 编辑媒体对话框 -->
<EditMediaDialog bind:open={editDialogOpen} media={editMediaTarget} onsuccess={loadMedia} />

<style>
  /* ---- 面包屑 ---- */
  .breadcrumb {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 24px;
    background: var(--bg);
    border-bottom: 1px solid var(--rule);
    flex-shrink: 0;
    font-size: 13px;
    flex-wrap: wrap;
  }

  .crumb {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    border: none;
    background: none;
    color: var(--muted);
    cursor: pointer;
    border-radius: 4px;
    font-size: 13px;
    transition: all 0.15s;
  }

  .crumb:hover {
    background: var(--hover);
    color: var(--text);
  }

  .crumb.active {
    color: var(--text);
    font-weight: 500;
    pointer-events: none;
  }

  .crumb-sep {
    color: var(--muted);
    font-size: 12px;
    user-select: none;
  }

  .crumb-clear {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border: none;
    background: none;
    color: var(--muted);
    cursor: pointer;
    border-radius: 4px;
    margin-left: 4px;
    transition: all 0.15s;
  }

  .crumb-clear:hover {
    background: var(--hover);
    color: var(--danger, #e53e3e);
  }

  /* ---- 工具栏 ---- */
  .toolbar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 24px;
    background: var(--bg);
    border-bottom: 1px solid var(--rule);
    flex-shrink: 0;
  }

  .chips {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .chip-wrap {
    position: relative;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-full);
    color: var(--ink);
    font-size: 12.5px;
    transition: all 200ms ease;
  }

  .chip:hover {
    border-color: var(--muted);
  }

  .chip.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
  }

  .caret {
    font-size: 9px;
    color: var(--muted);
  }

  .chip.active .caret {
    color: var(--accent);
  }

  .menu {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    min-width: 180px;
    background: var(--bg2);
    backdrop-filter: blur(12px);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.14);
    padding: 4px;
    z-index: 200;
    animation: pop 120ms ease;
  }

  @keyframes pop {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .menu-tags {
    /* 固定宽度：absolute shrink-to-fit 会让超长标签名把菜单撑到近 1000px，
       且选择分类后树内容变化导致宽度剧烈跳动。固定后宽度恒定，tree-item
       的 ellipsis 才真正生效（宽度受约束时才省略）。 */
    width: 320px;
    max-width: calc(100vw - 48px);
    max-height: 360px;
    overflow-y: auto;
  }

  /* 分类筛选条 */
  .tag-type-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
    position: sticky;
    top: 0;
    background: var(--bg-elevated, #1e1e2e);
    z-index: 1;
  }

  .type-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border: 1px solid var(--border, rgba(255,255,255,0.12));
    border-radius: 999px;
    background: none;
    color: var(--muted, #888);
    font-size: 12px;
    cursor: pointer;
    transition: all 150ms;
  }

  .type-chip:hover {
    border-color: var(--accent, #7c3aed);
    color: var(--ink, #fff);
  }

  .type-chip.active {
    background: var(--accent, #7c3aed);
    border-color: var(--accent, #7c3aed);
    color: #fff;
  }

  .type-chip .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* 标签树（高度交给 .menu-tags 统一滚动，避免双层滚动条） */
  .tag-tree {
    padding: 4px 0;
  }

  .tree-row {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    gap: 2px;
  }

  .tree-toggle,
  .tree-toggle-spacer {
    width: 18px;
    height: 24px;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .tree-toggle {
    border: none;
    background: none;
    color: var(--muted, #888);
    font-size: 10px;
    cursor: pointer;
    border-radius: 4px;
  }

  .tree-toggle:hover {
    background: var(--bg-soft, rgba(255,255,255,0.06));
    color: var(--ink, #fff);
  }

  .tree-item {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    gap: 7px;
    flex: 1;
    min-width: 0;
    padding: 5px 8px;
    border: none;
    background: none;
    border-radius: var(--radius, 8px);
    color: var(--ink, #fff);
    font-size: 13px;
    text-align: left;
    cursor: pointer;
    transition: background 150ms;
    overflow: hidden;
  }

  .tree-item:hover {
    background: var(--bg-soft, rgba(255,255,255,0.06));
  }

  .tree-item.active {
    color: var(--accent, #7c3aed);
    background: var(--accent-soft, rgba(124,58,237,0.12));
  }

  .tree-item .label {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .tree-item .muted {
    color: var(--muted, #888);
    font-size: 11.5px;
    flex-shrink: 0;
  }

  .tree-item .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .tree-check {
    width: 12px;
    flex-shrink: 0;
    font-size: 11px;
    color: var(--accent, #7c3aed);
    text-align: center;
  }

  .menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border: none;
    background: none;
    border-radius: var(--radius);
    color: var(--ink);
    font-size: 13px;
    text-align: left;
    transition: background 200ms;
  }

  .menu-item:hover {
    background: var(--bg-soft);
  }

  .menu-item.active {
    color: var(--accent);
    background: var(--accent-soft);
  }

  .menu-item .muted {
    color: var(--muted);
    font-size: 11.5px;
  }

  .menu-empty {
    padding: 12px;
    text-align: center;
    color: var(--muted);
    font-size: 12.5px;
  }

  .menu-foot {
    display: flex;
    justify-content: space-between;
    padding: 6px 8px 4px;
    border-top: 1px solid var(--rule);
    margin-top: 4px;
  }

  .link {
    background: none;
    border: none;
    color: var(--muted);
    font-size: 12.5px;
    padding: 2px 6px;
    border-radius: var(--radius);
  }

  .link:hover {
    color: var(--ink);
    background: var(--bg-soft);
  }

  .link.primary {
    color: var(--accent);
  }

  .clear {
    background: none;
    border: none;
    color: var(--muted);
    font-size: 12.5px;
    padding: 4px 8px;
    border-radius: var(--radius);
    transition: color 200ms;
  }

  .clear:hover {
    color: var(--accent);
  }

  .toolbar-actions {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .import-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 14px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    font-size: 12.5px;
    font-weight: 500;
    transition: background var(--dur) var(--ease-out), transform var(--dur-fast) var(--ease-out);
  }

  .import-btn:hover {
    background: var(--accent-hover);
  }

  .import-btn:active {
    transform: scale(0.97);
  }

  .view-switch {
    display: flex;
    align-items: center;
    gap: 2px;
    background: var(--bg-surface);
    border-radius: var(--radius);
    padding: 2px;
    flex-shrink: 0;
  }

  .vs-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 26px;
    padding: 0 8px;
    border: none;
    background: none;
    border-radius: 5px;
    color: var(--muted);
    font-size: 12px;
    transition: all 200ms;
  }

  .vs-btn:hover {
    color: var(--ink);
  }

  .vs-btn.active {
    background: var(--bg2);
    color: var(--accent);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .reset-cols-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    color: var(--muted);
    font-size: 12.5px;
    transition: all 200ms;
  }

  .reset-cols-btn:hover {
    border-color: var(--accent);
    color: var(--accent);
  }

  /* ---- 批量操作条 ---- */
  .batch-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    max-height: 0;
    overflow: hidden;
    padding: 0 24px;
    background: var(--accent-soft);
    border-bottom: 1px solid transparent;
    transition: max-height 200ms ease, padding 200ms ease, border-color 200ms;
    flex-shrink: 0;
  }

  .batch-bar.show {
    max-height: 60px;
    padding: 10px 24px;
    border-bottom-color: var(--accent);
    box-shadow: 0 2px 8px var(--accent-glow);
  }

  .batch-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .select-all-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--ink);
  }

  .select-all-wrap strong {
    color: var(--accent);
    font-weight: 600;
  }

  .clear-sel {
    background: none;
    border: none;
    color: var(--muted);
    font-size: 12.5px;
    padding: 4px 8px;
    border-radius: var(--radius);
    transition: color 200ms;
  }

  .clear-sel:hover {
    color: var(--ink);
  }

  .batch-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .batch-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 12px;
    border: 1px solid var(--accent);
    background: var(--bg2);
    border-radius: var(--radius);
    color: var(--accent);
    font-size: 12.5px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .batch-btn:hover {
    background: var(--accent);
    color: #06110d;
  }

  /* ---- 内容区 ---- */
  .manage-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px 24px;
    position: relative;
  }

  /* 已有内容时刷新的顶部加载条 */
  .reload-indicator {
    position: sticky;
    top: -12px;
    z-index: 5;
    height: 2px;
    margin: 0 -24px 10px;
    background: linear-gradient(90deg, transparent 0%, var(--accent) 50%, transparent 100%);
    background-size: 40% 100%;
    background-repeat: no-repeat;
    animation: reload-slide 1s linear infinite;
  }
  @keyframes reload-slide {
    from { background-position: -40% 0; }
    to { background-position: 140% 0; }
  }

  .state {
    padding: 80px 0;
    text-align: center;
    color: var(--muted);
    font-size: 14px;
  }

  .state.error {
    color: #ff3b30;
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }

  .empty-icon {
    font-size: 40px;
    opacity: 0.6;
  }

  .empty-text {
    font-size: 15px;
    color: var(--ink);
    font-weight: 500;
  }

  .empty-hint {
    font-size: 12.5px;
    color: var(--muted);
  }

  /* ---- 密集列表 ---- */
  .list-view {
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    overflow-x: auto;
    overflow-y: hidden;
    background: var(--bg2);
  }

  .list-head,
  .row {
    display: grid;
    grid-template-columns: 36px 56px minmax(220px, 2fr) 80px 70px 80px 70px 80px minmax(150px, 1fr);
    align-items: center;
    gap: 10px;
    padding: 0 12px;
  }

  .list-head {
    height: 36px;
    background: var(--bg-soft);
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    border-bottom: 1px solid var(--rule);
  }

  .row {
    height: 44px;
    border-bottom: 1px solid var(--rule);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    transition: background 200ms ease;
    cursor: pointer;
  }

  .row:last-child {
    border-bottom: none;
  }

  .row:hover {
    background: var(--bg-soft);
  }

  .row.selected {
    background: var(--accent-soft);
  }

  .row.selected:hover {
    background: var(--accent-soft);
  }

  .checkbox-cell {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .checkbox-cell input[type='checkbox'] {
    width: 15px;
    height: 15px;
    cursor: pointer;
    accent-color: var(--accent);
  }

  .col {
    min-width: 0;
    overflow: hidden;
  }

  .col-title {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  /* 列宽调整手柄 */
  .list-head .col {
    position: relative;
    overflow: visible;
  }

  .col-resize {
    position: absolute;
    top: 0;
    right: -5px;
    bottom: 0;
    width: 10px;
    cursor: col-resize;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .col-resize::after {
    content: '';
    width: 2px;
    height: 16px;
    background: transparent;
    border-radius: 1px;
    transition: background 150ms;
  }

  .col-resize:hover::after,
  .list-head.resizing .col-resize::after {
    background: var(--accent);
  }

  .title-text {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--ink);
    font-weight: 500;
  }

  .title-sub {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--muted);
    font-size: 11px;
  }

  .col-lib,
  .col-duration,
  .col-res,
  .col-size {
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .mini-thumb {
    width: 40px;
    height: 28px;
    border-radius: 4px;
    overflow: hidden;
    background: var(--bg-soft);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 14px;
  }

  .mini-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .fb {
    pointer-events: none;
  }

  .fav {
    color: var(--accent2);
    font-size: 11px;
  }

  .title-text.missing {
    color: var(--muted);
    text-decoration: line-through;
    text-decoration-color: rgba(239, 68, 68, 0.5);
  }

  .src-badge {
    font-size: 11px;
    color: #ef4444;
    background: rgba(239, 68, 68, 0.1);
    border-radius: var(--radius-full);
    padding: 0 5px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .src-badge.net {
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.12);
  }

  .src-badge.has-net {
    color: var(--accent);
    background: rgba(99, 91, 255, 0.1);
  }

  .grid-missing-badge {
    position: absolute;
    top: 6px;
    right: 6px;
    background: rgba(239, 68, 68, 0.85);
    color: #fff;
    font-size: 11px;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  }

  .grid-missing-badge.has-net {
    background: rgba(99, 91, 255, 0.85);
  }

  .grid-net-badge {
    position: absolute;
    top: 6px;
    left: 6px;
    background: rgba(37, 99, 235, 0.9);
    color: #fff;
    font-size: 10.5px;
    font-weight: 600;
    padding: 1px 8px;
    border-radius: 999px;
    letter-spacing: 0.3px;
  }

  .tag-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .tag {
    font-size: 11px;
    color: var(--muted);
    background: var(--bg-soft);
    border-radius: var(--radius-full);
    padding: 1px 8px;
    white-space: nowrap;
  }

  .tag.more {
    color: var(--accent);
    background: var(--accent-soft);
  }

  /* ---- 网格视图 ---- */
  .grid-view {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 14px;
  }

  .grid-card {
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    overflow: hidden;
    cursor: pointer;
    transition: transform 200ms ease, box-shadow 200ms ease, border-color 200ms;
  }

  .grid-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.1);
    border-color: var(--muted);
  }

  .grid-card.selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-soft);
  }

  .grid-thumb {
    position: relative;
    aspect-ratio: 16 / 10;
    background: var(--bg-soft);
    overflow: hidden;
  }

  .grid-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  /* AV covers are landscape — use a wider ratio and contain fit. */
  .grid-thumb.av-poster {
    aspect-ratio: 3 / 2;
  }

  .grid-thumb.av-poster img {
    object-fit: contain;
  }

  .grid-thumb .fb {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 28px;
  }

  .grid-check {
    position: absolute;
    top: 6px;
    left: 6px;
    background: rgba(255, 255, 255, 0.9);
    border-radius: var(--radius);
    padding: 2px;
    cursor: pointer;
  }

  .grid-check input[type='checkbox'] {
    width: 15px;
    height: 15px;
    accent-color: var(--accent);
    cursor: pointer;
  }

  .duration {
    position: absolute;
    bottom: 6px;
    right: 6px;
    background: rgba(0, 0, 0, 0.7);
    color: #fff;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    font-variant-numeric: tabular-nums;
  }

  .grid-info {
    padding: 8px 10px 10px;
  }

  .grid-title {
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    min-height: 2.7em;
  }

  .grid-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    margin-top: 5px;
    font-size: 11.5px;
  }

  .muted {
    color: var(--muted);
  }

  /* ---- 分页 ---- */
  .pager {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 24px 16px;
    border-top: 1px solid var(--rule);
    flex-shrink: 0;
  }

  .pager-left {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .pg-btn {
    min-width: 28px;
    height: 28px;
    padding: 0 8px;
    border: 1px solid var(--rule);
    background: var(--bg2);
    border-radius: var(--radius);
    color: var(--ink);
    font-size: 12.5px;
    transition: all 200ms;
  }

  .pg-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  .pg-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .pg-btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .pg-ellipsis {
    color: var(--muted);
    padding: 0 4px;
  }

  .pager-right {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12.5px;
    color: var(--muted);
  }

  .pager-right select {
    height: 28px;
    padding: 0 6px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 12.5px;
    font-family: inherit;
  }

  /* ---- 弹窗 ---- */
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.32);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fade 200ms ease;
  }

  @keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .rating-dialog,
  .move-dialog {
    width: 100%;
    max-width: 380px;
    background: var(--bg2);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
    padding: 20px 24px;
    animation: pop 200ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  @keyframes pop {
    from { opacity: 0; transform: translateY(-8px) scale(0.96); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .rating-dialog h2,
  .move-dialog h2 {
    margin: 0 0 6px;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
  }

  .dialog-desc {
    margin: 0 0 16px;
    font-size: 12.5px;
    color: var(--muted);
  }

  .rating-picker {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 16px;
    background: var(--bg-soft);
    border-radius: var(--radius);
    margin-bottom: 16px;
  }

  .rating-value {
    font-size: 13px;
    color: var(--muted);
    font-weight: 500;
  }

  .lib-select-wrap {
    margin-bottom: 16px;
  }

  .lib-select {
    width: 100%;
    height: 36px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
  }

  .lib-select:focus {
    outline: none;
    border-color: var(--accent);
  }

  .rating-dialog-foot,
  .move-dialog-foot {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .btn {
    height: 34px;
    padding: 0 16px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .btn:hover:not(:disabled) {
    border-color: var(--muted);
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-cancel {
    background: var(--bg-soft);
  }

  .btn-primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .btn-primary:hover:not(:disabled) {
    filter: brightness(1.08);
  }

  /* ---- 移动到目录对话框 ---- */
  .move-dir-dialog {
    width: 100%;
    max-width: 460px;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    background: var(--bg2);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
    padding: 20px 24px;
    animation: pop 200ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  .move-dir-dialog h2 {
    margin: 0 0 6px;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
  }

  .dir-browser {
    flex: 1;
    min-height: 0;
    max-height: 360px;
    overflow-y: auto;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: 6px;
    margin-bottom: 16px;
    background: var(--bg-soft);
  }

  .dir-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 13px;
    color: var(--ink);
    transition: background 150ms;
    user-select: none;
  }

  .dir-item:hover {
    background: var(--bg2);
  }

  .dir-item.active {
    background: var(--accent-soft);
    color: var(--accent);
  }

  .dir-toggle {
    width: 16px;
    text-align: center;
    font-size: 10px;
    color: var(--muted);
    cursor: pointer;
    flex-shrink: 0;
  }

  .dir-toggle:hover {
    color: var(--ink);
  }

  .dir-icon {
    font-size: 14px;
    flex-shrink: 0;
  }

  .dir-name {
    flex: 1;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .dir-check {
    color: var(--accent);
    font-size: 13px;
    flex-shrink: 0;
  }

  .dir-loading,
  .dir-empty {
    padding: 24px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }

  /* ---- 批量重命名对话框 ---- */
  .rename-dialog {
    width: 100%;
    max-width: 560px;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    background: var(--bg2);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
    padding: 20px 24px;
    animation: pop 200ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  .rename-dialog h2 {
    margin: 0 0 6px;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
  }

  .rename-template-section,
  .rename-start-section {
    margin-bottom: 14px;
  }

  .rename-suffix-section {
    margin-bottom: 14px;
  }

  .rename-checkbox {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--muted);
    cursor: pointer;
    user-select: none;
  }

  .rename-checkbox input[type='checkbox'] {
    accent-color: var(--accent, #7b73ff);
  }

  .rename-label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .rename-input {
    width: 100%;
    height: 36px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-soft);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
  }

  .rename-input:focus {
    outline: none;
    border-color: var(--accent);
  }

  .rename-vars {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 8px;
  }

  .rename-var-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 24px;
    padding: 0 8px;
    border: 1px solid var(--rule);
    border-radius: var(--radius-full);
    background: var(--bg-soft);
    color: var(--accent);
    font-size: 11.5px;
    font-family: monospace;
    transition: all 150ms;
  }

  .rename-var-chip:hover {
    border-color: var(--accent);
    background: var(--accent-soft);
  }

  .rename-var-desc {
    color: var(--muted);
    font-family: inherit;
    font-size: 10.5px;
  }

  .rename-index-input {
    width: 80px;
    height: 36px;
    padding: 0 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-soft);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
  }

  .rename-index-input:focus {
    outline: none;
    border-color: var(--accent);
  }

  .rename-preview-section {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    margin-bottom: 14px;
  }

  .rename-preview-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 6px;
  }

  .btn-sm {
    height: 26px;
    padding: 0 10px;
    font-size: 11.5px;
  }

  .rename-preview-table {
    flex: 1;
    max-height: 280px;
    overflow-y: auto;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-soft);
    padding: 4px;
  }

  .rename-preview-empty {
    padding: 24px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }

  .rename-preview-row {
    display: grid;
    grid-template-columns: 1fr 24px 1fr;
    gap: 6px;
    align-items: center;
    padding: 5px 8px;
    border-radius: var(--radius);
    font-size: 12px;
    line-height: 1.4;
  }

  .rename-preview-row:hover {
    background: var(--bg2);
  }

  .rename-preview-header {
    font-weight: 600;
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    border-bottom: 1px solid var(--rule);
    border-radius: 0;
    margin-bottom: 2px;
  }

  .rename-preview-row.error .rp-new {
    color: #ef4444;
  }

  .rp-old {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--muted);
  }

  .rp-arrow {
    text-align: center;
    color: var(--muted);
    font-size: 11px;
  }

  .rp-new {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--ink);
    font-weight: 500;
  }

  /* ---- Toast ---- */
  .toast {
    position: fixed;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 18px;
    background: var(--ink);
    color: #fff;
    border-radius: var(--radius-full);
    font-size: 13px;
    z-index: 2000;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    animation: toast-in 200ms ease;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .toast-undo {
    border: 1px solid rgba(255, 255, 255, 0.6);
    border-radius: var(--radius-full);
    background: transparent;
    color: #fff;
    font: inherit;
    font-size: 12px;
    font-weight: 650;
    padding: 3px 12px;
    cursor: pointer;
  }
  .toast-undo:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.16);
  }
  .toast-undo:disabled {
    opacity: 0.55;
    cursor: default;
  }

  @keyframes toast-in {
    from { opacity: 0; transform: translate(-50%, 10px); }
    to { opacity: 1; transform: translate(-50%, 0); }
  }

  .toast.ok {
    background: var(--ok);
  }

  .toast.err {
    background: #ff3b30;
  }

  /* ---- 单项右键菜单 ---- */
  .item-ctx-menu {
    position: fixed;
    z-index: 10000;
    min-width: 160px;
    max-width: 240px;
    max-height: calc(100vh - 24px);
    overflow-y: auto;
    padding: 4px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    animation: pop 120ms ease;
  }

  .item-ctx-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border: none;
    background: none;
    color: var(--ink);
    font-size: 12.5px;
    text-align: left;
    cursor: pointer;
    border-radius: var(--radius);
    transition: background 0.15s, color 0.15s;
  }

  .item-ctx-item:hover:not(:disabled) {
    background: var(--bg-soft);
  }

  .item-ctx-item:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .item-ctx-item.ai-item {
    color: var(--accent);
  }

  .item-ctx-item.convert-item {
    color: var(--amber, #f5b942);
  }

  .item-ctx-item.danger {
    color: #f87171;
  }
  .item-ctx-item.danger:hover:not(:disabled) {
    background: rgba(239, 68, 68, 0.12);
    color: #f87171;
  }

  .item-ctx-item.ai-item:hover:not(:disabled) {
    background: var(--accent-soft);
  }
</style>
