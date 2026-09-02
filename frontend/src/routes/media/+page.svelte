<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { browser } from '$app/environment';
  import { goto, replaceState, afterNavigate } from '$app/navigation';
  import { page as pageStore } from '$app/stores';
  import { mediaApi, normalizeMedia, type Media, type MediaFacets, type MediaHomeResponse, type MediaPayload, type MediaSortField } from '$lib/api/media';
  import { librariesApi, type Library } from '$lib/api/libraries';
  import { tagsApi, type Tag, flattenTags } from '$lib/api/tags';
  import { client } from '$lib/api/client';
  import { seriesApi, type Series } from '$lib/api/series';
  import { navigation } from '$lib/stores/navigation.svelte';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { mediaScroll } from '$lib/stores/mediaScroll.svelte';
  import { pageList, maxVisiblePages as maxVisiblePagesFor, MEDIA_PAGER_METRICS } from '$lib/utils/pagination';
  import FilterBar from '$lib/components/media/FilterBar.svelte';
  import PosterWall from '$lib/components/media/PosterWall.svelte';
  import SeriesWall from '$lib/components/media/SeriesWall.svelte';
  import UnifiedWall, { type UnifiedItem } from '$lib/components/media/UnifiedWall.svelte';
  import ListView from '$lib/components/media/ListView.svelte';
  import TimelineView from '$lib/components/media/TimelineView.svelte';
  import WatchCenter from '$lib/components/media/WatchCenter.svelte';
  import {
    type FilterState,
    type SortState,
    type SortField,
    type ViewMode,
    type ResolutionFilter,
    type DurationFilter,
    type FilterOptions,
    type ContentSection,
    resolutionBucket
  } from '$lib/components/media/types';

  // ---- URL 状态持久化 ----
  // 将 filter/sort/view/page/searchQuery 同步到 URL query parameters
  // 使页面可分享、可刷新恢复
  function parseFilterFromUrl(sp: URLSearchParams): FilterState {
    const f: FilterState = {};
    const type = sp.get('type');
    if (type) f.type = type;
    const genre = sp.get('genre');
    if (genre) f.genre = genre;
    const country = sp.get('country');
    if (country) f.country = country;
    const year = sp.get('year');
    if (year) f.year = Number(year);
    const resolution = sp.get('resolution');
    if (resolution) f.resolution = resolution as ResolutionFilter;
    const ratingMin = sp.get('rating_min');
    if (ratingMin) f.ratingMin = Number(ratingMin);
    const duration = sp.get('duration');
    if (duration) f.duration = duration as DurationFilter;
    const tags = sp.get('tags');
    if (tags) f.tags = tags.split(',').filter(Boolean);
    return f;
  }

  function parseSortFromUrl(sp: URLSearchParams): SortState {
    const field = (sp.get('sort') as SortField) || 'created_at';
    const order = (sp.get('order') as 'asc' | 'desc') || 'desc';
    return { field, order };
  }

  function buildUrlQuery(): URLSearchParams {
    const sp = new URLSearchParams();
    if (pageMode === 'center') {
      // 显式携带 mode=center：详情/播放器返回（history.back / from 参数）时
      // URL 保留观看中心标记，避免回退后被当作媒体库视图。
      sp.set('mode', 'center');
      return sp;
    }
    sp.set('mode', 'library');
    if (section !== 'all') sp.set('section', section);
    if (filter.type) sp.set('type', filter.type);
    if (filter.genre) sp.set('genre', filter.genre);
    if (filter.country) sp.set('country', filter.country);
    if (filter.year !== undefined) sp.set('year', String(filter.year));
    if (filter.resolution) sp.set('resolution', filter.resolution);
    if (filter.ratingMin) sp.set('rating_min', String(filter.ratingMin));
    if (filter.duration) sp.set('duration', filter.duration);
    if (filter.tags?.length) sp.set('tags', filter.tags.join(','));
    if (sort.field !== 'created_at' || sort.order !== 'desc') {
      sp.set('sort', sort.field);
      sp.set('order', sort.order);
    }
    if (view !== 'mixed') sp.set('view', view);
    if (searchQuery) sp.set('q', searchQuery);
    return sp;
  }

  let urlSyncing = false;
  // SvelteKit 路由初始化前调用 replaceState 会抛出异常，用 afterNavigate 标记就绪
  let routerReady = $state(false);
  afterNavigate(() => {
    routerReady = true;
  });
  // 在 effect 外捕获 pathname，避免 $pageStore.url 变化触发循环
  const mediaPathname = $pageStore.url.pathname;
  $effect(() => {
    // 追踪所有需要同步到 URL 的状态（page 由无限滚动内部管理，不同步）
    void filter;
    void sort;
    void section;
    void view;
    void searchQuery;
    void pageMode;
    if (urlSyncing || !routerReady) return;
    urlSyncing = true;
    const sp = buildUrlQuery();
    const qs = sp.toString();
    replaceState(qs ? `${mediaPathname}?${qs}` : mediaPathname, {});
    urlSyncing = false;
  });

  // ---- 状态（从 URL 初始化）----
  // 关键：popstate（详情/播放器返回）重挂载本组件时，SvelteKit 的 page store 可能
  // 只恢复 pathname 而丢失 query（实测 $page.url=/media 而 location=/media?mode=library）。
  // 若用它初始化，pageMode 会退回 center，URL 同步 effect 再把恢复的历史条目
  // replaceState 成 mode=center——表现为"从详情/播放器返回总是落在观看中心"。
  // 浏览器在派发 popstate 前就已更新 location，client 端以 location 为准（ground truth）；
  // SSR/水合时两者描述同一 URL，值一致，无失配风险。
  const initialParams = browser
    ? new URLSearchParams(window.location.search)
    : $pageStore.url.searchParams;
  let pageMode = $state<'center' | 'library'>(
    initialParams.get('mode') === 'library' || initialParams.has('view') || initialParams.has('section')
      ? 'library'
      : 'center'
  );
  const initialSection = initialParams.get('section') as ContentSection | null;
  let section = $state<ContentSection>(
    initialSection && ['all', 'movie', 'tv', 'image', 'audio'].includes(initialSection)
      ? initialSection
      : 'all'
  );
  const initialIsTv = initialSection === 'tv';
  let filter = $state<FilterState>(initialIsTv ? {} : parseFilterFromUrl(initialParams));
  let sort = $state<SortState>(initialIsTv ? { field: 'created_at', order: 'desc' } : parseSortFromUrl(initialParams));
  // 视图模式：URL 优先（书签/分享），localStorage 兜底——解决从详情页返回时
  // 若 URL 未保留 view 参数，列表/时间轴视图被重置回海报墙的问题。
  const VIEW_STORAGE_KEY = 'vitoice.media.view';
  let view = $state<ViewMode>(
    (initialParams.get('view') as ViewMode) ||
      (browser ? (localStorage.getItem(VIEW_STORAGE_KEY) as ViewMode) : '') ||
      'mixed'
  );
  $effect(() => {
    if (browser) localStorage.setItem(VIEW_STORAGE_KEY, view);
  });
  // 仅当 URL 明确请求 mode=center（点击 logo 跳 /media?mode=center）时才回到观看中心；
  // 其它不带 mode 参数的导航（详情返回、媒体库视图等）一律不干预，从而保留媒体库视图记忆。
  // 用 afterNavigate 而非 $effect：$effect 追踪 $pageStore.url 会在 replaceState 往返中
  // 读到过期 searchParams（点击侧边栏 → URL 同步为 mode=library → page store 异步发射
  // 仍带 mode=center 的快照 → 把 pageMode 翻回 center，表现为"侧边栏点击没反应"）。
  // afterNavigate 只在真实导航（goto/history）时触发，replaceState 不触发，无此竞态。
  afterNavigate((nav) => {
    const sp = (nav.to?.url ?? $pageStore.url).searchParams;
    if (sp.get('mode') === 'center' && pageMode !== 'center') pageMode = 'center';
  });
  let page = $state(1); // 无限滚动：当前已加载到的页数，由 loadMedia/loadMore 内部维护
  let pageSize = $state(60);
  const DENSITY_STORAGE_KEY = 'vitoice.media.density';
  let density = $state(
    browser ? Math.min(220, Math.max(132, Number(localStorage.getItem(DENSITY_STORAGE_KEY)) || 180)) : 180
  );
  $effect(() => {
    if (browser) localStorage.setItem(DENSITY_STORAGE_KEY, String(density));
  });
  // ---- 无限滚动状态 ----
  let hasMore = $state(true);       // 还有下一页可加载
  let loadingMore = $state(false);  // 正在追加下一页（防重复触发）
  let loadMoreError = $state(false); // 追加失败，底部显示重试
  let sentinelEl = $state<HTMLElement | null>(null);

  let items = $state<Media[]>([]);
  let seriesItems = $state<Series[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let homeData = $state<MediaHomeResponse | null>(null);
  let homeLoading = $state(false);
  let homeError = $state<string | null>(null);
  let recommendationSeed = 0;

  async function loadHome(refreshRecommendations = false): Promise<void> {
    homeLoading = true;
    homeError = null;
    if (refreshRecommendations) recommendationSeed += 1;
    try {
      const next = await mediaApi.home(recommendationSeed);
      if (refreshRecommendations && homeData) {
        homeData = { ...homeData, recommendations: next.recommendations };
      } else {
        homeData = next;
      }
    } catch (e) {
      homeError = e instanceof Error ? e.message : '请稍后重试';
    } finally {
      homeLoading = false;
    }
  }

  // 从详情/播放返回：首帧直接用快照渲染，避免"空状态/骨架屏 → 请求 → 恢复"的刷新感。
  // 不清空 mediaScroll——loadMedia 挂载首跑会检测到快照并走完整恢复逻辑（幂等，
  // 含锚点对齐与图片加载修正），且不发请求、不覆盖快照。
  if (browser && mediaScroll.savedItems) {
    items = mediaScroll.savedItems;
    seriesItems = mediaScroll.savedSeries ?? [];
    page = mediaScroll.page || 1;
    hasMore = mediaScroll.savedItems.length >= pageSize;
  }

  // 搜索（防抖）—— 从 URL 初始化
  let searchInput = $state(initialIsTv ? '' : (initialParams.get('q') || ''));
  let searchQuery = $state(initialIsTv ? '' : (initialParams.get('q') || ''));
  let searchDebounce: ReturnType<typeof setTimeout> | null = null;

  function onSearchInput(e: Event): void {
    searchInput = (e.target as HTMLInputElement).value;
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      const v = searchInput.trim();
      if (v !== searchQuery) {
        searchQuery = v;
        page = 1;
      }
    }, 300);
  }

  let libraries = $state<Library[]>([]);
  let tags = $state<Tag[]>([]);
  let allFiltered = $state<Media[]>([]); // 客户端分页时的完整结果
  let filterOptions = $state<FilterOptions>({ genres: [], countries: [], years: [] });
  let facets = $state<MediaFacets | null>(null);
  let lastFacetLibKey = ''; // 避免换库时重复请求 facets
  let mediaContextReady = $state(false);

  const libraryMap = $derived(
    Object.fromEntries(libraries.map((l) => [l.id, l.name]))
  );

  // 当前导航库是否为电视剧库（scrape_mode === 'tv'）
  const currentLibrary = $derived.by(() => {
    if (navigation.current.type !== 'library') return null;
    return libraries.find((l) => l.id === navigation.current.value) ?? null;
  });
  const isTvLibrary = $derived(currentLibrary?.scrape_mode === 'tv');

  // 媒体库视图下分类计数与标签筛选按当前库刷新；观看中心/全部媒体则为全局统计。
  const facetLibraryId = $derived(
    pageMode === 'library' && navigation.current.type === 'library'
      ? navigation.current.value
      : undefined
  );

  // 是否存在任何 TV 库（用于"全部媒体"模式决定是否加载 Series）
  const hasTvLibraries = $derived(
    libraries.some((l) => l.scrape_mode === 'tv')
  );

  // 先声明 showSeriesInAll 所依赖的派生值，避免"声明前使用"的 TS 错误
  const navNode = $derived(navigation.current);
  const clientFilterActive = $derived(!!filter.resolution || !!filter.duration);
  // 是否有激活的筛选/搜索（用于"无结果"空态文案区分）
  const hasActiveFilter = $derived(
    !!searchQuery.trim() ||
      !!filter.type ||
      !!filter.genre ||
      !!filter.country ||
      filter.year != null ||
      !!filter.resolution ||
      filter.ratingMin != null ||
      !!filter.duration ||
      (filter.tags ?? []).length > 0
  );
  const smartFolderMode = $derived(navNode.type === 'smartfolder');

  // "全部媒体"模式下且存在 TV 库时，启用混合展示（Series + 独立媒体）
  const showSeriesInAll = $derived(
    section === 'all' && navNode.type === 'all' && hasTvLibraries && !clientFilterActive && !smartFolderMode
  );
  const showSeriesOnly = $derived(
    section === 'tv' || (section === 'all' && isTvLibrary && navNode.type === 'library')
  );

  // 混合展示的统一列表（Series + 独立媒体合并为一个数组）
  const unifiedItems = $derived.by<UnifiedItem[]>(() => {
    if (!showSeriesInAll) return [];
    const seriesPart: UnifiedItem[] = seriesItems.map((s) => ({ kind: 'series', data: s }));
    const mediaPart: UnifiedItem[] = items.map((m) => ({ kind: 'media', data: m }));
    return [...seriesPart, ...mediaPart];
  });

  const tagMap = $derived(
    Object.fromEntries(tags.map((t) => [t.id, t.name]))
  );

  const heading = $derived(navNode.label || '全部媒体');

  // ---- 排序选项（内联渲染，active 项带下划线） ----
  const sortOptions: { field: SortField; label: string }[] = [
    { field: 'created_at', label: '添加时间' },
    { field: 'filename', label: '标题' },
    { field: 'rating', label: '评分' },
    { field: 'duration', label: '时长' },
    { field: 'progress', label: '进度' }
  ];

  // ---- 排序字段映射到 API ----
  const sortFieldMap: Record<SortState['field'], MediaSortField> = {
    created_at: 'created_at',
    filename: 'filename',
    rating: 'rating',
    duration: 'duration',
    progress: 'updated_at' // 进度无独立字段，以最近更新代理
  };

  // 智能文件夹模式走客户端分页（preview 端点不支持服务端筛选）
  const clientPaginate = $derived(smartFolderMode);

  const totalPages = $derived(
    clientPaginate ? Math.max(1, Math.ceil(allFiltered.length / pageSize)) : Math.max(1, Math.ceil(total / pageSize))
  );

  // ---- 加载辅助 ----
  let reqId = 0;
  // 快照恢复窗口期哨兵：返回媒体页后的一小段时间内，挂载期其余在途 loadMedia 的
  // 响应不得落地覆盖快照（否则锚点卡片消失、位置恢复失败）。窗口期内：
  //   - effect 层吞掉 revision/sig 变化（避免再发新请求）
  //   - loadMedia 响应层丢弃在途请求（myId 匹配但仍在窗口期内 → return）
  let snapshotGuardUntil = 0;

  function buildApiParams() {
    const p: Record<string, unknown> = {};
    if (navNode.type === 'library') p.library_id = navNode.value;
    if (navNode.type === 'favorite') p.favorite = true;
    if (navNode.type === 'continue') p.in_progress = true;
    // 'recent' uses default sort (created_at desc) — no special param needed
    // 合并标签：导航标签 + 筛选标签
    const navTags = navNode.type === 'tag' ? [navNode.value] : [];
    const filterTags = filter.tags ?? [];
    const mergedTags = Array.from(new Set([...navTags, ...filterTags]));
    if (mergedTags.length) {
      p.tags = mergedTags;
      if (mergedTags.length > 1) p.tag_match = 'all';
    }
    if (section === 'movie') {
      p.type = 'video';
      p.has_series = false;
    } else if (section === 'image') {
      p.type = 'image';
    } else if (section === 'audio') {
      p.type = 'audio';
    } else if (filter.type) {
      p.type = filter.type;
    }
    if (filter.genre) p.genre = filter.genre;
    if (filter.country) p.country = filter.country;
    if (filter.year !== undefined) p.year = filter.year;
    if (filter.ratingMin) p.rating_min = filter.ratingMin;
    if (searchQuery) p.q = searchQuery;

    // 分辨率筛选下沉到服务端
    if (filter.resolution) {
      switch (filter.resolution) {
        case '4k': p.resolution_min = 2160; break;
        case '1080p': p.resolution_min = 1080; p.resolution_max = 2159; break;
        case '720p': p.resolution_min = 720; p.resolution_max = 1079; break;
        case '480p': p.resolution_min = 480; p.resolution_max = 719; break;
        case 'other': p.resolution_max = 479; break;
      }
    }

    // 时长筛选下沉到服务端
    if (filter.duration) {
      switch (filter.duration) {
        case 'short': p.duration_max = 600; break;
        case 'medium': p.duration_min = 600; p.duration_max = 3600; break;
        case 'long': p.duration_min = 3600; break;
      }
    }

    p.sort = sortFieldMap[sort.field];
    p.order = sort.order;
    return p;
  }

  function applyClientFilters(list: Media[]): Media[] {
    return list.filter((m) => {
      if (filter.resolution) {
        if (resolutionBucket(m.width, m.height) !== filter.resolution) return false;
      }
      if (filter.duration && m.duration) {
        const d = m.duration;
        if (filter.duration === 'short' && d >= 600) return false;
        if (filter.duration === 'medium' && (d < 600 || d > 3600)) return false;
        if (filter.duration === 'long' && d <= 3600) return false;
      }
      return true;
    });
  }

  function paginate(list: Media[]): Media[] {
    const start = (page - 1) * pageSize;
    return list.slice(start, start + pageSize);
  }

  async function loadMedia(): Promise<void> {
    // 从详情/播放返回（快照在）：顶层已用快照渲染首帧，这里直接走完整恢复
    // （锚点对齐 + 图片加载修正 + 窗口哨兵）并返回，不发请求——避免挂载首跑
    // 请求的响应短暂覆盖快照（时间轴全量多请求尤其明显）造成界面刷新感。
    if (mediaScroll.savedItems) {
      restoreFromSnapshot();
      return;
    }
    const myId = ++reqId;
    // reload 语义：重置到第 1 页，并复位无限滚动状态
    page = 1;
    hasMore = true;
    loadingMore = false;
    loadMoreError = false;
    loading = true;
    error = null;
    try {
      // 电视剧库：加载剧列表而非单集
      if (showSeriesOnly && !smartFolderMode) {
        const libraryId = navNode.type === 'library' ? navNode.value : undefined;
        const seriesRes = await seriesApi.list(libraryId, page, pageSize);
        if (myId !== reqId || Date.now() < snapshotGuardUntil) return;
        seriesItems = seriesRes.items ?? [];
        total = seriesRes.total ?? 0;
        items = [];
        allFiltered = [];
        hasMore = (seriesRes.items ?? []).length >= pageSize;
        return;
      }

      // "全部媒体"模式 + 存在 TV 库：同时加载 Series 和非 Series 媒体
      if (showSeriesInAll) {
        const [seriesRes, mediaRes] = await Promise.all([
          seriesApi.list(undefined, 1, 200),
          mediaApi.list({ ...buildApiParams(), page, page_size: pageSize, exclude_series: true }),
        ]);
        if (myId !== reqId || Date.now() < snapshotGuardUntil) return;
        seriesItems = seriesRes.items ?? [];
        items = mediaRes.items ?? [];
        total = (seriesRes.total ?? 0) + (mediaRes.total ?? 0);
        allFiltered = [];
        hasMore = (mediaRes.items ?? []).length >= pageSize;
        return;
      }

      seriesItems = [];

      if (smartFolderMode) {
        // F1 fix: the preview endpoint returns raw MediaResponse rows
        // (file_name/poster_path/thumbnail_path), which PosterWall/ListView
        // read as filename/poster/thumbnail — normalize so cards render.
        const preview = await client.get<Partial<MediaPayload>[]>(
          `/smart-folders/${navNode.value}/preview`
        );
        if (myId !== reqId || Date.now() < snapshotGuardUntil) return;
        const normalized = (preview ?? []).map(normalizeMedia);
        const filtered = applyClientFilters(normalized);
        allFiltered = filtered;
        if (view === 'timeline') {
          // 时间轴：智能文件夹也全量展示（年份组必须完整）
          items = filtered;
          total = filtered.length;
          hasMore = false;
        } else {
          items = paginate(filtered);
          total = filtered.length;
          hasMore = items.length < allFiltered.length;
        }
      } else {
        // 时间轴按年份分组展示，分组完整性依赖完整数据集——必须全量加载。
        // 后端 page_size 上限 200，循环拉取直到拿满 total（桌面端数据量小，可接受）。
        if (view === 'timeline') {
          const bigParams = { ...buildApiParams(), page: 1, page_size: 200 };
          const first = await mediaApi.list(bigParams);
          if (myId !== reqId || Date.now() < snapshotGuardUntil) return;
          let all = first.items ?? [];
          total = first.total ?? 0;
          const pages = Math.ceil(total / 200);
          for (let p = 2; p <= pages && p <= 20; p++) {
            const next = await mediaApi.list({ ...bigParams, page: p });
            if (myId !== reqId || Date.now() < snapshotGuardUntil) return;
            all = [...all, ...(next.items ?? [])];
          }
          allFiltered = [];
          items = all;
          hasMore = false;
        } else {
          const params = { ...buildApiParams(), page, page_size: pageSize };
          const res = await mediaApi.list(params);
          if (myId !== reqId || Date.now() < snapshotGuardUntil) return;
          allFiltered = [];
          items = res.items ?? [];
          total = res.total ?? 0;
          hasMore = (res.items ?? []).length >= pageSize;
        }
      }
    } catch (e) {
      if (myId !== reqId || Date.now() < snapshotGuardUntil) return;
      error = '加载媒体失败，请检查后端服务是否运行';
      items = [];
      seriesItems = [];
      total = 0;
      allFiltered = [];
      hasMore = false;
    } finally {
      if (myId === reqId) loading = false;
      // 从详情/系列页返回：恢复离开时的滚动位置（快照恢复 / 补页兜底）
      if (myId === reqId && (mediaScroll.top > 0 || mediaScroll.anchorId || mediaScroll.savedItems)) {
        restoreFromSnapshot();
      }
    }
  }

  // 滚动快照诊断日志：仅开发构建输出，生产构建零开销。
  function scrollDebug(...args: unknown[]): void {
    if (import.meta.env.DEV) console.log('[scroll]', ...args);
  }

  // 恢复离开媒体页时的滚动状态。
  // 调用时机：
  //   ① loadMedia 开头——返回时快照已在（顶层已用快照渲染首帧），直接恢复且不发请求，
  //      避免"挂载首跑请求 → 响应短暂覆盖快照 → 再恢复"造成的界面刷新感；
  //   ② loadMedia finally——兜底（其他路径遗留的滚动状态）。
  function restoreFromSnapshot(): void {
    scrollDebug('restoring', { top: mediaScroll.top, page: mediaScroll.page, anchorId: mediaScroll.anchorId, hasSnapshot: !!mediaScroll.savedItems, reqId });
    const target = mediaScroll.top;
    const targetPages = mediaScroll.page;
    const anchorId = mediaScroll.anchorId;
    const anchorOffset = mediaScroll.anchorOffset;
    const savedItems = mediaScroll.savedItems;
    const savedSeries = mediaScroll.savedSeries;
    mediaScroll.top = 0;
    mediaScroll.page = 0;
    mediaScroll.anchorId = '';
    mediaScroll.anchorOffset = 0;
    mediaScroll.savedItems = null;
    mediaScroll.savedSeries = null;

    // 滚动到锚点卡片（数据与离开时一致时，位置直接精确映射）
    const restoreScroll = (): void => {
      const el = document.querySelector<HTMLElement>('.media-content');
      if (!el) return;
      if (anchorId) {
        const card = el.querySelector<HTMLElement>(`[data-id="${anchorId}"]`);
        if (card) {
          const cardAbsTop =
            card.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop;
          el.scrollTop = Math.max(0, cardAbsTop - anchorOffset);
          scrollDebug('anchored', { anchorId, cardAbsTop, anchorOffset, scrollTop: el.scrollTop });
          return;
        }
        scrollDebug('anchor card NOT FOUND', anchorId, '| items:', items.length, '| inItems:', items.some((m) => String(m.id) === anchorId), '| page:', page, '| total:', total);
      }
      if (target > 0) {
        const max = el.scrollHeight - el.clientHeight;
        if (max > 0) el.scrollTop = Math.min(target, max);
        scrollDebug('scrollTop fallback', { target, max, scrollTop: el.scrollTop });
      }
    };

    if (savedItems) {
      // 快照恢复（桌面端）：直接还原离开时的数据，渲染/布局与离开时一致。
      // 滚动时机：图片加载前后卡片比例会变（PosterWall 默认比例→实际比例），
      // 布局高度跳变会导致 scrollTop 错位——所以"先滚到大致位置，再随每张图片
      // 加载完成实时锚点修正，全部就绪后最终对齐"（业界 Layout Stabilizer 思路）。
      scrollDebug('snapshot restore', { n: savedItems.length, anchorId, inItems: savedItems.some((m) => String(m.id) === anchorId), targetPages });
      items = savedItems;
      seriesItems = savedSeries ?? [];
      page = targetPages;
      hasMore = savedItems.length >= pageSize;
      // 关键：返回时侧边栏 afterNavigate 会触发 librariesStore.reload() → revision++，
      // 若不同步，响应式 effect 会把快照恢复的列表再 loadMedia 重置回第一页（覆盖快照，
      // 锚点卡片随之消失）——这正是日志里 "anchor card NOT FOUND + max 骤减" 的原因。
      lastRev = librariesStore.revision;
      // 返回时组件重建会额外发出在途 loadMedia（settingsStore 异步加载完成 →
      // showRestricted 变化、reload 的 revision++ 在恢复之后到达等），其响应（第一页
      // 60 条）若落地会用 60 条覆盖快照（诊断日志：anchored 对齐成功后突现 NOT FOUND +
      // items 回到 60）。设置恢复窗口期哨兵做双保险：
      //   ① effect 层：窗口内 revision/sig 变化一律吞掉（同步基准，之后不再重跑）；
      //   ② 响应层：窗口内到达的 loadMedia 响应一律丢弃（myId 不匹配即 return）。
      snapshotGuardUntil = Date.now() + 800;
      loading = false;
      requestAnimationFrame(() => {
        restoreScroll();
        const el = document.querySelector<HTMLElement>('.media-content');
        if (!el) return;
        let settled = false;
        let pending = 0;
        const realign = (): void => { if (!settled) restoreScroll(); };
        const onImgDone = (): void => {
          pending--;
          if (pending <= 0) {
            settled = true;
            restoreScroll();
          } else {
            realign();
          }
        };
        for (const img of Array.from(el.querySelectorAll('img'))) {
          // 已加载（含缓存）的图片不参与等待
          if (img.complete && img.naturalWidth > 0) continue;
          pending++;
          img.addEventListener('load', onImgDone, { once: true });
          img.addEventListener('error', onImgDone, { once: true });
        }
        if (pending === 0) {
          settled = true; // 所有图片已就绪，布局稳定
          return;
        }
        // 兜底：3s 后强制对齐（避免个别图片一直不加载）
        setTimeout(() => {
          settled = true;
          restoreScroll();
        }, 3000);
      });
    } else {
      // 无快照（极端情况）：补页 + 锚点对齐
      const restoreAfterPages = async (): Promise<void> => {
        let guard = 0;
        while (page < targetPages && hasMore && !loadMoreError && guard < 50) {
          await loadMore();
          guard++;
        }
        requestAnimationFrame(restoreScroll);
      };
      void restoreAfterPages();
    }
  }

  // ---- 无限滚动：滚动到底自动加载下一页 ----
  async function loadMore(): Promise<void> {
    if (loadingMore || loading || !hasMore) return;
    loadingMore = true;
    loadMoreError = false;
    // 竞态守卫：追加期间若发生 reload（筛选/排序/导航变化，reqId 递增），
    // 本追加的 page/items 更新全部作废，避免把旧数据的下一页混进新筛选结果。
    const myReq = reqId;
    const nextPage = page + 1;
    try {
      // 电视剧库：追加剧集列表
      if (showSeriesOnly && !smartFolderMode) {
        const libraryId = navNode.type === 'library' ? navNode.value : undefined;
        const seriesRes = await seriesApi.list(libraryId, nextPage, pageSize);
        if (myReq !== reqId) return;
        page = nextPage;
        seriesItems = [...seriesItems, ...(seriesRes.items ?? [])];
        total = seriesRes.total ?? total;
        hasMore = (seriesRes.items ?? []).length >= pageSize;
        return;
      }
      // "全部媒体" + TV：追加非 Series 媒体（Series 已在第一页拉满 200）
      if (showSeriesInAll) {
        const mediaRes = await mediaApi.list({ ...buildApiParams(), page: nextPage, page_size: pageSize, exclude_series: true });
        if (myReq !== reqId) return;
        page = nextPage;
        items = [...items, ...(mediaRes.items ?? [])];
        hasMore = (mediaRes.items ?? []).length >= pageSize;
        return;
      }
      // 智能文件夹：客户端分页切片追加
      if (smartFolderMode) {
        if (myReq !== reqId) return;
        page = nextPage;
        const start = (nextPage - 1) * pageSize;
        const slice = allFiltered.slice(start, start + pageSize);
        items = [...items, ...slice];
        hasMore = items.length < allFiltered.length;
        return;
      }
      // 普通媒体：追加下一页
      const mediaRes = await mediaApi.list({ ...buildApiParams(), page: nextPage, page_size: pageSize });
      if (myReq !== reqId) return;
      page = nextPage;
      items = [...items, ...(mediaRes.items ?? [])];
      total = mediaRes.total ?? total;
      hasMore = (mediaRes.items ?? []).length >= pageSize;
    } catch {
      // 追加失败：页码不回退，底部显示重试
      if (myReq === reqId) loadMoreError = true;
    } finally {
      loadingMore = false;
    }
  }

  // ---- 响应式加载：筛选/排序/导航/限制内容开关变化时重置到第 1 页并重新加载 ----
  // 用 untrack 包裹 loadMedia：其同步部分会写 loading/error 并通过多个 $derived
  // 读取 libraries 等 state，若被追踪会扩大 effect 依赖面，可能在 libraries
  // 频繁刷新时与 Sidebar 的 reload 形成交叉触发。
  let lastSig = '';
  let lastRev = librariesStore.revision;
  $effect(() => {
    const n = navigation.current;
    const f = filter;
    const s = sort;
    // 注意：page 不能作为本 effect 依赖——loadMore 内部自增 page 用于追加加载，
    // 若此处追踪 page，每次追加都会触发 reload 回第 1 页，形成死循环。
    void pageSize; // 显式追踪每页数量变化（loadMedia 内在 await 后读取，需在此追踪）
    const restricted = settingsStore.showRestricted; // 追踪限制内容开关
    const contextReady = mediaContextReady;
    // 追踪侧边栏数据版本：打标/删除标签等操作(tagOps→reload)后立即刷新列表，
    // 否则当前筛选视图会一直显示旧数据直到用户切页/切筛选。
    const rev = librariesStore.revision;
    if (!contextReady && !mediaScroll.savedItems) return;
    if (rev !== lastRev) {
      lastRev = rev;
      // 快照恢复窗口期内：返回触发的侧边栏 reload 已完成、revision 变化到达，
      // 但快照已就绪，无需重载——吞掉避免覆盖快照（基准已同步，不会重跑）。
      if (Date.now() < snapshotGuardUntil) return;
      untrack(() => loadMedia());
      return;
    }
    const sig = JSON.stringify({ n, f, s, section, restricted, q: searchQuery });
    // 仅在实际状态变化时重新加载——避免 effect 因无关依赖重跑时产生重复请求
    // （否则每次 effect 重跑都无条件 loadMedia，操作频繁时列表被反复刷新）。
    if (sig !== lastSig) {
      lastSig = sig;
      // 同上：窗口期内 settingsStore 异步加载导致的 sig 变化被吞掉
      if (Date.now() < snapshotGuardUntil) return;
      untrack(() => loadMedia());
    }
  });

  // 视图切换（海报墙/列表/时间轴）独立触发重载：不依赖上面 sig 的 JSON 比较——
  // 视图决定加载策略（时间轴全量/其他分页），切换必须可靠地触发 loadMedia。
  let lastView = view;
  $effect(() => {
    const v = view;
    if (lastView !== v) {
      lastView = v;
      if (Date.now() < snapshotGuardUntil) return;
      untrack(() => loadMedia());
    }
  });

  async function loadSidebarData(): Promise<void> {
    const [libs, tgs, fos, facetResult] = await Promise.allSettled([
      librariesApi.list(true),
      tagsApi.list({ noCache: true }),
      mediaApi.getFilterOptions(),
      mediaApi.getFacets(facetLibraryId ? String(facetLibraryId) : undefined),
    ]);
    if (libs.status === 'fulfilled') {
      libraries = libs.value ?? [];
      // Card views read restriction metadata from the shared store. Keep it in
      // sync here as well so masking does not depend on Sidebar load timing.
      librariesStore.libraries = libraries;
    }
    if (tgs.status === 'fulfilled') tags = flattenTags(tgs.value ?? []);
    if (fos.status === 'fulfilled') filterOptions = fos.value ?? { genres: [], countries: [], years: [] };
    if (facetResult.status === 'fulfilled') facets = facetResult.value;
    mediaContextReady = true;
  }

  onMount(() => {
    loadSidebarData();
    void loadHome();
    return () => {
      if (searchDebounce) clearTimeout(searchDebounce);
    };
  });

  // 限制内容开关变化时重新加载侧边栏数据（库列表、标签），并回到第 1 页
  let prevRestrictedSidebar: boolean | null = null;
  $effect(() => {
    const current = settingsStore.showRestricted;
    if (prevRestrictedSidebar !== null && prevRestrictedSidebar !== current) {
      untrack(() => void loadSidebarData());
      page = 1;
    }
    prevRestrictedSidebar = current;
  });

  // 无限滚动触底观察：sentinel 进入视口（提前 600px）即追加下一页。
  // 依赖 sentinelEl 的挂载/卸载自动重建观察器；loadMore 内部有 loadingMore 守卫防重复。
  $effect(() => {
    const el = sentinelEl;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const ob = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          untrack(() => void loadMore());
        }
      },
      { rootMargin: '600px 0px' }
    );
    ob.observe(el);
    return () => ob.disconnect();
  });

  // 导航变化（用户点击侧边栏）时重置到第 1 页，并清除详情返回快照——
  // 否则 loadMedia 顶部检测到 mediaScroll.savedItems 会一直走快照恢复并 return，
  // 新导航（换库/换标签/换快捷入口）永远不加载新数据，表现为"点击没反应"。
  let lastNavKey = '';
  $effect(() => {
    const n = navigation.current;
    const key = `${n.type}:${n.value}`;
    if (lastNavKey !== '' && lastNavKey !== key) {
      page = 1;
      mediaScroll.savedItems = null;
      mediaScroll.savedSeries = null;
      mediaScroll.anchorId = '';
      mediaScroll.anchorOffset = 0;
      snapshotGuardUntil = 0;
    }
    lastNavKey = key;
  });

  // 切换媒体库时按当前库刷新分类计数与标签筛选行——否则 facets 停留全库统计，
  // 表现为"全部始终在全部、后面的按钮/标签不变"。
  $effect(() => {
    const lib = facetLibraryId;
    const key = lib ?? '';
    if (key === lastFacetLibKey) return;
    lastFacetLibKey = key;
    untrack(() => {
      mediaApi.getFacets(lib ? String(lib) : undefined).then((f) => {
        if (f) facets = f;
      });
    });
  });

  // 点击侧边栏（任意导航节点）时，自动从"观看中心"切到"媒体库"——
  // 否则停在观看中心时导航只更新了 store，页面内容不变化，表现为"点击没反应"。
  // lastNavCount 初始化为 -1：挂载首跑只记录基线不触发切换——否则从详情/播放器
  // 返回本页时（navigateCount 已 >0），会被误判为侧边栏点击而强制离开观看中心。
  let lastNavCount = -1;
  $effect(() => {
    const count = navigation.navigateCount;
    if (lastNavCount === -1) {
      lastNavCount = count;
      return;
    }
    if (count > 0 && count !== lastNavCount && pageMode === 'center') {
      pageMode = 'library';
    }
    lastNavCount = count;
  });

  // ---- 事件处理 ----
  function onFilterChange(next: FilterState): void {
    filter = next;
    page = 1;
  }
  function selectSection(next: ContentSection): void {
    if (section === next) return;
    if (next === 'tv') {
      filter = {};
      searchInput = '';
      searchQuery = '';
      sort = { field: 'created_at', order: 'desc' };
    }
    section = next;
    page = 1;
  }
  function toggleTagFilter(tagId: number): void {
    const id = String(tagId);
    const current = filter.tags ?? [];
    const tags = current.includes(id) ? current.filter((tag) => tag !== id) : [...current, id];
    onFilterChange({ ...filter, tags });
  }
  function selectSort(field: SortField): void {
    if (sort.field === field) {
      // 同一字段：切换升降序
      sort = { field, order: sort.order === 'asc' ? 'desc' : 'asc' };
    } else {
      // 新字段默认降序
      sort = { field, order: 'desc' };
    }
    page = 1;
  }
  // 离开媒体页前保存滚动状态：scrollTop + 已加载页数 + 锚点卡片 + 数据快照。
  // 数据快照（桌面端可承受）让返回时列表与离开时完全一致，无需重新请求/补页，
  // 滚动位置一步到位——彻底规避"返回后异步加载导致位置漂移"。
  function saveScrollState(preferId?: string): void {
    const container = document.querySelector<HTMLElement>('.media-content');
    mediaScroll.top = container?.scrollTop ?? 0;
    mediaScroll.page = page;
    mediaScroll.anchorId = '';
    mediaScroll.anchorOffset = 0;
    mediaScroll.savedItems = items;
    mediaScroll.savedSeries = seriesItems;
    if (!container) return;
    // 1) 首选：被点击的卡片（精确对应"用户在看的位置"）
    let card: HTMLElement | null = null;
    if (preferId) {
      card = container.querySelector<HTMLElement>(`[data-id="${preferId}"]`);
    }
    // 2) 兜底：视口内第一个可见卡片
    if (!card) {
      const vTop = container.getBoundingClientRect().top;
      for (const c of container.querySelectorAll<HTMLElement>('[data-id]')) {
        const r = c.getBoundingClientRect();
        if (r.bottom > vTop + 4) {
          card = c;
          break;
        }
      }
    }
    if (card) {
      const vTop = container.getBoundingClientRect().top;
      mediaScroll.anchorId = card.getAttribute('data-id') ?? '';
      // 允许负偏移：滚动位置不齐整时被点击的卡片顶部可能在容器上方（半露裁剪），
      // 此时偏移为负值；截断成 0 会导致恢复后卡片被对齐到容器顶部（偏下）。
      // 恢复侧 scrollTop = cardAbsTop - anchorOffset 自会正确映射（负偏移 → 卡片继续
      // 保持在容器上方相同位置）。
      mediaScroll.anchorOffset = card.getBoundingClientRect().top - vTop;
      scrollDebug('saved', { top: mediaScroll.top, page: mediaScroll.page, anchorId: mediaScroll.anchorId, anchorOffset: mediaScroll.anchorOffset, snapshot: items.length });
    } else {
      scrollDebug('saved (no card)', { top: mediaScroll.top, page: mediaScroll.page, snapshot: items.length });
    }
  }

  function onSelect(media: Media): void {
    saveScrollState(media.id);
    goto(`/detail/${media.id}`);
  }
  // 点击封面直接播放：进播放器，from 带当前 URL（含筛选/页码）——返回时回到原位
  function onPlayMedia(m: Media): void {
    if (m.type === 'image') return;
    saveScrollState(m.id);
    const from = encodeURIComponent(location.pathname + location.search);
    goto(`/player?id=${m.id}&from=${from}`);
  }
  function onSelectSeries(s: Series): void {
    saveScrollState();
    goto(`/series/${s.id}`);
  }
  function gotoPage(p: number): void {
    if (p < 1 || p > totalPages || p === page) return;
    page = p;
    mediaScroll.page = p;
    // 翻页回到内容顶部。用瞬时滚动（默认 behavior）而非 smooth——
    // smooth 动画是异步持续的，列表重渲染会延迟其启动，期间用户滚动/点击
    // 会保存到"动画中途值"，且返回时的滚动恢复也会被动画干扰。
    document.querySelector('.media-content')?.scrollTo({ top: 0 });
  }
  function onPageSizeChange(e: Event): void {
    pageSize = Number((e.target as HTMLSelectElement).value);
    page = 1;
    mediaScroll.page = 1;
  }

  // ---- 自适应可见页数 ----
  // 分页区空间充足时默认展示最多 15 个页码;窗口变窄时按实际宽度缩减
  // (最小 5 个,保证导航可用)。用 ResizeObserver 监听容器宽度实时重算。
  // 页码窗口算法与像素预算见 $lib/utils/pagination(与管理页共用,预算按页面传参)
  let pagerEl = $state<HTMLElement | null>(null);
  let pagerWidth = $state(0);

  const maxVisiblePages = $derived(maxVisiblePagesFor(pagerWidth, MEDIA_PAGER_METRICS));

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

  // 骨架卡片数量
  const skeletonCards = Array.from({ length: 18 });
</script>

<svelte:head><title>{heading} — vitoice</title></svelte:head>

<div class="media-page">
  <!-- 顶部装饰光晕 -->
  <div class="ambient-glow" aria-hidden="true"></div>

  <nav class="page-mode-tabs" aria-label="媒体页面">
    <button class:active={pageMode === 'center'} onclick={() => (pageMode = 'center')}>观看中心</button>
    <button class:active={pageMode === 'library'} onclick={() => (pageMode = 'library')}>媒体库</button>
  </nav>

  {#if pageMode === 'center'}
    <WatchCenter
      data={homeData}
      loading={homeLoading}
      error={homeError}
      onPlay={onPlayMedia}
      onOpenMedia={onSelect}
      onOpenSeries={onSelectSeries}
      onRefreshRecommendations={() => void loadHome(true)}
    />
  {:else}

  <!-- 页头 -->
  <header class="page-header">
    <div class="header-title-row">
      <span class="accent-dot" aria-hidden="true"></span>
      <h1 class="title">{heading}</h1>
    </div>
    <p class="subtitle">
      <span class="count-pill">
        <span class="count-num">{total.toLocaleString('zh-CN')}</span>
        <span class="count-unit">{isTvLibrary ? '部剧' : '项媒体'}</span>
      </span>
    </p>
  </header>

  <nav class="section-tabs" aria-label="媒体分类">
    {#each [
      { id: 'all', label: '全部', count: facets?.all ?? total },
      { id: 'movie', label: '电影', count: facets?.movies ?? 0 },
      { id: 'tv', label: '电视剧', count: facets?.series ?? 0 },
      { id: 'image', label: '图片', count: facets?.images ?? 0 },
      { id: 'audio', label: '音频', count: facets?.audio ?? 0 }
    ] as tab (tab.id)}
      <button
        class="section-tab"
        class:active={section === tab.id}
        aria-current={section === tab.id ? 'page' : undefined}
        onclick={() => selectSection(tab.id as ContentSection)}
      >
        <span>{tab.label}</span>
        <span class="section-count">{tab.count.toLocaleString('zh-CN')}</span>
      </button>
    {/each}
  </nav>

  {#if facets?.tags.length && !showSeriesOnly}
    <div class="tag-filter-row" aria-label="标签筛选">
      <span class="filter-row-label">标签</span>
      {#each facets.tags.slice(0, 6) as tag (tag.id)}
        <button
          class="tag-filter"
          class:active={filter.tags?.includes(String(tag.id))}
          onclick={() => toggleTagFilter(tag.id)}
          title={`${tag.value} · ${tag.count} 项`}
        >
          <span class="tag-color" style:background={tag.color || 'var(--accent)'}></span>
          <span>{tag.value}</span>
          <span class="tag-filter-count">{tag.count}</span>
        </button>
      {/each}
      {#if (filter.tags?.length ?? 0) > 1}
        <span class="tag-match-note">同时匹配 {filter.tags?.length} 个标签</span>
      {/if}
    </div>
  {/if}

  <!-- 工具栏：筛选 + 排序 + 视图切换 -->
  <div class="toolbar">
    <div class="toolbar-left">
      {#if !showSeriesOnly}
        <FilterBar {filter} {filterOptions} onChange={onFilterChange} />
      {/if}
    </div>

    <div class="toolbar-right">
      {#if !showSeriesOnly}
      <!-- 搜索框 -->
      <div class="search-box">
        <svg class="search-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
          <circle cx="7" cy="7" r="4.5"></circle>
          <line x1="10.5" y1="10.5" x2="13.5" y2="13.5" stroke-linecap="round"></line>
        </svg>
        <input
          type="text"
          class="search-input"
          placeholder="搜索标题或文件名…"
          value={searchInput}
          oninput={onSearchInput}
        />
      </div>

      <span class="toolbar-divider" aria-hidden="true"></span>

      <!-- 排序选项：文字标签，active 项有下划线 -->
      <div class="sort-group" role="group" aria-label="排序">
        {#each sortOptions as o (o.field)}
          <button
            class="sort-btn"
            class:active={sort.field === o.field}
            onclick={() => selectSort(o.field)}
            title={o.label}
          >
            <span class="sort-label">{o.label}</span>
            {#if sort.field === o.field}
              <svg class="sort-arrow" viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                {#if sort.order === 'asc'}
                  <polyline points="3,8 6,4 9,8"></polyline>
                {:else}
                  <polyline points="3,4 6,8 9,4"></polyline>
                {/if}
              </svg>
            {/if}
          </button>
        {/each}
      </div>

      <span class="toolbar-divider" aria-hidden="true"></span>
      {/if}
      <!-- 视图切换：3 个 SVG 图标按钮 -->
      <div class="view-switch" role="group" aria-label="视图模式">
        <button
          class="vs-btn"
          class:active={view === 'mixed'}
          title="混合媒体墙"
          aria-pressed={view === 'mixed'}
          onclick={() => (view = 'mixed')}
        >
          <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <rect x="2" y="2" width="5" height="7" rx="1"></rect><rect x="9" y="2" width="5" height="3" rx="1"></rect><rect x="9" y="7" width="5" height="7" rx="1"></rect><rect x="2" y="11" width="5" height="3" rx="1"></rect>
          </svg>
        </button>
        <button
          class="vs-btn"
          class:active={view === 'poster'}
          title="海报墙"
          aria-pressed={view === 'poster'}
          onclick={() => (view = 'poster')}
        >
          <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <rect x="2.25" y="2.25" width="4.75" height="4.75" rx="1.25"></rect>
            <rect x="9" y="2.25" width="4.75" height="4.75" rx="1.25"></rect>
            <rect x="2.25" y="9" width="4.75" height="4.75" rx="1.25"></rect>
            <rect x="9" y="9" width="4.75" height="4.75" rx="1.25"></rect>
          </svg>
        </button>
        <button
          class="vs-btn"
          class:active={view === 'list'}
          title="列表"
          aria-pressed={view === 'list'}
          onclick={() => (view = 'list')}
        >
          <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
            <line x1="2.5" y1="4" x2="13.5" y2="4"></line>
            <line x1="2.5" y1="8" x2="13.5" y2="8"></line>
            <line x1="2.5" y1="12" x2="13.5" y2="12"></line>
          </svg>
        </button>
        <button
          class="vs-btn"
          class:active={view === 'timeline'}
          title="时间轴"
          aria-pressed={view === 'timeline'}
          onclick={() => (view = 'timeline')}
        >
          <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="2" y="3.25" width="12" height="10.5" rx="1.5"></rect>
            <line x1="2" y1="6.25" x2="14" y2="6.25"></line>
            <line x1="5" y1="1.75" x2="5" y2="4"></line>
            <line x1="11" y1="1.75" x2="11" y2="4"></line>
            <line x1="5" y1="9" x2="5" y2="11"></line>
            <line x1="8" y1="9" x2="8" y2="11"></line>
            <line x1="11" y1="9" x2="11" y2="11"></line>
          </svg>
        </button>
      </div>
      <span class="toolbar-divider" aria-hidden="true"></span>
      <label class="density-control" title="调整卡片密度">
        <span>紧凑</span>
        <input type="range" min="132" max="220" step="4" bind:value={density} aria-label="卡片密度" />
        <span>舒展</span>
      </label>
    </div>
  </div>

  <!-- 内容区 -->
  <div class="media-content">
    {#if loading && items.length === 0 && seriesItems.length === 0 && unifiedItems.length === 0}
      <!-- 骨架屏 -->
      <div class="skeleton-grid">
        {#each skeletonCards as _, i}
          <div class="sk-card">
            <div class="sk-thumb skeleton"></div>
            <div class="sk-line skeleton" style="width:{70 + ((i * 13) % 30)}%"></div>
            <div class="sk-line skeleton" style="width:{40 + ((i * 7) % 25)}%;height:8px"></div>
          </div>
        {/each}
      </div>
    {:else if error}
      <div class="state state-error anim-fade-in">
        <svg class="state-icon" viewBox="0 0 48 48" width="44" height="44" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="24" cy="24" r="20"></circle>
          <line x1="24" y1="16" x2="24" y2="28"></line>
          <circle cx="24" cy="33" r="1" fill="currentColor" stroke="none"></circle>
        </svg>
        <div class="state-title">无法加载媒体</div>
        <div class="state-hint">{error}</div>
      </div>
    {:else if showSeriesOnly && seriesItems.length > 0}
      <SeriesWall items={seriesItems} onSelect={onSelectSeries} mode={view} {density} />
    {:else if showSeriesOnly && seriesItems.length === 0}
      <!-- 空状态：电视剧库无剧 -->
      <div class="empty-state anim-fade-in">
        <div class="empty-illustration-wrap">
          <svg class="empty-illustration" viewBox="0 0 240 180" width="220" height="165" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <defs>
              <linearGradient id="cardGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.28"></stop>
                <stop offset="100%" stop-color="var(--accent2)" stop-opacity="0.14"></stop>
              </linearGradient>
              <linearGradient id="playGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="var(--accent)"></stop>
                <stop offset="100%" stop-color="var(--accent-hover)"></stop>
              </linearGradient>
              <radialGradient id="glowGrad" cx="0.5" cy="0.5" r="0.5">
                <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.18"></stop>
                <stop offset="100%" stop-color="var(--accent)" stop-opacity="0"></stop>
              </radialGradient>
            </defs>
            <circle cx="120" cy="92" r="78" fill="url(#glowGrad)"></circle>
            <rect class="card-back" x="78" y="34" width="100" height="124" rx="16" fill="var(--accent)" opacity="0.06"></rect>
            <rect class="card-back2" x="86" y="40" width="100" height="124" rx="16" fill="var(--accent)" opacity="0.05"></rect>
            <rect x="70" y="30" width="100" height="124" rx="15" fill="url(#cardGrad)" stroke="var(--accent)" stroke-opacity="0.38" stroke-width="1.4"></rect>
            <rect x="80" y="40" width="80" height="12" rx="3" fill="var(--accent)" opacity="0.14"></rect>
            <circle cx="86" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <circle cx="94" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <circle cx="102" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <circle cx="110" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <circle cx="118" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <circle cx="126" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <circle cx="134" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <circle cx="142" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <circle cx="150" cy="46" r="1.7" fill="var(--bg-elevated)"></circle>
            <path d="M106 72 L106 112 L140 92 Z" fill="url(#playGrad)"></path>
            <rect x="82" y="126" width="56" height="6" rx="3" fill="var(--accent)" opacity="0.22"></rect>
            <rect x="82" y="138" width="34" height="5" rx="2.5" fill="var(--accent)" opacity="0.12"></rect>
            <circle class="sparkle s1" cx="48" cy="56" r="2.4" fill="var(--accent2)"></circle>
            <circle class="sparkle s2" cx="188" cy="68" r="1.8" fill="var(--accent)"></circle>
            <circle class="sparkle s3" cx="178" cy="142" r="2.2" fill="var(--accent2)"></circle>
            <circle class="sparkle s4" cx="52" cy="132" r="1.6" fill="var(--accent)"></circle>
            <path class="sparkle s5" d="M196 104 L196 110 M193 107 L199 107" stroke="var(--accent2)" stroke-width="1.4" stroke-linecap="round"></path>
          </svg>
        </div>
        <h2 class="empty-title">暂无剧集</h2>
        <p class="empty-desc">扫描电视剧库后，系统将自动按剧名聚合展示。<br/>请确认库中已导入视频文件并完成扫描。</p>
        <a class="empty-cta" href="/libraries">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <polyline points="2,8 6,12 14,4"></polyline>
          </svg>
          <span>前往库管理</span>
        </a>
      </div>
    {:else if showSeriesInAll && unifiedItems.length > 0}
      <UnifiedWall items={unifiedItems} onSelectSeries={onSelectSeries} onSelectMedia={onSelect} mode={view} {density} />
    {:else if showSeriesInAll && unifiedItems.length === 0}
      <div class="state anim-fade-in">
        <div class="state-title">暂无媒体</div>
        <div class="state-hint">请确认已导入媒体文件并完成扫描。</div>
      </div>
    {:else if items.length === 0 && unifiedItems.length === 0}
      <!-- 空状态：非 TV 视图无结果（筛选/搜索无匹配或库为空） -->
      <div class="state anim-fade-in">
        <div class="state-title">{hasActiveFilter ? '没有匹配的媒体' : '暂无媒体'}</div>
        <div class="state-hint">{hasActiveFilter ? '尝试调整筛选条件或搜索关键词。' : '请确认已导入媒体文件并完成扫描。'}</div>
      </div>
    {:else if view === 'mixed' || view === 'poster'}
      <PosterWall {items} onSelect={onSelect} onplay={onPlayMedia} mode={view} {density} />
    {:else if view === 'list'}
      <ListView {items} libraryMap={libraryMap} tagMap={tagMap} onSelect={onSelect} onplay={onPlayMedia} />
    {:else}
      <TimelineView {items} onSelect={onSelect} onplay={onPlayMedia} {density} />
    {/if}
    <!-- 触底哨兵：必须放在滚动容器(.media-content)内部作为最后子元素——
         容器滚动到底时哨兵进入视口触发加载；加载后内容变高哨兵被推离视口，
         再次滚动到底重新触发（交叉状态变化驱动的无限滚动）。 -->
    {#if (items.length > 0 || seriesItems.length > 0 || unifiedItems.length > 0) && !error}
      <div bind:this={sentinelEl} class="infinite-sentinel"></div>
    {/if}
  </div>

  <!-- 无限滚动底部状态条（容器外，固定显示加载状态） -->
  {#if (items.length > 0 || seriesItems.length > 0 || unifiedItems.length > 0) && !error}
    <div class="infinite-footer">
      <div class="infinite-status" aria-live="polite">
        {#if loadingMore}
          <span class="pg-loading">加载中…</span>
        {:else if loadMoreError}
          <button class="pg-retry" onclick={() => void loadMore()}>加载失败，点击重试</button>
        {:else if !hasMore}
          <span class="pg-end">已经到底了 · 共 {total} 项</span>
        {/if}
      </div>
    </div>
  {/if}
  {/if}
</div>

<style>
  .media-page {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    position: relative;
    overflow: hidden;
  }

  .page-mode-tabs {
    position: relative;
    z-index: 3;
    display: flex;
    align-items: center;
    gap: 22px;
    min-height: 44px;
    padding: 0 32px;
    border-bottom: 1px solid var(--rule);
    flex-shrink: 0;
  }

  .page-mode-tabs button {
    position: relative;
    align-self: stretch;
    padding: 0 1px;
    color: var(--muted);
    background: transparent;
    border: 0;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
  }

  .page-mode-tabs button::after {
    content: '';
    position: absolute;
    right: 0;
    bottom: -1px;
    left: 0;
    height: 2px;
    background: transparent;
  }

  .page-mode-tabs button.active { color: var(--ink); }
  .page-mode-tabs button.active::after { background: var(--accent); }

  /* 顶部氛围光晕 */
  .ambient-glow {
    position: absolute;
    top: -120px;
    left: 50%;
    transform: translateX(-50%);
    width: 600px;
    height: 320px;
    background: radial-gradient(
      ellipse at center,
      var(--accent-glow) 0%,
      transparent 70%
    );
    opacity: 0.5;
    pointer-events: none;
    z-index: 0;
  }

  /* ---- 页头 ---- */
  .page-header {
    position: relative;
    z-index: 1;
    padding: 32px 32px 18px;
    flex-shrink: 0;
  }

  .header-title-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .accent-dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background: var(--accent);
    box-shadow: 0 0 12px var(--accent-glow), 0 0 0 3px var(--accent-soft);
    flex-shrink: 0;
  }

  .title {
    margin: 0;
    font-family: var(--font-display);
    font-size: 28px;
    font-weight: 700;
    color: var(--ink);
    letter-spacing: 0;
    line-height: 1.15;
  }

  .subtitle {
    margin: 8px 0 0 20px;
  }

  .section-tabs {
    position: relative;
    z-index: 2;
    display: flex;
    align-items: stretch;
    gap: 4px;
    min-height: 42px;
    margin: 0 32px;
    border-bottom: 1px solid var(--rule);
    overflow-x: auto;
    scrollbar-width: none;
    flex-shrink: 0;
  }

  .section-tabs::-webkit-scrollbar,
  .tag-filter-row::-webkit-scrollbar { display: none; }

  .section-tab {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    min-width: max-content;
    padding: 0 13px;
    border: 0;
    background: transparent;
    color: var(--ink-tertiary);
    font: inherit;
    font-size: 13px;
  }

  .section-tab:hover { color: var(--ink); }
  .section-tab.active { color: var(--ink); font-weight: 600; }
  .section-tab.active::after {
    content: '';
    position: absolute;
    right: 12px;
    bottom: -1px;
    left: 12px;
    height: 2px;
    border-radius: 2px 2px 0 0;
    background: var(--accent);
  }

  .section-count {
    color: var(--muted);
    font-size: 10.5px;
    font-variant-numeric: tabular-nums;
  }

  .section-tab.active .section-count { color: var(--accent); }

  .tag-filter-row {
    position: relative;
    z-index: 3;
    display: flex;
    align-items: center;
    gap: 7px;
    min-height: 42px;
    margin: 0 32px;
    overflow-x: auto;
    flex-shrink: 0;
    scrollbar-width: none;
  }

  .filter-row-label { color: var(--muted); font-size: 11px; margin-right: 2px; }
  .tag-filter {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-width: max-content;
    height: 25px;
    padding: 0 8px;
    border: 1px solid var(--rule);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--ink-tertiary);
    font-size: 11px;
  }

  .tag-filter:hover { color: var(--ink); border-color: var(--muted); }
  .tag-filter.active { color: var(--ink); border-color: var(--accent); background: var(--accent-soft); }
  .tag-color { width: 6px; height: 6px; border-radius: 50%; flex: 0 0 auto; }
  .tag-filter-count { color: var(--muted); font-variant-numeric: tabular-nums; }
  .tag-match-note { min-width: max-content; color: var(--accent); font-size: 10.5px; }

  .count-pill {
    display: inline-flex;
    align-items: baseline;
    gap: 5px;
    padding: 3px 10px;
    background: var(--bg-surface);
    border: 1px solid var(--rule);
    border-radius: var(--radius-full);
  }

  .count-num {
    font-family: var(--font-display);
    font-size: 12.5px;
    font-weight: 600;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
  }

  .count-unit {
    font-size: 11.5px;
    color: var(--ink-tertiary);
  }

  /* ---- 工具栏 ---- */
  .toolbar {
    position: relative;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin: 0 32px;
    padding: 8px 10px 8px 14px;
    background: var(--bg-surface);
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    flex-shrink: 0;
    flex-wrap: wrap;
  }

  .density-control {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 146px;
    color: var(--muted);
    font-size: 10px;
    white-space: nowrap;
  }

  .density-control input { width: 76px; accent-color: var(--accent); }

  .toolbar-left {
    display: flex;
    align-items: center;
    flex: 1 1 auto;
    min-width: 0;
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-shrink: 0;
  }

  .toolbar-divider {
    width: 1px;
    height: 20px;
    background: var(--rule);
    flex-shrink: 0;
  }

  /* 搜索框 */
  .search-box {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-full);
    transition: border-color 150ms;
  }

  .search-box:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .search-icon {
    color: var(--muted);
    flex-shrink: 0;
  }

  .search-input {
    border: none;
    background: none;
    outline: none;
    color: var(--ink);
    font-size: 12.5px;
    width: 160px;
    font-family: inherit;
  }

  .search-input::placeholder {
    color: var(--muted);
  }

  /* 排序组 */
  .sort-group {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .sort-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 28px;
    padding: 0 9px;
    border: none;
    background: none;
    border-radius: var(--radius-sm);
    color: var(--ink-tertiary);
    font-family: var(--font-body);
    font-size: 12.5px;
    font-weight: 450;
    position: relative;
    transition: color var(--dur) var(--ease-out), background var(--dur-fast) var(--ease-out);
  }

  .sort-btn:hover {
    color: var(--ink-secondary);
    background: var(--bg-hover);
  }

  .sort-btn.active {
    color: var(--ink);
    font-weight: 500;
  }

  .sort-btn.active::after {
    content: '';
    position: absolute;
    left: 9px;
    right: 9px;
    bottom: 3px;
    height: 1.5px;
    background: var(--accent);
    border-radius: 1px;
    transform-origin: center;
    animation: underline-in var(--dur) var(--ease-out);
  }

  @keyframes underline-in {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
  }

  .sort-arrow {
    color: var(--accent);
    flex-shrink: 0;
  }

  /* 视图切换分段控件 */
  .view-switch {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 3px;
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    flex-shrink: 0;
  }

  .vs-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 26px;
    border: none;
    background: none;
    border-radius: var(--radius-sm);
    color: var(--ink-tertiary);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out), box-shadow var(--dur) var(--ease-out);
  }

  .vs-btn:hover {
    color: var(--ink-secondary);
    background: var(--bg-hover);
  }

  .vs-btn.active {
    background: var(--accent-soft);
    color: var(--accent);
    box-shadow: var(--shadow-sm), inset 0 0 0 1px var(--accent-soft);
  }

  .vs-btn:active {
    transform: scale(0.94);
  }

  /* ---- 内容区 ---- */
  .media-content {
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px 16px;
    position: relative;
    z-index: 1;
  }

  /* 骨架屏 */
  .skeleton-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 16px;
  }

  .sk-card {
    display: flex;
    flex-direction: column;
    gap: 9px;
  }

  .sk-thumb {
    aspect-ratio: 2 / 3;
    border-radius: var(--radius-md);
  }

  .sk-line {
    height: 10px;
    border-radius: var(--radius-xs);
  }

  /* 通用状态区 */
  .state {
    padding: 100px 24px;
    text-align: center;
    color: var(--ink-secondary);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }

  .state-icon {
    color: var(--danger);
    opacity: 0.8;
    margin-bottom: 4px;
  }

  .state-title {
    font-family: var(--font-display);
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
  }

  .state-hint {
    font-size: 13px;
    color: var(--ink-tertiary);
  }

  /* ---- 空状态 ---- */
  .empty-state {
    padding: 80px 24px 60px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .empty-illustration-wrap {
    margin-bottom: 28px;
    animation: float 5s var(--ease-in-out) infinite;
  }

  @keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
  }

  .empty-illustration {
    display: block;
  }

  .card-back, .card-back2 {
    animation: card-drift 6s var(--ease-in-out) infinite;
  }
  .card-back2 {
    animation-delay: -2s;
  }
  @keyframes card-drift {
    0%, 100% { transform: translate(0, 0); }
    50% { transform: translate(-2px, -2px); }
  }

  .sparkle {
    transform-origin: center;
    animation: twinkle 2.8s var(--ease-in-out) infinite;
  }
  .s1 { animation-delay: 0s; }
  .s2 { animation-delay: 0.6s; }
  .s3 { animation-delay: 1.2s; }
  .s4 { animation-delay: 1.8s; }
  .s5 { animation-delay: 2.4s; }

  @keyframes twinkle {
    0%, 100% { opacity: 0.25; transform: scale(0.85); }
    50% { opacity: 1; transform: scale(1.15); }
  }

  .empty-title {
    margin: 0 0 10px;
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 600;
    color: var(--ink);
    letter-spacing: 0;
  }

  .empty-desc {
    margin: 0 0 28px;
    font-family: var(--font-body);
    font-size: 13.5px;
    line-height: 1.7;
    color: var(--ink-secondary);
    max-width: 360px;
  }

  .empty-cta {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    height: 38px;
    padding: 0 18px;
    background: var(--accent);
    color: #fff;
    font-family: var(--font-display);
    font-size: 13.5px;
    font-weight: 600;
    border-radius: var(--radius-md);
    box-shadow: var(--shadow), 0 0 0 0 var(--accent-glow);
    transition: background var(--dur) var(--ease-out), transform var(--dur) var(--ease-out), box-shadow var(--dur-slow) var(--ease-out);
  }

  .empty-cta:hover {
    background: var(--accent-hover);
    transform: translateY(-1px);
    box-shadow: var(--shadow-md), 0 0 24px var(--accent-glow);
  }

  .empty-cta:active {
    transform: translateY(0);
  }

  /* ---- 分页 ---- */
  /* 无限滚动底部：加载状态 + 每页大小 + 触底哨兵 */
  .infinite-footer {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    min-height: 44px;
    padding: 12px 32px 16px;
    border-top: 1px solid var(--rule-light);
    flex-shrink: 0;
  }

  .infinite-status {
    min-height: 20px;
    display: flex;
    align-items: center;
  }

  .pg-retry {
    background: none;
    border: 1px solid var(--rule);
    color: var(--accent);
    font-size: 12px;
    padding: 4px 12px;
    border-radius: 999px;
    cursor: pointer;
    transition: border-color 200ms;
  }

  .pg-retry:hover {
    border-color: var(--accent);
  }

  .pg-end {
    color: var(--muted);
    font-size: 12px;
  }

  .infinite-sentinel {
    /* 滚动容器内的普通块元素：作为最后子元素位于内容底部 */
    height: 1px;
    pointer-events: none;
    flex-shrink: 0;
  }

  /* 翻页加载指示 */
  .pg-loading {
    font-size: 12px;
    color: var(--muted);
    margin-left: 10px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    animation: fadeIn 160ms ease;
  }

  .pg-loading::before {
    content: '';
    width: 10px;
    height: 10px;
    border: 2px solid var(--rule);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 700ms linear infinite;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* ---- 响应式 ---- */
  @media (max-width: 720px) {
    .page-mode-tabs { padding-inline: 20px; }
    .section-tabs,
    .tag-filter-row { margin-inline: 20px; }
    .density-control { display: none; }
    .page-header { padding: 24px 20px 14px; }
    .toolbar { margin: 0 20px; padding: 8px; }
    .media-content { padding: 20px 20px 12px; }
    .infinite-footer { padding: 12px 20px 16px; }
    .title { font-size: 24px; }
    .sort-group { flex-wrap: wrap; }
    .toolbar-right { flex-wrap: wrap; justify-content: flex-end; }
  }
</style>
