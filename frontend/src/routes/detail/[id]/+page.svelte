<script lang="ts">
  // 详情页 - 单媒体深度信息页
  // 左固定 + 右滚动布局
  // 拆分为子组件：DetailHero / DetailMeta / DetailSegments / DetailTags / DetailLinks / DetailSimilar

  import { onMount, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { mediaApi, type Media, type MediaUrl, type UrlRole, type ScrapeData, type AIRescrapeResponse, isAvMedia, hasNetworkSource, getNetworkSourceUrl } from '$lib/api/media';
  import { librariesApi, type Library } from '$lib/api/libraries';
  import { tagsApi, type Tag, flattenTags } from '$lib/api/tags';
  import { seriesApi, type EpisodeNavigation } from '$lib/api/series';
  import { player } from '$lib/stores/player.svelte';
  import { classifyNetworkUrl, openExternalUrl, isAdultNetworkMedia, extractFancode } from '$lib/utils/network-media';
  import { adultNetworkApi } from '$lib/api/networkSources';
  import TagSelector from '$lib/components/common/TagSelector.svelte';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
  import DetailHero from '$lib/components/detail/DetailHero.svelte';
  import DetailCast from '$lib/components/detail/DetailCast.svelte';
  import DetailWork from '$lib/components/detail/DetailWork.svelte';
  import DetailMeta from '$lib/components/detail/DetailMeta.svelte';
  import DetailSegments from '$lib/components/detail/DetailSegments.svelte';
  import DetailTags from '$lib/components/detail/DetailTags.svelte';
  import DetailLinks from '$lib/components/detail/DetailLinks.svelte';
  import DetailSimilar from '$lib/components/detail/DetailSimilar.svelte';
  import DetailInfo from '$lib/components/detail/DetailInfo.svelte';
  import DetailMediaInfo from '$lib/components/detail/DetailMediaInfo.svelte';
  import { formatResolution, formatSize, formatTime, formatBitrate } from '$lib/utils/format';
  import EditMediaDialog from '$lib/components/manage/EditMediaDialog.svelte';
  import type { Segment, Subtitle } from '$lib/components/detail/types';

  let { params } = $props();
  const id = $derived(params.id);

  // ---- 返回来源页（管理页/媒体页/搜索等），无历史时回退到 /media ----
  function goBack(): void {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      goto('/media');
    }
  }

  // ---- 数据状态 ----
  let media = $state<Media | null>(null);
  let libraries = $state<Library[]>([]);
  let allTags = $state<Tag[]>([]);
  let similar = $state<Media[]>([]);
  let episodeNav = $state<EpisodeNavigation | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let saving = $state(false);

  // ---- 编辑状态 ----
  let titleEditing = $state(false);
  let titleDraft = $state('');
  let titleInput: HTMLInputElement | null = $state(null);

  let descEditing = $state(false);
  let descDraft = $state('');

  let tagSelectorOpen = $state(false);

  // ---- 编辑对话框（更换封面等） ----
  let editDialogOpen = $state(false);
  let editMediaTarget = $state<Media | null>(null);

  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  function showToast(msg: string, type: 'ok' | 'err' = 'ok'): void {
    toast = { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2500);
  }

  // ---- 扩展数据提取（从 metadata） ----
  function readMeta<T>(key: string, fallback: T): T {
    if (!media?.metadata) return fallback;
    const v = (media.metadata as Record<string, unknown>)[key];
    return (v ?? fallback) as T;
  }

  // 描述：优先顶层 description（TMDB 刮削写入），回退 metadata.description / summary
  const description = $derived(
    media?.description ?? readMeta<string>('description', readMeta<string>('summary', ''))
  );
  // 片段：权威数据在后端 segments 表（顶层 media.segments，字段 name/start_time/end_time/color），
  // 经 normalizeMedia 透传；此处映射为组件契约 {id, start, end, label}。
  const segments = $derived(
    (media?.segments ?? []).map((s) => ({
      id: String(s.id),
      start: s.start_time,
      end: s.end_time ?? undefined,
      label: (s.name ?? '').trim() || undefined
    }))
  );
  // 资源链接：从 media.urls 派生（后端 CRUD 接口管理）
  const sourceLinks = $derived(
    media?.urls?.filter((u) => u.url_role === 'source') ?? []
  );
  const referenceLinks = $derived(
    media?.urls?.filter((u) => u.url_role === 'reference') ?? []
  );
  const subtitles = $derived(readMeta<Subtitle[]>('subtitles', []));
  const codec = $derived(readMeta<string>('codec', readMeta<string>('video_codec', '')));
  const fps = $derived(readMeta<number>('fps', readMeta<number>('frame_rate', 0)));
  const bitrate = $derived(readMeta<number>('bitrate', readMeta<number>('bit_rate', 0)));

  const libraryName = $derived(
    libraries.find((l) => l.id === media?.library_id)?.name ?? '—'
  );

  // 标题：优先顶层 title（TMDB 刮削写入），回退 metadata.title / 文件名
  const displayTitle = $derived(
    media?.title ?? readMeta<string>('title', media?.filename ?? '')
  );

  // 是否已有刮削海报（区别于 ffmpeg 缩略图）
  const hasPoster = $derived(!!media?.poster);
  // AV 媒体使用横向封面（JavBus），需不同的海报比例
  const isAv = $derived(media ? isAvMedia(media) : false);

  // ---- 成人网络源（聚合站解析） ----
  const isAdultNet = $derived(media ? isAdultNetworkMedia(media) : false);
  const adultFancode = $derived(
    media ? extractFancode(media.title || media.filename || '') : null
  );
  let refreshingAdult = $state(false);

  // 从聚合站解析并添加为网络源（本地成人文件也可用——标题含番号即可）
  const canAggregateResolve = $derived(
    media ? !!extractFancode(media.title || media.filename || '') : false
  );
  let aggregateResolving = $state(false);

  async function resolveAggregateSource(): Promise<boolean> {
    if (!media || aggregateResolving) return false;
    const fc = extractFancode(media.title || media.filename || '');
    if (!fc) return false;
    aggregateResolving = true;
    try {
      // 走 adult-refresh（按 platform 去重 + 原地刷新过期直链）：
      // 同一 server（vidhide/turboplay/streamwish）已存在的 source 原地更新
      // 签名 URL 并清 is_expired，缺失的 server 才新增——避免每次点击重复
      // 追加导致"越点越多"，同时顺带刷新 36h 过期的直链解决"无效源"。
      const res = await adultNetworkApi.refresh(media.id, fc);
      // 后端解析失败（如 javgg 限流）返回 200 + refresh.status=error——必须显式检查，
      // 否则会显示"新增 0 个"造成解析成功的错觉
      if (res.refresh && res.refresh.status !== 'ok') {
        showToast(res.refresh.message || '解析失败，请稍后再试', 'err');
        return false;
      }
      await reloadMedia();
      const parts: string[] = [];
      if (res.added > 0) parts.push(`新增 ${res.added} 个源`);
      if (res.updated > 0) parts.push(`刷新 ${res.updated} 个已有源`);
      if (res.removed > 0) parts.push(`收敛 ${res.removed} 个重复源`);
      showToast(parts.length > 0 ? `聚合解析完成：${parts.join('、')}` : '解析成功但未发现新源');
      return res.added > 0 || res.updated > 0;
    } catch (e) {
      const status = (e as { status?: number })?.status;
      const detail = (e as { body?: { detail?: string } })?.body?.detail;
      if (status === 403) showToast(detail || '成人网络源功能未开启（设置 → 内容管理）', 'err');
      else showToast(detail || '解析失败', 'err');
      return false;
    } finally {
      aggregateResolving = false;
    }
  }

  // 文件丢失 → 转为网络视频：先确保有可播放的网络源（有番号优先聚合解析），
  // 再调用后端 convert-to-network 完成状态转换（OFFLINE → NETWORK，清除 file_missing）。
  let convertingToNetwork = $state(false);

  async function convertToNetwork(): Promise<void> {
    if (!media || convertingToNetwork) return;
    // 1. 确保有源：无源且标题含番号 → 先聚合解析补源
    if (!hasNetworkSource(media)) {
      const fc = extractFancode(media.title || media.filename || '');
      if (fc) {
        const ok = await resolveAggregateSource();
        if (!ok) return; // 解析失败，停留当前状态
      }
      if (!hasNetworkSource(media)) {
        showToast('暂无网络源：请先通过「从聚合站解析」或「添加链接」添加源链接', 'err');
        return;
      }
    }
    // 2. 转换
    convertingToNetwork = true;
    try {
      const updated = await mediaApi.convertToNetwork(media.id);
      media = updated;
      showToast('已转为网络视频，可继续从网络源播放');
    } catch (e) {
      const detail = (e as { body?: { detail?: string } })?.body?.detail;
      showToast(detail || '转为网络视频失败', 'err');
    } finally {
      convertingToNetwork = false;
    }
  }

  // —— "回收"（删除本地文件）流程 ——
  // 逻辑闭环：本地文件与网络源是两份独立资产，删除也分两次。
  // 第一步删本地文件前，若媒体还没有网络源，先询问用户是否添加，
  // 避免删完本地文件后无法播放。
  let askAddNetworkOpen = $state(false);
  // 标记"先加源、后继续删除流程"：手动链接保存成功后自动移入回收站
  let pendingDeleteAfterLink = $state(false);

  // —— 第一步：本地文件 → 软删除进回收站（磁盘文件不动，回收站二次确认） ——
  function onRecycleClick(): void {
    if (!media) return;
    askAddNetworkOpen = true;
  }

  async function confirmRecycle(): Promise<void> {
    if (!media) return;
    askAddNetworkOpen = false;
    pendingDeleteAfterLink = false;
    try {
      await mediaApi.delete(media.id);
      showToast('已移入回收站（磁盘文件未删除，可到回收站二次确认）');
      setTimeout(() => goto('/manage'), 900);
    } catch {
      showToast('移入回收站失败', 'err');
    }
  }

  function onAskSkipAdd(): void {
    askAddNetworkOpen = false;
    void confirmRecycle();
  }

  async function onAskAddNetwork(): Promise<void> {
    const cur = media;
    if (!cur) return;
    askAddNetworkOpen = false;
    const fc = extractFancode(cur.title || cur.filename || '');
    if (fc) {
      // 能提取番号 → 优先走聚合站解析
      pendingDeleteAfterLink = true;
      const ok = await resolveAggregateSource();
      if (ok) {
        // 解析成功 → 源已就位，移入回收站
        void confirmRecycle();
      } else if (hasNetworkSource(cur)) {
        // 解析报错但媒体已有源（如缓存命中/重复添加）→ 直接移入回收站
        void confirmRecycle();
      } else {
        // 解析失败且仍无源 → 打开手动添加链接（保存后自动移入回收站）
        addResourceLink();
      }
    } else {
      // 无番号 → 手动添加链接
      pendingDeleteAfterLink = true;
      addResourceLink();
    }
  }

  async function refreshAdultSource(): Promise<void> {
    if (!media || !adultFancode || refreshingAdult) return;
    refreshingAdult = true;
    try {
      const res = await adultNetworkApi.refresh(media.id, adultFancode);
      // 后端解析失败（如 javgg 限流）返回 200 + refresh.status=error——必须显式检查，
      // 否则会显示"更新 0 个、新增 0 个"造成刷新成功的错觉
      if (res.refresh && res.refresh.status !== 'ok') {
        showToast(res.refresh.message || '刷新失败，请稍后再试', 'err');
        return;
      }
      await reloadMedia();
      const parts = [`更新 ${res.updated} 个`];
      if (res.added > 0) parts.push(`新增 ${res.added} 个`);
      if (res.removed > 0) parts.push(`收敛 ${res.removed} 个重复`);
      showToast(`已刷新成人源（${parts.join('、')}）`);
    } catch (e) {
      const status = (e as { status?: number })?.status;
      const detail = (e as { body?: { detail?: string } })?.body?.detail;
      if (status === 403) showToast(detail || '成人网络源功能未开启（设置 → 内容管理）', 'err');
      else showToast(detail || '刷新失败', 'err');
    } finally {
      refreshingAdult = false;
    }
  }

  // ---- 刮削详情 ----
  const sd = $derived<ScrapeData | undefined>(media?.scrape_data);
  const hasScrapeData = $derived(!!sd && Object.keys(sd).length > 0);
  const backdropUrl = $derived(
    !isAv && sd?.backdrop_path
      ? media
        ? mediaApi.backdropUrl(media.id, media.updated_at)
        : ''
      : ''
  );
  const tmdbRatingText = $derived(
    sd?.tmdb_rating != null ? sd.tmdb_rating.toFixed(1) : null
  );
  const runtimeText = $derived.by(() => {
    const mins = sd?.runtime_minutes;
    if (!mins) return null;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return h > 0 ? `${h}h ${m}min` : `${m}min`;
  });

  const tagMap = $derived(
    Object.fromEntries(allTags.map((t) => [t.id, t]))
  );

  const mediaTagObjects = $derived(
    (media?.tags ?? [])
      .map((tid) => tagMap[tid])
      .filter((t): t is Tag => !!t)
  );

  // 按类型分组标签（Tag 接口无 type 字段，读取扩展字段）
  function tagType(t: Tag): string {
    const ext = t as Tag & { type?: string; category?: string };
    return ext.type ?? ext.category ?? '通用';
  }

  const groupedTags = $derived.by(() => {
    const map = new Map<string, Tag[]>();
    for (const t of mediaTagObjects) {
      const g = tagType(t);
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(t);
    }
    return Array.from(map.entries()).map(([name, items]) => ({ name, items }));
  });

  // ---- 加载数据 ----
  // F3 fix: a monotonically increasing request id guards against stale
  // responses — rapid prev/next-episode switches can no longer let a slow
  // older request overwrite the current media.
  let loadReqId = 0;
  async function loadMedia(): Promise<void> {
    const myId = ++loadReqId;
    loading = true;
    error = null;
    try {
      const result = await mediaApi.get(id);
      if (myId !== loadReqId) return; // stale response — drop it
      media = result;
      // 加载集导航（上一集/下一集）
      if (media) {
        try {
          const nav = await seriesApi.getEpisodeNav(media.id);
          if (myId !== loadReqId) return;
          episodeNav = nav;
        } catch {
          if (myId === loadReqId) episodeNav = null;
        }
      }
      // 加载相似内容（基于标签匹配）
      // 逻辑：将当前媒体的所有标签作为过滤条件，查询拥有任意相同标签的媒体（OR 语义），
      // 排除当前媒体自身，取前 8 条作为推荐。后端 GET /media?tag_ids=1,2,3 返回
      // 至少包含其中一个标签的媒体。当媒体没有标签时跳过（返回空数组）。
      if (media && media.tags && media.tags.length > 0) {
        try {
          const res = await mediaApi.list({ tags: media.tags, page: 1, page_size: 9 });
          if (myId !== loadReqId) return;
          // page_size=9 预留 1 条余量以覆盖当前媒体被包含的情况，过滤后取 8 条
          similar = (res.items ?? []).filter((m) => m.id !== id).slice(0, 8);
        } catch {
          if (myId === loadReqId) similar = [];
        }
      }
    } catch (e) {
      if (myId !== loadReqId) return;
      error = '加载媒体详情失败，请检查后端服务是否运行';
      media = null;
    } finally {
      if (myId === loadReqId) loading = false;
    }
  }

  async function loadSidebarData(): Promise<void> {
    const [libs, tgs] = await Promise.allSettled([librariesApi.list(), tagsApi.list()]);
    if (libs.status === 'fulfilled') libraries = libs.value ?? [];
    if (tgs.status === 'fulfilled') allTags = flattenTags(tgs.value ?? []);
  }

  onMount(() => {
    // loadMedia 由下方 $effect 统一触发（含首帧），此处只加载侧栏，避免重复请求
    loadSidebarData();
  });

  // id 变化时重新加载（含首次挂载）
  let lastId = '';
  $effect(() => {
    if (id !== lastId) {
      lastId = id;
      untrack(() => loadMedia());
    }
  });

  // ---- 标题编辑 ----
  function startEditTitle(): void {
    titleDraft = displayTitle;
    titleEditing = true;
    // 等待 DOM 更新后聚焦
    queueMicrotask(() => {
      titleInput?.focus();
      titleInput?.select();
    });
  }

  async function saveTitle(): Promise<void> {
    if (!media) return;
    titleEditing = false;
    const trimmed = String(titleDraft ?? '').trim();
    if (trimmed === displayTitle || !trimmed) return;
    saving = true;
    try {
      const updated = await mediaApi.update(media.id, { title: trimmed });
      media = updated;
      showToast('标题已保存');
    } catch {
      showToast('保存失败', 'err');
    } finally {
      saving = false;
    }
  }

  function cancelEditTitle(): void {
    titleEditing = false;
    titleDraft = displayTitle;
  }

  // ---- 描述编辑 ----
  function startEditDesc(): void {
    descDraft = description;
    descEditing = true;
  }

  async function saveDesc(): Promise<void> {
    if (!media) return;
    descEditing = false;
    if (descDraft === description) return;
    saving = true;
    try {
      const updated = await mediaApi.update(media.id, { description: descDraft });
      media = updated;
      showToast('描述已保存');
    } catch {
      showToast('保存失败', 'err');
    } finally {
      saving = false;
    }
  }

  function cancelEditDesc(): void {
    descEditing = false;
    descDraft = description;
  }

  function onDescKeydown(e: KeyboardEvent): void {
    // Ctrl+Enter 保存
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      saveDesc();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelEditDesc();
    }
  }

  // ---- 评分 ----
  async function setRating(value: number): Promise<void> {
    if (!media) return;
    saving = true;
    try {
      const updated = await mediaApi.update(media.id, { rating: value });
      media = updated;
      showToast(value > 0 ? `已评分 ${value} 星` : '已清除评分');
    } catch {
      showToast('评分失败', 'err');
    } finally {
      saving = false;
    }
  }

  // ---- 收藏 ----
  async function toggleFavorite(): Promise<void> {
    if (!media) return;
    saving = true;
    try {
      const updated = await mediaApi.update(media.id, { favorite: !media.favorite });
      media = updated;
    } catch {
      showToast('操作失败', 'err');
    } finally {
      saving = false;
    }
  }

  // ---- TMDB 刮削 ----
  let scraping = $state(false);

  async function scrapeMedia(): Promise<void> {
    if (!media || scraping) return;
    scraping = true;
    try {
      const updated = await mediaApi.scrape(media.id);
      media = updated;
      showToast('刮削完成：已更新标题 / 年份 / 简介 / 海报');
    } catch (e) {
      // 400: TMDB/AV 未配置；404: 未匹配到结果；502: 网络/接口错误
      let msg = '刮削失败';
      const status = (e as { status?: number })?.status;
      const detail = (e as { body?: { detail?: string } })?.body?.detail;
      if (status === 400) msg = detail || '请先在「设置 → 刮削」中配置 API Key';
      else if (status === 404) msg = detail || '未匹配到对应作品';
      else if (status === 502) msg = detail || '接口请求失败，请检查网络';
      else if (detail) msg = detail;
      showToast(msg, 'err');
    } finally {
      scraping = false;
    }
  }

  // ---- AI 辅助二次刮削 ----
  let aiRescraping = $state(false);
  let aiRescrapeResult = $state<AIRescrapeResponse | null>(null);

  async function aiRescrapeMedia(): Promise<void> {
    if (!media || aiRescraping) return;
    aiRescraping = true;
    aiRescrapeResult = null;
    try {
      const result = await mediaApi.aiRescrape(media.id);
      aiRescrapeResult = result;
      if (result.success) {
        showToast('AI 辅助刮削成功，已更新元数据');
        // 成功后刷新详情页数据
        await reloadMedia();
      } else {
        showToast(result.message || 'AI 已分析但 TMDB 未匹配到结果', 'err');
      }
    } catch (e) {
      const status = (e as { status?: number })?.status;
      let msg = 'AI 辅助刮削失败';
      if (status === 400) {
        // 尝试提取后端返回的 detail 信息
        const detail = (e as { body?: { detail?: string } })?.body?.detail;
        msg = detail || '请检查 AI / TMDB 配置';
      } else if (status === 502) {
        const detail = (e as { body?: { detail?: string } })?.body?.detail;
        msg = detail || 'AI 或 TMDB 调用失败，请检查配置或网络';
      }
      showToast(msg, 'err');
    } finally {
      aiRescraping = false;
    }
  }

  function dismissAiResult(): void {
    aiRescrapeResult = null;
  }

  // ---- 标签操作 ----
  async function addTags(tagIds: string[]): Promise<void> {
    if (!media || tagIds.length === 0) return;
    tagSelectorOpen = false;
    const existing = media.tags ?? [];
    const merged = Array.from(new Set([...existing, ...tagIds]));
    saving = true;
    try {
      const updated = await mediaApi.update(media.id, { tags: merged });
      media = updated;
      showToast(`已添加 ${tagIds.length} 个标签`);
    } catch {
      showToast('添加标签失败', 'err');
    } finally {
      saving = false;
    }
  }

  async function removeTag(tagId: string): Promise<void> {
    if (!media) return;
    const next = (media.tags ?? []).filter((t) => t !== tagId);
    saving = true;
    try {
      const updated = await mediaApi.update(media.id, { tags: next });
      media = updated;
      showToast('已移除标签');
    } catch {
      showToast('移除标签失败', 'err');
    } finally {
      saving = false;
    }
  }

  // ---- 播放 ----
  function play(startAt?: number): void {
    if (!media) return;
    // 文件丢失时：检查是否有网络源可回退
    if (media.file_missing) {
      const networkUrl = getNetworkSourceUrl(media);
      if (networkUrl) {
        const urlType = classifyNetworkUrl(networkUrl);
        if (urlType === 'direct' || urlType === 'hls') {
          // 直链/HLS：跳转到播放器内联播放
          goto(`/player?id=${media.id}&from=${encodeURIComponent(`/detail/${media.id}`)}`);
        } else {
          // 平台链接：在系统浏览器中打开
          openExternalUrl(networkUrl);
          showToast('已打开网络源（平台链接）');
        }
      } else {
        showToast('本地文件丢失，暂无网络源可播放', 'err');
      }
      return;
    }
    player.load(media);
    if (startAt !== undefined && startAt > 0) {
      player.seek(startAt);
    }
    player.play();
    // 跳转到播放器（若路由不存在则触发全屏）
    goto(`/player?id=${media.id}&from=${encodeURIComponent(`/detail/${media.id}`)}`).catch(() => {
      player.toggleFullscreen();
    });
  }

  function jumpToSegment(seg: Segment): void {
    play(seg.start);
  }

  // 从资源链接播放（确保 media 非空）
  function playFromLink(): void {
    play();
  }

  // ---- 字幕加载 ----
  function handleSubtitleFile(fileName: string): void {
    showToast(`已加载字幕文件: ${fileName}`);
  }

  // ---- 删除确认 ----
  let deleteDialogOpen = $state(false);

  // ---- 文件重命名 ----
  let renameEditing = $state(false);
  let renameDraft = $state('');
  let renameReScrape = $state(false);
  let renaming = $state(false);

  function startRename(): void {
    if (!media) return;
    renameDraft = media.filename;
    renameReScrape = false;
    renameEditing = true;
  }

  async function saveRename(): Promise<void> {
    if (!media) return;
    const trimmed = String(renameDraft ?? '').trim();
    if (!trimmed || trimmed === media.filename) {
      renameEditing = false;
      return;
    }
    renaming = true;
    try {
      const updated = await mediaApi.rename(media.id, trimmed, renameReScrape);
      media = updated;
      showToast(renameReScrape ? '已重命名并重新刮削' : '文件已重命名');
    } catch (e: any) {
      const status = (e as { status?: number })?.status;
      let msg = '重命名失败';
      if (status === 409) msg = '目标文件名已存在';
      else if (status === 400) msg = '文件名包含非法字符';
      else if (status === 404) msg = '原始文件未找到';
      showToast(msg, 'err');
    } finally {
      renaming = false;
      renameEditing = false;
    }
  }

  function cancelRename(): void {
    renameEditing = false;
    renameDraft = media?.filename ?? '';
  }

  async function deleteMedia(): Promise<void> {
    if (!media) return;
    deleteDialogOpen = false;
    try {
      await mediaApi.delete(media.id);
      showToast('已移入回收站');
      setTimeout(() => goto('/manage'), 800);
    } catch {
      showToast('删除失败', 'err');
    }
  }

  // ---- 资源链接 CRUD ----
  let linkEditorOpen = $state(false);
  let linkEditing = $state<MediaUrl | null>(null);
  let linkForm = $state({
    url: '',
    title: '',
    url_role: 'source' as UrlRole,
    platform: ''
  });
  let platformManual = $state(false);
  let linkSaving = $state(false);
  let linkDeleteTarget = $state<MediaUrl | null>(null);
  let linkDeleteOpen = $state(false);

  // 轻量重新加载媒体（不闪烁 loading 状态）
  async function reloadMedia(): Promise<void> {
    try {
      media = await mediaApi.get(id);
    } catch {
      showToast('刷新数据失败', 'err');
    }
  }

  function addResourceLink(): void {
    linkEditing = null;
    platformManual = false;
    linkForm = {
      url: '',
      title: '',
      url_role: 'source',
      platform: ''
    };
    linkEditorOpen = true;
  }

  function editResourceLink(url: MediaUrl): void {
    linkEditing = url;
    platformManual = false;
    linkForm = {
      url: url.url,
      title: url.title ?? '',
      url_role: url.url_role,
      platform: url.platform ?? ''
    };
    linkEditorOpen = true;
  }

  function cancelLinkEditor(): void {
    linkEditorOpen = false;
    linkEditing = null;
    // 回收流程中取消手动添加链接 → 终止整个删除流程（用户可重新点"回收"）
    pendingDeleteAfterLink = false;
  }

  async function saveResourceLink(): Promise<void> {
    if (!media) return;
    const url = String(linkForm.url ?? '').trim();
    if (!url) {
      showToast('请输入链接地址', 'err');
      return;
    }
    linkSaving = true;
    try {
      const data: { url: string; url_role: UrlRole; title?: string; platform?: string } = {
        url,
        url_role: linkForm.url_role
      };
      const linkTitle = String(linkForm.title ?? '').trim();
      const linkPlatform = String(linkForm.platform ?? '').trim();
      if (linkTitle) data.title = linkTitle;
      if (linkPlatform) data.platform = linkPlatform;

      if (linkEditing) {
        await mediaApi.updateUrl(media.id, linkEditing.id, data);
        showToast('链接已更新');
      } else {
        await mediaApi.createUrl(media.id, data);
        showToast('链接已添加');
      }
      linkEditorOpen = false;
      linkEditing = null;
      await reloadMedia();
      // 回收流程中：链接保存成功后自动移入回收站（软删除）
      if (pendingDeleteAfterLink) {
        pendingDeleteAfterLink = false;
        void confirmRecycle();
      }
    } catch {
      showToast('保存链接失败', 'err');
    } finally {
      linkSaving = false;
    }
  }

  function confirmDeleteLink(url: MediaUrl): void {
    linkDeleteTarget = url;
    linkDeleteOpen = true;
  }

  async function deleteResourceLink(): Promise<void> {
    if (!media || !linkDeleteTarget) return;
    const urlId = linkDeleteTarget.id;
    linkDeleteOpen = false;
    linkSaving = true;
    try {
      await mediaApi.deleteUrl(media.id, urlId);
      showToast('链接已删除');
      linkDeleteTarget = null;
      // 纯网络(NETWORK)媒体删空最后一个可播源时后端会整条删除记录 → 跳回媒体页
      try {
        const updated = await mediaApi.get(media.id);
        if (updated) media = updated;
      } catch (e) {
        if ((e as { status?: number }).status === 404) {
          await goto('/media');
          return;
        }
        showToast('刷新数据失败', 'err');
      }
    } catch {
      showToast('删除链接失败', 'err');
    } finally {
      linkSaving = false;
    }
  }

  function cancelDeleteLink(): void {
    linkDeleteOpen = false;
    linkDeleteTarget = null;
  }

  // 键盘快捷键：左右方向键切换集（编辑文本时禁用）
  function onWindowKeydown(e: KeyboardEvent): void {
    if (titleEditing || descEditing || renameEditing) return;
    const target = e.target as HTMLElement;
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return;
    if (!episodeNav) return;
    if (e.key === 'ArrowLeft' && episodeNav.has_previous && episodeNav.previous_id) {
      e.preventDefault();
      goto(`/detail/${episodeNav.previous_id}`);
    } else if (e.key === 'ArrowRight' && episodeNav.has_next && episodeNav.next_id) {
      e.preventDefault();
      goto(`/detail/${episodeNav.next_id}`);
    }
  }
</script>

<svelte:window onkeydown={onWindowKeydown} />

<svelte:head><title>{media ? displayTitle : '加载中'} — vitoice</title></svelte:head>

{#if loading}
  <div class="state">加载中…</div>
{:else if error}
  <div class="state error">{error}</div>
{:else if media}
  <div class="detail-page">
    <!-- 顶部栏 -->
    <div class="topbar">
      <button class="icon-btn" onclick={goBack} title="返回">
        <svg viewBox="0 0 24 24" width="18" height="18"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" fill="currentColor"/></svg>
      </button>

      <div class="title-area">
        {#if titleEditing}
          <input
            bind:this={titleInput}
            class="title-input"
            bind:value={titleDraft}
            onblur={saveTitle}
            onkeydown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); saveTitle(); }
              if (e.key === 'Escape') { e.preventDefault(); cancelEditTitle(); }
            }}
          />
        {:else}
          <div class="title" onclick={startEditTitle} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); startEditTitle(); } }} role="button" tabindex="0" title="点击编辑标题">
            {displayTitle}
            <svg class="edit-icon" viewBox="0 0 24 24" width="13" height="13"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/></svg>
          </div>
        {/if}
      </div>

      <div class="actions">
        {#if episodeNav && (episodeNav.has_previous || episodeNav.has_next)}
          <button
            class="action-btn ep-nav-btn"
            onclick={() => episodeNav?.previous_id && goto(`/detail/${episodeNav.previous_id}`)}
            disabled={!episodeNav?.has_previous}
            title={episodeNav?.previous_title ? `上一集: ${episodeNav.previous_title}` : '无上一集'}
          >
            <svg viewBox="0 0 24 24" width="14" height="14"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z" fill="currentColor"/></svg>
            上一集
          </button>
          <button
            class="action-btn ep-nav-btn"
            onclick={() => episodeNav?.next_id && goto(`/detail/${episodeNav.next_id}`)}
            disabled={!episodeNav?.has_next}
            title={episodeNav?.next_title ? `下一集: ${episodeNav.next_title}` : '无下一集'}
          >
            下一集
            <svg viewBox="0 0 24 24" width="14" height="14"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" fill="currentColor"/></svg>
          </button>
        {/if}
        <button class="action-btn primary" onclick={() => play()}>
          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
          播放
        </button>
        <button class="action-btn" onclick={scrapeMedia} disabled={scraping} title="从 TMDB 刮削标题/年份/简介/海报">
          {#if scraping}
            <svg class="spin" viewBox="0 0 24 24" width="14" height="14"><path d="M12 2a10 10 0 1 0 10 10h-2a8 8 0 1 1-8-8z" fill="currentColor"/></svg>
            刮削中…
          {:else}
            <svg viewBox="0 0 24 24" width="14" height="14"><path d="M20.2 6 3 11l-.9-2.4c-.3-.9.2-1.9 1-2.2l14-4.5c.9-.3 1.9.2 2.2 1zM6.2 5.3l3.1 3.9M12.4 3.4l3.1 4M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
            刮削
          {/if}
        </button>
        <button class="action-btn ai-btn" onclick={aiRescrapeMedia} disabled={aiRescraping} title="AI 分析文件名后二次匹配 TMDB（可纠正刮错/漏刮的元数据）">
          {#if aiRescraping}
            <svg class="spin" viewBox="0 0 24 24" width="14" height="14"><path d="M12 2a10 10 0 1 0 10 10h-2a8 8 0 1 1-8-8z" fill="currentColor"/></svg>
            AI 分析中…
          {:else}
            <svg viewBox="0 0 24 24" width="14" height="14"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
            AI 辅助刮削
          {/if}
        </button>
        <button class="action-btn" onclick={startEditTitle} title="编辑">
          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/></svg>
          编辑
        </button>
        {#if media?.file_missing}
          <button
            class="action-btn convert-btn"
            onclick={convertToNetwork}
            disabled={convertingToNetwork}
            title="本地文件已丢失：为媒体添加网络源并转为纯网络视频（保留记录/标签/元数据）"
          >
            {#if convertingToNetwork}
              <svg class="spin" viewBox="0 0 24 24" width="14" height="14"><path d="M12 2a10 10 0 1 0 10 10h-2a8 8 0 1 1-8-8z" fill="currentColor"/></svg>
              转换中…
            {:else}
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
              转为网络视频
            {/if}
          </button>
        {/if}
        <button class="action-btn" onclick={() => (deleteDialogOpen = true)} title="更多">
          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/></svg>
        </button>
        {#if media?.path && !media?.file_missing}
          <button class="action-btn recycle-btn" onclick={onRecycleClick} title="移入回收站（磁盘文件暂不删除，可在回收站二次确认）">
            <svg viewBox="0 0 24 24" width="14" height="14"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/></svg>
            回收
          </button>
        {/if}
      </div>
    </div>

    <!-- AI 辅助刮削结果面板 -->
    {#if aiRescrapeResult}
      <div class="ai-result-panel" class:ok={aiRescrapeResult.success} class:fail={!aiRescrapeResult.success}>
        <div class="ai-result-icon">
          {#if aiRescrapeResult.success}
            <svg viewBox="0 0 24 24" width="18" height="18"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill="currentColor"/></svg>
          {:else}
            <svg viewBox="0 0 24 24" width="18" height="18"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" fill="currentColor"/></svg>
          {/if}
        </div>
        <div class="ai-result-content">
          <div class="ai-result-title">{aiRescrapeResult.success ? 'AI 辅助刮削成功' : 'AI 辅助刮削未匹配'}</div>
          <div class="ai-result-detail">
            {#if aiRescrapeResult.suggested_title}
              <span class="ai-field">
                <span class="ai-label">AI 建议:</span>
                <span class="ai-value">{aiRescrapeResult.suggested_title}{#if aiRescrapeResult.suggested_year} ({aiRescrapeResult.suggested_year}){/if}</span>
              </span>
            {/if}
            {#if aiRescrapeResult.matched_title}
              <span class="ai-field">
                <span class="ai-label">TMDB 匹配:</span>
                <span class="ai-value">{aiRescrapeResult.matched_title}{#if aiRescrapeResult.matched_year} ({aiRescrapeResult.matched_year}){/if}</span>
              </span>
            {:else if aiRescrapeResult.suggested_title}
              <span class="ai-field">
                <span class="ai-label">TMDB 匹配:</span>
                <span class="ai-value muted">未匹配到结果</span>
              </span>
            {/if}
            {#if aiRescrapeResult.message}
              <span class="ai-field"><span class="ai-value muted">{aiRescrapeResult.message}</span></span>
            {/if}
          </div>
        </div>
        <button class="ai-result-close" onclick={dismissAiResult} title="关闭">
          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" fill="currentColor"/></svg>
        </button>
      </div>
    {/if}

    <!-- 主体：左固定 + 右滚动 -->
    <div class="detail-body">
      <!-- Hero 区块：海报 + 关键元数据（顶部横排） -->
      <DetailHero
        media={media}
        displayTitle={displayTitle}
        hasPoster={hasPoster}
        isAv={isAv}
        libraryName={libraryName}
        codec={codec}
        fps={fps}
        bitrate={bitrate}
        sd={sd}
        subtitle={sd?.original_title || media.filename}
        synopsis={media.description || ''}
        genreText={(sd?.genres ?? []).join(' / ')}
        companyText={(sd?.production_companies ?? []).slice(0, 3).join(' / ')}
        tmdbRatingText={tmdbRatingText}
        runtimeText={runtimeText}
        saving={saving}
        onplay={() => play()}
        ontoggleFavorite={toggleFavorite}
        onsetRating={setRating}
        oneditcover={() => {
          if (!media) return;
          editMediaTarget = media;
          editDialogOpen = true;
        }}
        showRefreshSource={isAdultNet && !!adultFancode}
        onrefreshsource={refreshAdultSource}
        backdropUrl={backdropUrl}
      />

      <!-- 演员阵容（独立区块） -->
      <DetailCast cast={sd?.cast ?? []} />

      <!-- 作品详情（独立区块，位于演员阵容之后） -->
      <DetailWork sd={sd} hasScrapeData={hasScrapeData} />

      <!-- 原始文件 / 描述 / 字幕（真实功能区，统一设计样式后并入主流程） -->
      <DetailMeta
        media={media}
        description={description}
        subtitles={subtitles}
        bind:renameEditing
        bind:renameDraft
        bind:renameReScrape
        renaming={renaming}
        bind:descEditing
        bind:descDraft
        onstartRename={startRename}
        onsaveRename={saveRename}
        oncancelRename={cancelRename}
        onstartDescEdit={startEditDesc}
        onsaveDesc={saveDesc}
        oncancelDesc={cancelEditDesc}
        ondescKeydown={onDescKeydown}
        onloadSubtitleFile={handleSubtitleFile}
      />

      <!-- 标签 + 资源版本（双栏） -->
      <div class="detail-grid">
        <DetailTags
          mediaTagObjects={mediaTagObjects}
          groupedTags={groupedTags}
          onadd={() => (tagSelectorOpen = true)}
          onremove={removeTag}
        />
        <DetailLinks
          sourceLinks={sourceLinks}
          referenceLinks={referenceLinks}
          bind:linkEditorOpen
          bind:linkEditing
          bind:linkForm
          bind:platformManual
          linkSaving={linkSaving}
          bind:linkDeleteOpen
          bind:linkDeleteTarget
          onadd={addResourceLink}
          onedit={editResourceLink}
          oncancel={cancelLinkEditor}
          onSave={saveResourceLink}
          onconfirmDelete={confirmDeleteLink}
          onDelete={deleteResourceLink}
          oncancelDelete={cancelDeleteLink}
          onplay={playFromLink}
          showAggregateResolve={canAggregateResolve}
          aggregateResolving={aggregateResolving}
          onaggregateResolve={resolveAggregateSource}
        />
      </div>

      <!-- 媒体信息 -->
      <DetailMediaInfo
        resolutionText={formatResolution(media.width, media.height)}
        codec={codec}
        fpsText={fps > 0 ? `${fps.toFixed(2)} fps` : ''}
        bitrateText={bitrate > 0 ? formatBitrate(bitrate) : ''}
        subtitles={subtitles}
        containerText={readMeta<string>('mime_type', '').split('/').pop()?.toUpperCase() ?? ''}
        durationText={media.duration ? formatTime(media.duration) : ''}
        sizeText={formatSize(media.size)}
      />

      <!-- 内容区：各分区（单列流式，随页面整体滚动） -->
      <div class="right-col">
        <DetailSegments
          segments={segments}
          mediaDuration={media.duration}
          onjump={jumpToSegment}
        />
        <DetailInfo subtitleCount={subtitles.length} segmentCount={segments.length} linkCount={sourceLinks.length + referenceLinks.length} />
        <DetailSimilar
          similar={similar}
          onnavigate={(sid) => goto(`/detail/${sid}`)}
        />
      </div>
    </div>
  </div>
{/if}

<!-- 标签选择器 -->
<TagSelector
  bind:open={tagSelectorOpen}
  tags={allTags}
  multiple={true}
  title="添加标签"
  selected={media?.tags ?? []}
  onselect={(ids) => addTags(ids)}
  oncancel={() => (tagSelectorOpen = false)}
/>

<!-- 删除确认对话框 -->
<ConfirmDialog
  bind:open={deleteDialogOpen}
  title="删除媒体"
  description={`将"${displayTitle}"移入回收站。\n\n磁盘文件不会删除，可在回收站中恢复或彻底删除（无自动清理期限）。`}
  confirmText="删除"
  danger={true}
  onconfirm={deleteMedia}
  oncancel={() => (deleteDialogOpen = false)}
/>

<!-- 编辑媒体对话框（上传/更换/删除封面、编辑标题年份描述） -->
<EditMediaDialog
  bind:open={editDialogOpen}
  media={editMediaTarget}
  onsuccess={reloadMedia}
/>


<!-- 回收确认：将本地文件移入回收站（无网络源时附加"是否添加网络源"问询） -->
{#if askAddNetworkOpen && media}
  <div class="ask-overlay" onclick={() => (askAddNetworkOpen = false)}>
    <div class="ask-card" onclick={(e) => e.stopPropagation()}>
      <div class="ask-header">
        <span class="ask-icon">⚠</span>
        <h3>将本地文件放入回收站？</h3>
        <button class="ask-close" onclick={() => (askAddNetworkOpen = false)}>✕</button>
      </div>
      <div class="ask-body">
        <p>本地文件将<strong>移入回收站</strong>，磁盘文件不会立即删除。可在回收站二次确认「仅删除本地文件」或「彻底删除」。</p>
        <p class="ask-hint">
          注意：「仅删除本地文件」会把媒体<strong>恢复回媒体列表并标记为"文件丢失"</strong>
          （记录、标签、元数据保留，可经网络源继续播放）；「彻底删除」才会真正移除记录。
        </p>
        {#if !hasNetworkSource(media)}
          <div class="ask-net-warn">
            <p>该媒体当前<strong>没有网络源</strong>，删除本地文件后将无法播放。</p>
            <p class="ask-hint">是否先添加网络源？添加后删除本地文件，仍可经网络源继续播放。</p>
          </div>
        {/if}
      </div>
      <div class="ask-actions">
        {#if hasNetworkSource(media)}
          <button class="ask-btn primary" onclick={confirmRecycle}>确认移入回收站</button>
        {:else}
          <button class="ask-btn primary" onclick={onAskAddNetwork}>添加网络源（推荐）</button>
          <button class="ask-btn danger" onclick={onAskSkipAdd}>不添加，直接移入回收站</button>
        {/if}
      </div>
    </div>
  </div>
{/if}

<!-- Toast -->
{#if toast}
  <div class="toast" class:ok={toast.type === 'ok'} class:err={toast.type === 'err'}>{toast.msg}</div>
{/if}

<style>
  .state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 14px;
  }

  .state.error {
    color: #ff3b30;
  }

  .detail-page {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }

  /* ---- 顶部栏 ---- */
  .topbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 24px;
    border-bottom: 1px solid var(--rule);
    background: var(--bg);
    flex-shrink: 0;
  }

  .icon-btn {
    width: 34px;
    height: 34px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--muted);
    transition: all 200ms ease;
    flex-shrink: 0;
  }

  .icon-btn:hover {
    color: var(--ink);
    border-color: var(--muted);
  }

  .title-area {
    flex: 1;
    min-width: 0;
  }

  .title {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: text;
    line-height: 1.4;
  }

  .edit-icon {
    color: var(--muted);
    opacity: 0;
    transition: opacity 200ms;
  }

  .title:hover .edit-icon {
    opacity: 1;
  }

  .title-input {
    width: 100%;
    max-width: 500px;
    height: 34px;
    padding: 0 10px;
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 16px;
    font-weight: 600;
    font-family: inherit;
  }

  .title-input:focus {
    outline: none;
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .action-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 32px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 12.5px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .action-btn:hover {
    border-color: var(--muted);
  }

  .action-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .ep-nav-btn {
    padding: 0 10px;
    font-size: 12px;
  }

  .spin {
    animation: spin 800ms linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .action-btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .action-btn.primary:hover {
    filter: brightness(1.08);
  }

  .action-btn.ai-btn {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
  }

  .action-btn.ai-btn:hover {
    background: var(--accent);
    color: #fff;
  }

  /* 回收（删除本地文件）：红色危险强调 */
  .action-btn.recycle-btn {
    background: rgba(239, 68, 68, 0.12);
    border-color: rgba(239, 68, 68, 0.45);
    color: #f87171;
  }

  .action-btn.recycle-btn:hover {
    background: rgba(239, 68, 68, 0.22);
    border-color: #f87171;
  }

  /* 转为网络视频：琥珀色强调（文件丢失场景下的补救操作） */
  .action-btn.convert-btn {
    background: rgba(245, 185, 66, 0.14);
    border-color: rgba(245, 185, 66, 0.5);
    color: var(--amber, #f5b942);
  }

  .action-btn.convert-btn:hover:not(:disabled) {
    background: rgba(245, 185, 66, 0.24);
    border-color: var(--amber, #f5b942);
  }

  .action-btn.convert-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* 回收前置问询对话框 */
  .ask-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 120;
    backdrop-filter: blur(2px);
  }

  .ask-card {
    width: 380px;
    max-width: calc(100vw - 32px);
    background: var(--bg2, #1e1e2e);
    border: 1px solid var(--rule, rgba(255,255,255,0.12));
    border-radius: 12px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
    overflow: hidden;
  }

  .ask-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 18px;
    border-bottom: 1px solid var(--rule, rgba(255,255,255,0.1));
  }

  .ask-icon {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    flex-shrink: 0;
  }

  .ask-header h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    flex: 1;
  }

  .ask-close {
    background: none;
    border: none;
    color: var(--muted, #888);
    font-size: 14px;
    cursor: pointer;
    padding: 2px 4px;
  }

  .ask-close:hover {
    color: var(--ink, #eee);
  }

  .ask-body {
    padding: 16px 18px;
    font-size: 13.5px;
    line-height: 1.7;
    color: var(--ink, #e5e5e5);
  }

  .ask-body p {
    margin: 0 0 6px;
  }

  .ask-hint {
    color: var(--muted, #999);
    font-size: 12.5px;
  }

  .ask-net-warn {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 8px;
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.3);
  }

  .ask-net-warn p {
    margin: 0 0 4px;
  }

  .ask-net-warn .ask-hint {
    margin: 0;
  }

  .ask-actions {
    display: flex;
    gap: 10px;
    padding: 12px 18px 16px;
  }

  .ask-btn {
    flex: 1;
    height: 34px;
    border-radius: 8px;
    border: 1px solid var(--rule, rgba(255,255,255,0.15));
    background: var(--bg3, #26263a);
    color: var(--ink, #eee);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 160ms ease;
  }

  .ask-btn:hover {
    filter: brightness(1.1);
  }

  .ask-btn.primary {
    background: var(--accent, #7c3aed);
    border-color: var(--accent, #7c3aed);
    color: #fff;
  }

  .ask-btn.danger {
    background: transparent;
    border-color: rgba(239, 68, 68, 0.5);
    color: #f87171;
  }

  .ask-btn.danger:hover {
    background: rgba(239, 68, 68, 0.15);
  }

  /* ---- AI 辅助刮削结果面板 ---- */
  .ai-result-panel {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px 24px;
    border-bottom: 1px solid var(--rule);
    background: var(--bg2);
    flex-shrink: 0;
    animation: ai-panel-in 200ms ease;
  }

  @keyframes ai-panel-in {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .ai-result-panel.ok {
    border-left: 3px solid var(--ok, #34c759);
  }

  .ai-result-panel.fail {
    border-left: 3px solid #f59e0b;
  }

  .ai-result-icon {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-full);
  }

  .ai-result-panel.ok .ai-result-icon {
    color: var(--ok, #34c759);
    background: rgba(52, 199, 89, 0.12);
  }

  .ai-result-panel.fail .ai-result-icon {
    color: #f59e0b;
    background: rgba(245, 158, 11, 0.12);
  }

  .ai-result-content {
    flex: 1;
    min-width: 0;
  }

  .ai-result-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 4px;
  }

  .ai-result-detail {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 16px;
    font-size: 12.5px;
  }

  .ai-field {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  .ai-label {
    color: var(--muted);
    flex-shrink: 0;
  }

  .ai-value {
    color: var(--ink);
  }

  .ai-value.muted {
    color: var(--muted);
  }

  .ai-result-close {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: none;
    color: var(--muted);
    cursor: pointer;
    border-radius: var(--radius);
    transition: all 200ms ease;
  }

  .ai-result-close:hover {
    color: var(--ink);
    background: var(--bg-soft);
  }

  /* ---- 主体布局（单列流式：整页滚动） ---- */
  .detail-body {
    flex: 1;
    overflow-y: auto;
  }

  /* ---- 内容区 ---- */
  .right-col {
    max-width: 1280px;
    margin: 0 auto;
    padding: 24px 28px;
  }

  /* ---- 标签 + 资源版本 双栏 ---- */
  .detail-grid {
    display: grid;
    grid-template-columns: 1.05fr 1.65fr;
    gap: 14px;
    align-items: start;
    padding: 24px 28px;
    max-width: 1280px;
    margin: 0 auto;
  }

  @media (max-width: 900px) {
    .detail-grid {
      grid-template-columns: 1fr;
      padding: 18px 16px;
    }
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
</style>
