<script lang="ts">
  // 全屏播放器页面（vitoice Phase 3.0 核心体验）
  // YouTube 风格手势 + 完整快捷键体系 + 整理带。
  // 说明：播放状态以 <video> 元素为唯一真相源，绑定到本地 $state；
  //       全局项（音量/静音/字幕偏好）走 localStorage 持久化，per-media 速率/进度走后端。
  //       player store 文件按约定未修改，本页自包含不依赖其字段。
  import { onMount, onDestroy, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { mediaApi, type RelatedMediaItem } from '$lib/api/media';
  import { seriesApi } from '$lib/api/series';
  import { client, BASE_URL } from '$lib/api/client';
  import { formatTime } from '$lib/utils/format';
  import { toggleWorkAreaMaximize, isWorkAreaMaximized, sizeLooksMaximized } from '$lib/utils/tauri-window';
  import { classifyNetworkUrl, loadHlsJs, openExternalUrl, isAdultAggregatorUrl, isAdultNetworkMedia, extractFancode } from '$lib/utils/network-media';
  import { adultNetworkApi } from '$lib/api/networkSources';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import ProgressBar from '$lib/components/player/ProgressBar.svelte';
  import SubtitleTrack from '$lib/components/player/SubtitleTrack.svelte';
  import OrganizeStrip from '$lib/components/player/OrganizeStrip.svelte';
  import SegmentDialog from '$lib/components/player/SegmentDialog.svelte';
  import QuickTagDialog from '$lib/components/player/QuickTagDialog.svelte';

  // —— 本地类型（匹配后端 MediaResponse，因前端共享类型未含这些字段）——
  interface Segment {
    id: number;
    media_id: number;
    name: string;
    start_time: number;
    end_time: number | null;
    color: string | null;
  }
  interface Subtitle {
    id: number;
    media_id: number;
    language: string;
    title: string | null;
    file_path: string | null;
    file_format: string | null;
    is_default: boolean;
  }
  interface PlayerMedia {
    id: number;
    library_id: number;
    title: string;
    file_name: string;
    file_path: string | null;
    media_type: string;
    mime_type: string | null;
    file_size: number | null;
    file_missing: boolean;
    duration: number | null;
    width: number | null;
    height: number | null;
    thumbnail_path: string | null;
    rating: number | null;
    is_favorite: boolean;
    is_watched: boolean;
    playback_position: number;
    playback_speed: number | null;
    segments: Segment[];
    subtitles: Subtitle[];
    urls?: { id: number; url: string; url_role: string; platform?: string | null; is_expired: boolean; played_progress?: number }[];
    created_at: string;
    updated_at: string;
  }

  const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

  const mediaId = $derived($page.url.searchParams.get('id') ?? '');

  // —— 媒体与加载 ——
  let media = $state<PlayerMedia | null>(null);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let loadReqId = 0;

  // —— 文件丢失对话框 ——
  let fileMissingInfo = $state<{ hasNetwork: boolean; networkUrl: string | null; isPlatform: boolean } | null>(null);

  // —— 网络播放状态 ——
  let hlsInstance: any = null;
  let networkPlayError = $state<string | null>(null);

  // 检查是否有可用的网络源
  function getNetworkSourceUrl(m: PlayerMedia): string | null {
    const source = m.urls?.find((u) => u.url_role === 'source' && !u.is_expired);
    return source?.url ?? null;
  }

  // —— 视频元素与播放状态（绑定 <video>）——
  let videoEl = $state<HTMLVideoElement | null>(null);
  let containerEl = $state<HTMLDivElement | null>(null);
  let paused = $state(true);
  let currentTime = $state(0);
  let duration = $state(0);
  let buffered = $state(0);
  let waiting = $state(false);

  // —— 播放器挂载守卫：防止中央播放按钮首次渲染时的 transform 漂移 ——
  let playerMounted = $state(false);

  // —— Seek 抑制标志：转码流切换 src 时抑制 video error 事件 ——
  let seeking = $state(false);

  // —— 全局偏好（localStorage 持久化）——
  let volume = $state(loadPref('vitoice:volume', 1));
  let muted = $state(loadPref('vitoice:muted', false));
  // 静音前的音量，用于一键恢复
  let lastVolume = $state(loadPref('vitoice:lastVolume', 1));
  let captionsOn = $state(loadPref('vitoice:captions', false));

  // —— per-media / 会话状态 ——
  let playbackRate = $state(1);
  let isFullscreen = $state(false);
  let currentSubtitleId = $state<number | null>(null);
  let subtitleMenuOpen = $state(false);
  let speedMenuOpen = $state(false);
  let volumeOpen = $state(false);

  // —— 转码流 seek 支持 ——
  let streamStart = $state(0); // 转码流起始时间（0 = 从头播放）
  // 原生 seek 验证：直接播放分支设置 videoEl.currentTime 后，浏览器可能拒绝
  // （流实际不支持 Range，如后端对 HEVC MP4 转码的流）——短超时后 currentTime
  // 未接近目标则降级为重载式 seek（streamStart + ?start=）。不依赖前后端对
  // "是否转码"的判断一致（后端按 codec 探测，前端只能按扩展名猜）。
  let seekVerify: { target: number; before: number } | null = null;
  let wasPlayingBeforeSeek = false; // seek 前是否在播放，用于 seek 后恢复

  // —— 控制层可见性（三层）——
  let controlsVisible = $state(true);
  let organizeVisible = $state(false);
  let organizePinned = $state(false); // 整理带锁定开关：开启后常驻不自动隐藏

  // —— 片段标记 ——
  let markStart = $state<number | null>(null);
  let segmentDialogOpen = $state(false);
  let segmentStart = $state(0);
  let segmentEnd = $state(0);

  // —— 片段列表面板 ——
  let segPanelOpen = $state(false);
  let deletingSegId = $state<number | null>(null);

  // —— 快速打标 ——
  let quickTagOpen = $state(false);
  let aiPreselect = $state<number[]>([]);

  // —— Toast / 截图闪光 ——
  let toastMsg = $state<string | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  let flash = $state(false);

  // —— 派生 ——
  const isPlaying = $derived(!paused);
  const hasSubtitle = $derived((media?.subtitles?.length ?? 0) > 0);
  const currentSubtitle = $derived(
    media?.subtitles?.find((s) => s.id === currentSubtitleId) ?? null
  );
  const title = $derived(media?.title || media?.file_name || '播放器');
  const rating = $derived(media?.rating ?? 0);
  const favorite = $derived(media?.is_favorite ?? false);
  const isImage = $derived((media?.mime_type ?? '').startsWith('image'));

  // —— 网络播放模式判定 ——
  // 多源切换：media 可能有多个 source URL（如成人聚合站的 vidhide/turboplay/streamwish），
  // 用户在控制条上手动切换；切换 activeSourceIdx 后 streamUrl 变化，hls $effect 自动重建。
  let activeSourceIdx = $state(0);
  const playableSources = $derived(
    (media?.urls ?? []).filter((u) => u.url_role === 'source' && !u.is_expired)
  );
  const networkSourceUrl = $derived.by(() => {
    if (!media) return null;
    if (playableSources.length > 0) {
      const idx = activeSourceIdx < playableSources.length ? activeSourceIdx : 0;
      return playableSources[idx]?.url ?? null;
    }
    return getNetworkSourceUrl(media);
  });

  // 切换媒体时重置源索引
  let lastMediaIdForSource: string | number | null = null;
  $effect(() => {
    const mid = media?.id ?? null;
    if (mid !== lastMediaIdForSource) {
      lastMediaIdForSource = mid;
      activeSourceIdx = 0;
    }
  });

  function switchSource(idx: number): void {
    if (idx === activeSourceIdx || idx < 0 || idx >= playableSources.length) return;
    activeSourceIdx = idx;
    showControls();
  }

  const networkMode = $derived.by(() => {
    if (!media || !networkSourceUrl) return 'none' as 'none' | 'direct' | 'hls' | 'platform';
    // 纯网络媒体或文件丢失时使用网络源
    const needsNetwork = media.file_missing || media.media_type === 'network';
    if (!needsNetwork) return 'none';
    return classifyNetworkUrl(networkSourceUrl);
  });
  const isNetworkPlayback = $derived(networkMode === 'direct' || networkMode === 'hls');
  const showSourceSwitch = $derived(isNetworkPlayback && playableSources.length > 1);

  // 聚合站页面链接（javgg 文章页）无法直接播放——明确提示用户去"刷新源"，
  // 而不是当视频流代理导致 502 黑屏。切到正常直链源时自动清除该提示。
  const AGGREGATOR_PAGE_MSG = '检测到聚合站页面链接（无法直接播放），请刷新源获取播放直链';
  $effect(() => {
    const url = networkSourceUrl;
    if (url && isAdultAggregatorUrl(url)) {
      networkPlayError = AGGREGATOR_PAGE_MSG;
    } else if (networkPlayError === AGGREGATOR_PAGE_MSG) {
      networkPlayError = null;
    }
  });

  // —— 播放器内联"刷新源"（成人聚合站媒体） ——
  const canRefreshAdultSource = $derived(
    !!media && isAdultNetworkMedia(media) && !!extractFancode(media.title || media.file_name || '')
  );
  let refreshingSource = $state(false);
  // F5 fix: set when a network-source refresh should auto-play the new
  // stream; consumed by onLoadedMetadata (or cleared after a direct play).
  let pendingAutoPlay = $state(false);

  async function refreshAdultSource(): Promise<void> {
    if (!media || refreshingSource) return;
    const fc = extractFancode(media.title || media.file_name || '');
    if (!fc) return;
    refreshingSource = true;
    try {
      const res = await adultNetworkApi.refresh(String(media.id), fc);
      // 后端解析失败（如 javgg 限流）返回 200 + refresh.status=error——显式检查
      if (res.refresh && res.refresh.status !== 'ok') {
        networkPlayError = res.refresh.message || '刷新失败，请稍后再试';
        return;
      }
      networkPlayError = null;
      await loadMedia(mediaId); // 重新加载媒体（新直链已就位）
      activeSourceIdx = 0;
      // F5 fix: loadMedia() flips loading=true which unmounts the old <video>
      // — a queueMicrotask play() would run before the new element renders.
      // Set a flag instead; onLoadedMetadata consumes it once the new stream
      // is ready (fallback: the element already loaded → play directly).
      pendingAutoPlay = true;
      if (videoEl && videoEl.readyState >= 1) {
        videoEl.play().catch(() => {});
        pendingAutoPlay = false;
      }
    } catch (e) {
      const status = (e as { status?: number })?.status;
      const detail = (e as { body?: { detail?: string } })?.body?.detail;
      networkPlayError =
        status === 403
          ? detail || '成人网络源功能未开启（设置 → 内容管理）'
          : detail || '刷新失败，请稍后再试';
    } finally {
      refreshingSource = false;
    }
  }

  const streamUrl = $derived.by(() => {
    if (!media) return '';
    if (isImage) return mediaApi.thumbnailUrl(String(media.id), media.updated_at);
    // HLS 流：直接使用原始 URL（hls.js 负责加载，避免代理导致播放列表相对路径错乱）
    if (networkMode === 'hls') {
      return networkSourceUrl ?? '';
    }
    // 直链视频：通过后端代理解决 CORS，支持 Range 请求
    // url_id 指定当前选中的源（多源切换时代理必须转发正确的 URL）
    if (networkMode === 'direct') {
      const srcId = playableSources[activeSourceIdx]?.id;
      return `${BASE_URL}/media/${media.id}/network-stream${srcId ? `?url_id=${srcId}` : ''}`;
    }
    // 本地文件可用
    if (!media.file_missing && media.media_type !== 'network') {
      return streamStart > 0
        ? `${mediaApi.streamUrl(String(media.id))}?start=${streamStart}`
        : mediaApi.streamUrl(String(media.id));
    }
    return '';
  });
  const posterUrl = $derived(media?.thumbnail_path ? mediaApi.thumbnailUrl(String(media.id), media.updated_at) : '');
  // Seek 期间隐藏 poster：转码流切换 src 时浏览器会显示 poster（= 首帧/缩略图），
  // 给用户造成"画面回到开头"的错觉。清空后浏览器保持上一帧（或黑屏 + 加载指示器）。
  const effectivePoster = $derived(seeking ? '' : posterUrl);

  const segAnchors = $derived.by(() => {
    const out = (media?.segments ?? []).map((s) => ({
      start: s.start_time,
      end: s.end_time,
      color: s.color,
      label: s.name
    }));
    if (markStart != null) {
      out.push({ start: markStart, end: null, color: '#f59e0b', label: '片段起点（未结束）' });
    }
    return out;
  });

  const anyDialogOpen = $derived(
    segmentDialogOpen || quickTagOpen || segPanelOpen || subtitleMenuOpen || speedMenuOpen || volumeOpen
  );

  // —— 限制内容遮罩 ——
  const isRestrictedMedia = $derived.by(() => {
    if (!media || !settingsStore.maskRestricted) return false;
    return librariesStore.libraries.some(
      (l) => String(l.id) === String(media!.library_id) && l.is_restricted
    );
  });

  // —— 转码流相关派生值 ——
  // 检测文件是否需要转码（MKV 容器浏览器支持不稳定）
  // 网络播放时始终使用原生 seek（代理支持 Range 请求，HLS 由 hls.js 管理）
  const needsTranscoding = $derived(
    media && !isNetworkPlayback ? (media.file_name?.toLowerCase().endsWith('.mkv') ||
             (media.mime_type ?? '').includes('matroska')) : false
  );
  // 显示用的时间（考虑转码流偏移量）
  const displayTime = $derived(streamStart + currentTime);
  // 显示用的总时长（优先使用 API 返回的原始时长，转码流 video.duration 可能不准）
  const displayDuration = $derived(media?.duration ?? duration);
  // 显示用的缓冲位置
  const displayBuffered = $derived(streamStart + buffered);

  // —— 持久化助手 ——
  function loadPref<T>(key: string, fallback: T): T {
    try {
      const v = localStorage.getItem(key);
      if (v === null) return fallback;
      return JSON.parse(v) as T;
    } catch {
      return fallback;
    }
  }
  function savePref(key: string, value: unknown): void {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore */
    }
  }

  // 持久化全局偏好
  $effect(() => {
    savePref('vitoice:volume', volume);
  });
  $effect(() => {
    savePref('vitoice:muted', muted);
  });
  $effect(() => {
    savePref('vitoice:captions', captionsOn);
  });
  // per-media 播放偏好（音量/静音/字幕轨；倍速已按媒体存后端 playback_speed）
  $effect(() => {
    if (!media) return;
    savePref(`vitoice:media:${media.id}`, {
      volume,
      muted,
      captionsOn,
      subtitleId: currentSubtitleId,
    });
  });

  // —— 加载媒体 ——
  async function loadMedia(id: string): Promise<void> {
    if (!id) {
      loading = false;
      return;
    }
    const myId = ++loadReqId;
    loading = true;
    loadError = null;
    try {
      // 直接使用 client.get 获取后端完整响应（含 segments/subtitles/playback_speed 等）
      // mediaApi.get() 会经过 normalizeMedia() 丢弃播放器所需字段
      const raw = await client.get<any>(`/media/${id}`);
      if (myId !== loadReqId) return;
      if (!raw || typeof raw !== 'object') {
        loadError = '媒体数据无效，ID 可能不存在';
        return;
      }
      media = {
        ...raw,
        file_missing: raw?.file_missing ?? false,
        urls: Array.isArray(raw?.urls) ? raw.urls : [],
        segments: Array.isArray(raw?.segments) ? raw.segments : [],
        subtitles: Array.isArray(raw?.subtitles) ? raw.subtitles : [],
        playback_position: raw?.playback_position ?? 0,
        playback_speed: raw?.playback_speed ?? null,
        is_watched: raw?.is_watched ?? false,
        is_favorite: raw?.is_favorite ?? false,
        rating: raw?.rating ?? null,
      } as PlayerMedia;
      // 文件丢失或纯网络媒体检测
      const netUrl = getNetworkSourceUrl(media);
      const needsNetworkPlayback = media.file_missing || media.media_type === 'network';
      networkPlayError = null;

      if (needsNetworkPlayback && netUrl) {
        const urlType = classifyNetworkUrl(netUrl);
        if (urlType === 'platform') {
          // 平台链接（YouTube/Bilibili等）无法内联播放，显示对话框
          fileMissingInfo = { hasNetwork: true, networkUrl: netUrl, isPlatform: true };
        } else {
          // direct/hls: 内联播放，不显示对话框
          fileMissingInfo = null;
        }
      } else if (media.file_missing && !netUrl) {
        fileMissingInfo = { hasNetwork: false, networkUrl: null, isPlatform: false };
      } else {
        fileMissingInfo = null;
      }
      // 默认字幕
      const subs = media.subtitles;
      const def = subs?.find((s) => s.is_default) ?? subs?.[0] ?? null;
      currentSubtitleId = def?.id ?? null;
      if (!subs?.length) captionsOn = false;
      // per-media 速率
      if (media.playback_speed) playbackRate = media.playback_speed;
      // per-media 播放偏好（音量/静音/字幕轨），覆盖全局默认
      const mp = loadPref<null | {
        volume?: number;
        muted?: boolean;
        captionsOn?: boolean;
        subtitleId?: number;
      }>(`vitoice:media:${id}`, null);
      if (mp) {
        if (typeof mp.volume === 'number') volume = Math.max(0, Math.min(1, mp.volume));
        if (typeof mp.muted === 'boolean') muted = mp.muted;
        if (typeof mp.captionsOn === 'boolean' && subs?.length) captionsOn = mp.captionsOn;
        if (typeof mp.subtitleId === 'number' && subs?.some((s) => s.id === mp.subtitleId)) {
          currentSubtitleId = mp.subtitleId;
        }
      }
      // 重置片段标记和转码流偏移
      markStart = null;
      streamStart = 0;
    } catch {
      if (myId !== loadReqId) return;
      loadError = '加载媒体失败，请检查后端服务或链接是否有效';
    } finally {
      if (myId === loadReqId) loading = false;
    }
  }

  $effect(() => {
    const id = mediaId;
    // untrack：loadMedia 在 await 前同步写 loading/loadError（$state），
    // 防止被追踪进 effect 依赖面（项目 Svelte 5 响应式安全约定）
    if (id) untrack(() => loadMedia(id));
    else {
      media = null;
      loading = false;
    }
  });

  // —— HLS.js 初始化（网络 HLS 流播放）——
  // —— HLS 清晰度（levels）——
  let hlsLevels = $state<{ height: number; bitrate: number }[]>([]);
  let currentLevelIdx = $state(-1); // -1 = 自动
  let qualityOpen = $state(false);
  const showQualityMenu = $derived(
    isNetworkPlayback && networkMode === 'hls' && hlsLevels.length > 1
  );
  const currentQualityLabel = $derived(
    currentLevelIdx >= 0 && hlsLevels[currentLevelIdx] ? `${hlsLevels[currentLevelIdx].height}p` : '自动'
  );

  function setQuality(idx: number): void {
    if (hlsInstance) hlsInstance.nextLevel = idx; // -1 = auto
    currentLevelIdx = idx;
    if (idx >= 0 && hlsLevels[idx]) {
      localStorage.setItem('player-quality-height', String(hlsLevels[idx].height));
    } else {
      localStorage.removeItem('player-quality-height');
    }
    qualityOpen = false;
  }

  $effect(() => {
    const mode = networkMode;
    const el = videoEl;
    const url = streamUrl;

    // 非 HLS 模式：清理已有实例
    if (mode !== 'hls' || !el || !url) {
      if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
      }
      hlsLevels = [];
      currentLevelIdx = -1;
      qualityOpen = false;
      return;
    }

    let cancelled = false;
    loadHlsJs().then((Hls) => {
      if (cancelled || !videoEl) return;
      if (Hls.isSupported()) {
        if (hlsInstance) hlsInstance.destroy();
        hlsInstance = new Hls({ enableWorker: true });
        hlsInstance.loadSource(url);
        hlsInstance.attachMedia(videoEl);
        hlsInstance.on(Hls.Events.ERROR, (_evt: any, data: any) => {
          if (data.fatal) {
            networkPlayError = 'HLS 流播放失败——源可能已失效或过期，请返回详情页点击「刷新源」更新';
          }
        });
        // 清晰度：解析 master playlist 的 levels + 应用记忆偏好
        hlsInstance.on(Hls.Events.MANIFEST_PARSED, (_evt: any, data: any) => {
          const levels = (data?.levels ?? []).map((l: any) => ({
            height: l.height || 0,
            bitrate: l.bitrate || 0,
          }));
          hlsLevels = levels;
          currentLevelIdx = -1;
          if (levels.length > 1) {
            const pref = Number(localStorage.getItem('player-quality-height'));
            const idx = levels.findIndex((l: { height: number }) => l.height === pref);
            if (idx >= 0 && hlsInstance) {
              hlsInstance.nextLevel = idx;
              currentLevelIdx = idx;
            }
          }
        });
        hlsInstance.on(Hls.Events.LEVEL_SWITCHED, (_evt: any, data: any) => {
          if (typeof data?.level === 'number' && data.level >= 0 && data.level < hlsLevels.length) {
            currentLevelIdx = data.level;
          }
        });
      } else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
        // Safari 原生 HLS 支持
        videoEl.src = url;
      } else {
        networkPlayError = '当前浏览器不支持 HLS 播放';
      }
    }).catch(() => {
      if (!cancelled) networkPlayError = '无法加载 HLS 播放器组件';
    });

    return () => {
      cancelled = true;
      if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
      }
    };
  });

  // —— 进度自动保存（每 5 秒，播放中）——
  async function saveProgress(): Promise<void> {
    if (!media) return;
    const m = media;
    // 只用底层 $state 快照（不读 $derived）：exitPlayer 里 void saveProgress() 后
    // 组件可能立即销毁，await 之后再读 derived 会触发 Svelte 5 的
    // derived_inert 警告（读取属于已销毁 effect 的 derived）。
    const pos = streamStart + currentTime;
    // 防御：播放失败时 currentTime 可能为 NaN（network-stream 502 等），
    // position=NaN 会被后端 ge=0 校验拒绝（422）
    if (!Number.isFinite(pos)) return;
    const spd = playbackRate;
    // await 前取好网络同步所需快照（networkMode/playableSources 是 derived）
    const net = networkMode;
    const srcObj =
      playableSources[activeSourceIdx] ??
      m.urls?.find((u) => u.url_role === 'source' && !u.is_expired);
    const srcId = srcObj?.id;
    try {
      await client.post(`/media/${m.id}/progress`, {
        position: pos,
        speed: spd
      });
      // Phase 5: 网络播放时同步进度到 URL 记录（跨源进度同步）
      if ((net === 'direct' || net === 'hls') && srcId) {
        await client.put(`/media/${m.id}/urls/${srcId}/progress`, {
          played_progress: pos,
        }).catch(() => {}); // 静默失败，不阻塞主进度保存
      }
    } catch {
      /* 静默 */
    }
  }

  $effect(() => {
    if (!isPlaying || !media) return;
    const id = setInterval(() => {
      void saveProgress();
    }, 5000);
    return () => clearInterval(id);
  });

  // 页面隐藏 / 卸载时保存
  function onVisibility(): void {
    if (document.visibilityState === 'hidden') void saveProgress();
  }

  // —— 视频事件 ——
  function onTimeUpdate(): void {
    // 手动同步播放位置（替代 bind:currentTime，消除双向绑定竞态）：
    // video 元素是唯一真相源；seek 期间（转码流重载 src）不写回，
    // 避免新源 currentTime 瞬间为 0 时把显示进度覆盖回开头。
    if (!videoEl || seeking) return;
    const t = videoEl.currentTime;
    if (Number.isFinite(t) && t !== currentTime) currentTime = t;
  }

  function onProgress(): void {
    if (!videoEl) return;
    try {
      if (videoEl.buffered.length) {
        buffered = videoEl.buffered.end(videoEl.buffered.length - 1);
      }
    } catch {
      /* ignore */
    }
  }
  function onLoadedMetadata(): void {
    // 新流已加载，清除 seek 抑制标志
    seeking = false;
    if (!videoEl || !media) return;

    if (streamStart > 0) {
      // 转码流 seek 后重新加载：视频从 streamStart 开始，无需设置 currentTime
      // 相对基准归零（bind:currentTime 可能未及时写回，显式保证 displayTime 正确）
      currentTime = 0;
      if (wasPlayingBeforeSeek) {
        videoEl.play().catch(() => {});
        wasPlayingBeforeSeek = false;
      }
      showControls();
      return;
    }

    // 正常加载：恢复上次播放位置
    let saved = media.playback_position ?? 0;
    // 网络播放：如果主进度为 0，尝试从 URL 的 played_progress 恢复（跨源进度同步）
    if (isNetworkPlayback && saved === 0) {
      const sourceUrlObj = media.urls?.find((u) => u.url_role === 'source' && !u.is_expired);
      if (sourceUrlObj?.played_progress && sourceUrlObj.played_progress > 0) {
        saved = sourceUrlObj.played_progress;
      }
    }
    const dur = media.duration ?? duration;
    if (saved > 0 && dur > 0 && saved < dur * 0.95) {
      if (videoEl) videoEl.currentTime = saved;
      currentTime = saved;
    }
    // 尝试自动播放（浏览器可能拦截带声音的自动播放，失败则保持暂停）
    if (!isImage) {
      videoEl.play().catch(() => {
        /* 用户需手动点击播放 */
      });
      // F5 fix: consume the refresh auto-play flag once the new stream is ready
      pendingAutoPlay = false;
      // 首次进入时短暂展示整理带，提示可用快捷键
      showOrganize();
    }
  }
  function onEnded(): void {
    void saveProgress();
    showControls();
    void handlePlaybackEnded();
  }

  // —— 播放结束：连播 / 推荐网格（T1） ——
  let endOverlayOpen = $state(false);
  let endNextId = $state<number | null>(null);
  let endCountdown = $state(0);
  let endRecItems = $state<RelatedMediaItem[]>([]);
  let endTimer: ReturnType<typeof setInterval> | null = null;
  let endNavBusy = $state(false);

  async function handlePlaybackEnded(): Promise<void> {
    if (!media || endNavBusy) return;
    endNavBusy = true;
    try {
      // 下一集（同系列）
      let nextId: number | null = null;
      try {
        const nav = await seriesApi.getEpisodeNav(String(media.id));
        if (nav.has_next && nav.next_id) nextId = nav.next_id;
      } catch {
        /* 非系列媒体 → 无下一集 */
      }
      // 推荐列表（同系列下一集 > 同标签 > 同库）
      try {
        endRecItems = await mediaApi.related(String(media.id), 8);
      } catch {
        endRecItems = [];
      }

      if (settingsStore.playerAutoplay && nextId != null) {
        // 连播：5s 倒计时覆盖层
        endNextId = nextId;
        endCountdown = 5;
        endOverlayOpen = true;
        cancelEndTimer();
        endTimer = setInterval(() => {
          endCountdown -= 1;
          if (endCountdown <= 0) void playNextNow();
        }, 1000);
      } else if (settingsStore.playerRecGrid && endRecItems.length > 0) {
        // 无连播 → 推荐网格
        endOverlayOpen = true;
      }
    } finally {
      endNavBusy = false;
    }
  }

  function cancelEndTimer(): void {
    if (endTimer) {
      clearInterval(endTimer);
      endTimer = null;
    }
  }

  async function playNextNow(): Promise<void> {
    cancelEndTimer();
    const id = endNextId;
    endOverlayOpen = false;
    if (id != null) {
      // 保留 from 等现有参数，仅替换 id —— $effect(mediaId) 会自动重载
      const url = new URL($page.url);
      url.searchParams.set('id', String(id));
      await goto(url.pathname + url.search);
    }
  }

  function playRecItem(item: RelatedMediaItem): void {
    cancelEndTimer();
    endOverlayOpen = false;
    const url = new URL($page.url);
    url.searchParams.set('id', String(item.id));
    void goto(url.pathname + url.search);
  }

  function dismissEndOverlay(): void {
    cancelEndTimer();
    endOverlayOpen = false;
  }

  // —— 视频错误处理：抑制 seek 期间的 ERR_ABORTED ——
  function onVideoError(): void {
    if (!videoEl || !videoEl.error) return;
    const code = videoEl.error.code;
    // MEDIA_ERR_ABORTED (1)：seek 时浏览器中止上一个流请求，属于预期行为
    // seek 期间（转码流切换 src）的所有错误都静默忽略
    if (code === 1 || seeking) return;
    if (isNetworkPlayback) {
      // 网络源失败：明确提示（直链可能已过期/失效），而不是黑屏静默
      networkPlayError =
        '网络源播放失败——源可能已失效或过期，请返回详情页点击「刷新源」更新';
    } else {
      console.warn('[Player] 视频错误:', code, videoEl.error.message);
    }
  }

  // —— 播放控制 ——
  async function togglePlay(): Promise<void> {
    if (!videoEl || isImage) return;
    if (paused) {
      try {
        await videoEl.play();
      } catch {
        /* ignore */
      }
    } else {
      videoEl.pause();
    }
  }
  function seek(t: number): void {
    // F4 fix: guard against NaN (metadata not loaded) — never write NaN
    // into the video element.
    if (!Number.isFinite(t)) return;
    // 时长基准：优先 displayDuration（media.duration，真实总时长）。
    // 注意不能用 video.duration 优先——对后端转码流（前端误判为直连时），
    // video.duration 只显示已缓冲部分（实测 HEVC MP4 = 10s），会把 seek 目标
    // 钳制到缓冲尾（拖 50% 却只跳到 10s）。video.duration 仅在 media.duration
    // 缺失（未刮削）时兜底。
    let dur = Number.isFinite(displayDuration) && displayDuration > 0 ? displayDuration : 0;
    if (dur <= 0 && videoEl && Number.isFinite(videoEl.duration) && videoEl.duration > 0) {
      dur = videoEl.duration;
    }
    if (dur <= 0 && Number.isFinite(duration) && duration > 0) dur = duration;
    const target = Math.max(0, Math.min(dur, t));

    // 转码流：检查目标位置是否在已缓冲范围内
    if (needsTranscoding && videoEl) {
      const relativeTarget = target - streamStart;
      let isBuffered = false;
      for (let i = 0; i < videoEl.buffered.length; i++) {
        if (relativeTarget >= videoEl.buffered.start(i) - 1 && relativeTarget <= videoEl.buffered.end(i) + 1) {
          isBuffered = true;
          break;
        }
      }
      if (!isBuffered) {
        // 未缓冲：更新 streamStart 触发重新加载
        wasPlayingBeforeSeek = !paused;
        // 设置 seeking 标志：src 切换期间浏览器会中止上一个流请求，
        // 产生 ERR_ABORTED，在 onVideoError 中据此静默忽略
        seeking = true;
        streamStart = target;
        // 重载后视频从新流起点（相对 0）计时，相对基准归零——
        // 否则 displayTime = 新 streamStart + 旧 currentTime 会跳变
        currentTime = 0;
        // 安全兜底：5 秒后自动清除（防止 onLoadedMetadata 未触发时标志残留）
        setTimeout(() => { seeking = false; }, 5000);
        return;
      }
      // 已缓冲：在当前流内 seek
      if (videoEl) videoEl.currentTime = relativeTarget;
      currentTime = relativeTarget;
      return;
    }

    // 直接播放/未知流：先尝试原生 seek（显式写 DOM，不依赖 bind 反向同步），
    // 并验证浏览器是否接受——若被拒绝（该流实际不支持 Range，如后端转码流）
    // 自动降级为 streamStart 重载式 seek，彻底解决"拖动进度条跳回开头"。
    if (videoEl) {
      const before = videoEl.currentTime;
      videoEl.currentTime = target;
      currentTime = target;
      const my = { target, before };
      seekVerify = my;
      setTimeout(() => {
        if (seekVerify !== my || !videoEl) return;
        seekVerify = null;
        const v = videoEl;
        // 接受 = currentTime 严格接近目标。注意：浏览器把超范围 currentTime
        // clamp 到缓冲尾（如转码流 video.duration=10 → clamp 到 10）不算接受，
        // 必须接近目标才视为原生 seek 成功。
        const accepted = Math.abs(v.currentTime - my.target) < 2;
        if (!accepted) {
          // 被拒绝：流不支持范围 seek → 降级为转码式重载（?start=）
          fallbackTranscodeSeek(my.target);
        }
      }, 700);
    } else {
      currentTime = target;
    }
  }

  // 转码式 seek：更新 streamStart 触发 src 带 ?start= 重载（后端从该位置开始转码）
  function fallbackTranscodeSeek(target: number): void {
    wasPlayingBeforeSeek = !paused;
    // 设置 seeking 标志：src 切换期间浏览器会中止上一个流请求，
    // 产生 ERR_ABORTED，在 onVideoError 中据此静默忽略
    seeking = true;
    streamStart = target;
    // 重载后视频从新流起点（相对 0）计时，相对基准归零——
    // 否则 displayTime = 新 streamStart + 旧 currentTime 会跳变
    currentTime = 0;
    // 安全兜底：5 秒后自动清除（防止 onLoadedMetadata 未触发时标志残留）
    setTimeout(() => { seeking = false; }, 5000);
  }
  function seekRelative(d: number): void {
    seek(displayTime + d);
  }
  function step(d: number): void {
    seek(displayTime + d);
  }
  function stepFrame(forward: boolean): void {
    if (!paused) videoEl?.pause();
    seek(displayTime + (forward ? 1 / 30 : -1 / 30));
  }
  function seekPercent(p: number): void {
    seek((displayDuration * p) / 100);
  }
  function setVolume(v: number): void {
    volume = Math.max(0, Math.min(1, v));
    if (v > 0) {
      muted = false;
      lastVolume = volume;
      savePref('vitoice:lastVolume', lastVolume);
    }
  }
  /** 点击音量按钮：一键静音 / 一键恢复 */
  function toggleMute(): void {
    if (muted || volume === 0) {
      // 恢复：如果上次音量为 0 或不存在，给一个默认值
      const restore = lastVolume > 0 ? lastVolume : 0.8;
      volume = restore;
      muted = false;
    } else {
      // 静音：记住当前音量
      lastVolume = volume;
      savePref('vitoice:lastVolume', lastVolume);
      volume = 0;
      muted = true;
    }
  }
  function setSpeed(r: number): void {
    playbackRate = r;
    speedMenuOpen = false;
    if (media) {
      void client
        .post(`/media/${media.id}/progress`, { position: displayTime, speed: r })
        .catch(() => {});
    }
  }
  function toggleCaptions(): void {
    if (!hasSubtitle) return;
    captionsOn = !captionsOn;
    if (captionsOn && currentSubtitleId == null && media?.subtitles?.length) {
      currentSubtitleId = media.subtitles[0]?.id ?? null;
    }
  }
  function pickSubtitle(id: number): void {
    currentSubtitleId = id;
    captionsOn = true;
    subtitleMenuOpen = false;
  }

  // —— 全屏 ——
  // Tauri 桌面端优先使用原生 setFullscreen（覆盖任务栏），
  // 浏览器环境回退到 Fullscreen API。
  let isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
  let isMaximized = $state(false);

  /** 迷你置顶小窗：先落盘进度，暂停主播放，再开置顶 mini 窗口继续看 */
  async function openMiniWindow(): Promise<void> {
    if (!media) return;
    if (!isTauri) {
      toast('迷你小窗需要在 vitoice 客户端中使用');
      return;
    }
    try {
      const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow');
      const existing = await WebviewWindow.getByLabel('mini');
      if (existing) await existing.close();
      // 主播放器暂停并落盘进度，mini 窗口从后端读回续播
      videoEl?.pause();
      await saveProgress();
      new WebviewWindow('mini', {
        url: `/mini-player?id=${media.id}`,
        title: 'vitoice 迷你播放',
        // 16:9 视频比例的独立小窗（剥离 AppShell 后整窗即播放器）
        width: 480,
        height: 270,
        minWidth: 320,
        minHeight: 180,
        resizable: true,
        alwaysOnTop: true,
        decorations: false,
        skipTaskbar: true,
      });
    } catch (e) {
      console.warn('openMiniWindow failed:', e);
    }
  }

  async function getTauriWindow() {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      return getCurrentWindow();
    } catch {
      return null;
    }
  }

  async function minimizeWindow(): Promise<void> {
    (await getTauriWindow())?.minimize();
  }
  async function toggleMaximizeWindow(): Promise<void> {
    const win = await getTauriWindow();
    if (!win) return;
    // 手动"最大化到工作区"：任务栏保持可见（系统 maximize 在无边框窗口下会覆盖任务栏）
    isMaximized = await toggleWorkAreaMaximize(win);
  }
  async function closeWindow(): Promise<void> {
    (await getTauriWindow())?.close();
  }

  async function toggleBrowserFullscreen(): Promise<void> {
    if (isTauri) {
      try {
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const win = getCurrentWindow();
        const fs = await win.isFullscreen();
        await win.setFullscreen(!fs);
        return;
      } catch {
        /* Tauri API 不可用时回退 */
      }
    }
    if (!document.fullscreenElement) {
      containerEl?.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  }
  async function onFullscreenChange(): Promise<void> {
    if (isTauri) {
      try {
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const win = getCurrentWindow();
        isFullscreen = await win.isFullscreen();
        return;
      } catch {
        /* 回退到浏览器 API */
      }
    }
    isFullscreen = !!document.fullscreenElement;
  }

  // Tauri 窗口状态监听：setFullscreen 不会触发浏览器的 fullscreenchange 事件，
  // 需要通过 Tauri 的 onResized 监听窗口状态变化（同时同步最大化状态）。
  $effect(() => {
    if (!isTauri) return;
    let unlisten: (() => void) | null = null;
    (async () => {
      try {
        const { getCurrentWindow } = await import('@tauri-apps/api/window');
        const win = getCurrentWindow();
        isMaximized = (await win.isMaximized()) || isWorkAreaMaximized();
        unlisten = await win.onResized(async () => {
          isFullscreen = await win.isFullscreen();
          // 手动工作区最大化时系统 isMaximized() 返回 false，用尺寸判断
          const s = await win.outerSize();
          isMaximized = s ? sizeLooksMaximized(s) : await win.isMaximized();
        });
      } catch {
        /* ignore */
      }
    })();
    return () => { unlisten?.(); };
  });

  // —— 评分 / 收藏 ——
  async function rate(n: number): Promise<void> {
    if (!media) return;
    const next = media.rating === n ? 0 : n; // 再按一次取消
    media = { ...media, rating: next };
    try {
      await client.put(`/media/${media.id}`, { rating: next });
    } catch {
      /* ignore */
    }
  }
  async function toggleFavorite(): Promise<void> {
    if (!media) return;
    const fav = !media.is_favorite;
    media = { ...media, is_favorite: fav };
    try {
      await client.put(`/media/${media.id}`, { is_favorite: fav });
    } catch {
      /* ignore */
    }
  }

  // —— 片段标记 ——
  function markIn(): void {
    markStart = displayTime;
    toast('已标记片段起点');
  }
  function markOut(): void {
    if (markStart == null) {
      toast('请先按 I 标记起点');
      return;
    }
    if (displayTime <= markStart) {
      toast('终点需在起点之后');
      return;
    }
    segmentStart = markStart;
    segmentEnd = displayTime;
    segmentDialogOpen = true;
  }
  function onSegmentConfirm(seg: {
    id?: number;
    media_id?: number;
    name: string;
    start_time: number;
    end_time: number;
    color: string | null;
  }): void {
    if (media) {
      const newSeg: Segment = {
        id: seg.id ?? Date.now(),
        media_id: seg.media_id ?? media.id,
        name: seg.name,
        start_time: seg.start_time,
        end_time: seg.end_time,
        color: seg.color
      };
      const segs = [...(media.segments ?? []), newSeg].sort((a, b) => a.start_time - b.start_time);
      media = { ...media, segments: segs };
    }
    markStart = null;
    toast('片段已保存');
  }

  function seekToSegment(seg: Segment): void {
    seek(seg.start_time);
    toast(`跳转到 ${seg.name}`);
  }

  async function deleteSegment(seg: Segment): Promise<void> {
    deletingSegId = seg.id;
    try {
      await client.delete(`/segments/${seg.id}`);
      if (media) {
        const segs = (media.segments ?? []).filter((s) => s.id !== seg.id);
        media = { ...media, segments: segs };
      }
      toast('片段已删除');
    } catch (e) {
      console.error('[Player] 删除片段失败:', e);
      toast('删除片段失败');
    } finally {
      deletingSegId = null;
    }
  }

  // —— 快速打标 / AI 打标 ——
  function openQuickTag(): void {
    aiPreselect = [];
    quickTagOpen = true;
  }
  async function aiTag(): Promise<void> {
    if (!media) return;
    toast('AI 打标请求已发送…');
    try {
      await client.post(`/media/${media.id}/ai-tags`);
      toast('AI 打标完成');
    } catch {
      toast('AI 打标暂不可用，可使用快速打标 (T)');
      openQuickTag();
    }
  }

  // —— 截图 ——
  function downloadBlob(blob: Blob, name: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function writeClipboardImage(blob: Blob): Promise<boolean> {
    // 1) 尝试 Tauri 剪贴板插件（运行时动态加载，未安装时静默回退）
    try {
      // 使用非字面量模块标识符 + @vite-ignore，避免 TS 静态解析 / Vite 打包未安装的依赖
      const clipMod = '@tauri-apps/plugin-clipboard-manager';
      const mod: any = await import(/* @vite-ignore */ clipMod);
      const bytes = new Uint8Array(await blob.arrayBuffer());
      if (typeof mod.writeImage === 'function') {
        await mod.writeImage(Array.from(bytes));
        return true;
      }
      if (typeof mod.writeImageBase64 === 'function') {
        const b64 = btoa(String.fromCharCode(...bytes));
        await mod.writeImageBase64(b64);
        return true;
      }
    } catch {
      /* 插件未安装，回退 */
    }
    // 2) 浏览器剪贴板 API
    try {
      const ClipboardItemCtor = (window as any).ClipboardItem;
      if (ClipboardItemCtor && navigator.clipboard?.write) {
        await navigator.clipboard.write([
          new ClipboardItemCtor({ 'image/png': blob })
        ]);
        return true;
      }
    } catch {
      /* 可能跨域污染，回退 */
    }
    return false;
  }
  async function screenshot(toFile: boolean): Promise<void> {
    if (!videoEl || isImage) {
      toast(isImage ? '图片媒体不支持截图' : '无法截取当前帧');
      return;
    }
    const w = videoEl.videoWidth;
    const h = videoEl.videoHeight;
    if (!w || !h) {
      toast('视频尚未就绪');
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      toast('截图失败');
      return;
    }
    try {
      ctx.drawImage(videoEl, 0, 0, w, h);
    } catch {
      toast('截图失败（跨域限制）');
      return;
    }
    // 闪光
    flash = true;
    setTimeout(() => (flash = false), 180);

    const baseName = (media?.file_name ?? 'screenshot').replace(/\.[^.]+$/, '');
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);

    const blob: Blob | null = await new Promise((resolve) => {
      try {
        canvas.toBlob((b) => resolve(b), 'image/png');
      } catch {
        resolve(null);
      }
    });
    if (!blob) {
      toast('截图失败（跨域限制）');
      return;
    }

    if (toFile) {
      try {
        const { save } = await import('@tauri-apps/plugin-dialog');
        const { writeFile } = await import('@tauri-apps/plugin-fs');
        const path = await save({
          defaultPath: `${baseName}_${ts}.png`,
          filters: [{ name: 'PNG', extensions: ['png'] }]
        });
        if (path) {
          const buf = new Uint8Array(await blob.arrayBuffer());
          await writeFile(path, buf);
          toast('截图已保存到文件');
          return;
        }
        toast('已取消保存');
      } catch {
        downloadBlob(blob, `${baseName}_${ts}.png`);
        toast('截图已下载');
      }
    } else {
      const ok = await writeClipboardImage(blob);
      if (ok) toast('截图已复制到剪贴板');
      else {
        downloadBlob(blob, `${baseName}_${ts}.png`);
        toast('剪贴板不可用，已下载');
      }
    }
  }

  // —— 将当前帧设为封面 ——
  // 服务端 ffmpeg 从原文件精确抽取当前时间戳的帧（POST /media/{id}/poster-from-frame）：
  // 无 canvas 跨域污染问题、原生分辨率、与暂停画面逐帧一致；落盘后 poster_source="custom"
  // （刮削不覆盖），updated_at onupdate 自动破 7 天封面缓存。
  let settingCover = $state(false);
  async function setCoverFromFrame(): Promise<void> {
    if (!videoEl || isImage || !media) {
      toast(isImage ? '图片媒体无需设置封面' : '无法获取当前帧');
      return;
    }
    if (settingCover) return;
    settingCover = true;
    try {
      const t = videoEl.currentTime || 0;
      const resp = await fetch(
        `${BASE_URL}/media/${media.id}/poster-from-frame?t=${encodeURIComponent(String(t))}`,
        { method: 'POST' }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || '设置封面失败');
      }
      // 闪光反馈 + 通知列表/详情刷新（新 updated_at 破封面缓存）
      flash = true;
      setTimeout(() => (flash = false), 180);
      librariesStore.notifyChanged();
      toast('已将当前帧设为封面');
    } catch (e) {
      toast(e instanceof Error ? e.message : '设置封面失败');
    } finally {
      settingCover = false;
    }
  }

  // —— 控制层可见性 ——
  let hideTimer: ReturnType<typeof setTimeout> | null = null;
  function showControls(): void {
    controlsVisible = true;
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    hideTimer = setTimeout(() => {
      if (
        isPlaying &&
        !organizeVisible &&
        !anyDialogOpen &&
        !speedMenuOpen &&
        !subtitleMenuOpen &&
        !volumeOpen &&
        !segPanelOpen
      ) {
        controlsVisible = false;
      }
    }, 3000);
  }
  function onStageMouseMove(): void {
    showControls();
  }

  let organizeTimer: ReturnType<typeof setTimeout> | null = null;
  function showOrganize(): void {
    organizeVisible = true;
    showControls();
    if (organizePinned) return; // 锁定时常驻，不设定时器
    if (organizeTimer) clearTimeout(organizeTimer);
    organizeTimer = setTimeout(() => {
      organizeVisible = false;
      // 重新计算控制层显隐（播放中且无操作时 3 秒后自动隐藏）
      showControls();
    }, 5000);
  }
  function toggleOrganizePin(): void {
    organizePinned = !organizePinned;
    if (organizePinned) {
      organizeVisible = true;
      showControls();
    } else {
      organizeVisible = false;
      showControls();
    }
  }

  // —— 手势：单击 / 双击分区 / 长按 2× ——
  let clickTimer: ReturnType<typeof setTimeout> | null = null;
  let suppressClick = false;
  let pressTimer: ReturnType<typeof setTimeout> | null = null;
  let longPressActive = $state(false);
  let prevRate = 1;
  let pressStart = { x: 0, y: 0 };

  function onStageClick(e: MouseEvent): void {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    if (clickTimer) {
      clearTimeout(clickTimer);
      clickTimer = null;
      handleDoubleClick(e);
      return;
    }
    clickTimer = setTimeout(() => {
      clickTimer = null;
      if (!isImage) togglePlay();
      else showControls();
    }, 250);
  }
  function handleDoubleClick(e: MouseEvent): void {
    const target = e.currentTarget as HTMLElement;
    const rect = target.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const third = rect.width / 3;
    if (x < third) {
      seekRelative(-10);
    } else if (x > third * 2) {
      seekRelative(10);
    } else {
      toggleBrowserFullscreen();
    }
    showControls();
  }
  function onStagePointerDown(e: PointerEvent): void {
    if (isImage) return;
    // F2 fix: pointerdown on control-bar buttons/progress bar bubbles up
    // to the stage; only start the long-press (2x speed) gesture on the
    // bare stage/video area, never on interactive controls.
    const target = e.target as HTMLElement | null;
    if (target?.closest?.('.bottom-controls,.top-bar,.play-center,.seg-panel')) return;
    pressStart = { x: e.clientX, y: e.clientY };
    pressTimer = setTimeout(() => {
      longPressActive = true;
      prevRate = playbackRate;
      playbackRate = 2;
      showControls();
    }, 500);
  }
  function onStagePointerMove(e: PointerEvent): void {
    if (!pressTimer) return;
    const dx = e.clientX - pressStart.x;
    const dy = e.clientY - pressStart.y;
    if (Math.hypot(dx, dy) > 10) {
      clearTimeout(pressTimer);
      pressTimer = null;
    }
  }
  function onStagePointerUp(): void {
    if (pressTimer) {
      clearTimeout(pressTimer);
      pressTimer = null;
    }
    if (longPressActive) {
      longPressActive = false;
      playbackRate = prevRate;
      suppressClick = true;
    }
  }

  // —— 快捷键 ——
  function onKeydown(e: KeyboardEvent): void {
    // Esc 分层处理
    if (e.key === 'Escape') {
      e.preventDefault();
      if (segmentDialogOpen) {
        segmentDialogOpen = false;
        return;
      }
      if (quickTagOpen) {
        quickTagOpen = false;
        return;
      }
      if (segPanelOpen) {
        segPanelOpen = false;
        return;
      }
      if (organizeVisible) {
        organizeVisible = false;
        organizePinned = false;
        return;
      }
      if (subtitleMenuOpen) {
        subtitleMenuOpen = false;
        return;
      }
      if (speedMenuOpen) {
        speedMenuOpen = false;
        return;
      }
      if (volumeOpen) {
        volumeOpen = false;
        return;
      }
      if (isFullscreen) {
        toggleBrowserFullscreen();
        return;
      }
      exitPlayer();
      return;
    }

    // 对话框打开时仅响应 Esc（其余交给对话框/输入框）
    if (anyDialogOpen) return;

    const target = e.target as HTMLElement | null;
    // F8 fix: also skip shortcuts when a <select> (speed/quality menu) has
    // focus — space would otherwise toggle play and preventDefault would
    // block the native dropdown from opening.
    const inInput =
      target &&
      (target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable);
    if (inInput) return;

    const key = e.key.toLowerCase();

    // Shift+S 截图到文件
    if (key === 's' && e.shiftKey) {
      e.preventDefault();
      void screenshot(true);
      showOrganize();
      return;
    }
    // 1-5 评分
    if (key >= '1' && key <= '5' && !e.shiftKey) {
      e.preventDefault();
      void rate(Number(key));
      showOrganize();
      return;
    }
    // 0 / 6-9 跳转 N*10%
    if (key === '0' || (key >= '6' && key <= '9')) {
      e.preventDefault();
      seekPercent(Number(key) * 10);
      showControls();
      return;
    }

    switch (key) {
      case ' ':
      case 'spacebar':
        e.preventDefault();
        // 若控制按钮被聚焦，失焦以免 keyup 再次激活按钮造成双重切换
        if (
          document.activeElement instanceof HTMLElement &&
          document.activeElement.tagName === 'BUTTON'
        ) {
          document.activeElement.blur();
        }
        void togglePlay();
        showControls();
        break;
      case 'j':
        e.preventDefault();
        seekRelative(-10);
        showControls();
        break;
      case 'l':
        e.preventDefault();
        seekRelative(10);
        showControls();
        break;
      case 'arrowleft':
        e.preventDefault();
        step(-settingsStore.stepSize);
        showControls();
        break;
      case 'arrowright':
        e.preventDefault();
        step(settingsStore.stepSize);
        showControls();
        break;
      case ',':
        e.preventDefault();
        stepFrame(false);
        showControls();
        break;
      case '.':
        e.preventDefault();
        stepFrame(true);
        showControls();
        break;
      case 'i':
        e.preventDefault();
        markIn();
        showOrganize();
        break;
      case 'o':
        e.preventDefault();
        markOut();
        showOrganize();
        break;
      case 't':
        e.preventDefault();
        openQuickTag();
        break;
      case 'a':
        e.preventDefault();
        void aiTag();
        showOrganize();
        break;
      case 's':
        e.preventDefault();
        void screenshot(false);
        showOrganize();
        break;
      case 'r':
        e.preventDefault();
        void toggleFavorite();
        showOrganize();
        break;
      case 'c':
        e.preventDefault();
        toggleCaptions();
        showOrganize();
        break;
      case 'f':
        e.preventDefault();
        toggleBrowserFullscreen();
        break;
      case 'm':
        e.preventDefault();
        toggleMute();
        showControls();
        break;
      case 'x':
        e.preventDefault();
        toggleOrganizePin();
        showControls();
        break;
    }
  }

  // —— Toast ——
  function toast(msg: string): void {
    toastMsg = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastMsg = null;
    }, 2200);
  }

  // —— 退出 ——
  // 优先返回来源页面（from 参数），避免 history.back() 的不可预测导航。
  // 用 replaceState 替换当前播放器记录——从详情页进播放器再退出时，
  // history 栈仍是 列表→详情，详情页的"返回"按钮会正确回到媒体列表，
  // 而不是回到播放器（旧记录）。
  function exitPlayer(): void {
    void saveProgress();
    const from = $page.url.searchParams.get('from');
    if (from) {
      goto(decodeURIComponent(from), { replaceState: true });
    } else {
      goto('/media', { replaceState: true });
    }
  }

  // —— 从网络源播放（平台链接在系统浏览器打开）——
  function playFromNetwork(): void {
    if (fileMissingInfo?.networkUrl) {
      openExternalUrl(fileMissingInfo.networkUrl);
    }
  }

  // —— 关闭文件丢失对话框 ——
  function dismissFileMissing(): void {
    fileMissingInfo = null;
  }

  // —— 挂载守卫：首次渲染完成后再启用 transform 过渡 ——
  onMount(() => {
    // 使用 requestAnimationFrame 确保按钮已在目标位置渲染完毕，
    // 之后再启用 transition，避免从默认位置到 translate(-50%, -50%) 的漂移动画
    requestAnimationFrame(() => {
      playerMounted = true;
    });
  });

  // —— 清理 ——
  onDestroy(() => {
    void saveProgress();
    if (hlsInstance) {
      hlsInstance.destroy();
      hlsInstance = null;
    }
    if (hideTimer) clearTimeout(hideTimer);
    if (organizeTimer) clearTimeout(organizeTimer);
    if (clickTimer) clearTimeout(clickTimer);
    cancelEndTimer();
    if (pressTimer) clearTimeout(pressTimer);
    if (toastTimer) clearTimeout(toastTimer);
  });
</script>

<svelte:head>
  <title>{title} — 播放器</title>
</svelte:head>

<svelte:window
  onkeydown={onKeydown}
  onfullscreenchange={onFullscreenChange}
  onvisibilitychange={onVisibility}
/>

<div class="player-root" bind:this={containerEl} class:fs={isFullscreen}>
  {#if loading}
    <div class="state-screen">
      <div class="spinner"></div>
      <div class="state-text">加载中…</div>
    </div>
  {:else if loadError}
    <div class="state-screen">
      <div class="state-text err">{loadError}</div>
      <button class="back-btn" onclick={exitPlayer}>返回</button>
    </div>
  {:else if !media}
    <div class="state-screen">
      <div class="state-text">未指定要播放的媒体</div>
      <button class="back-btn" onclick={() => goto('/media?mode=library')}>返回媒体库</button>
    </div>
  {:else if fileMissingInfo}
    <div class="state-screen file-missing-screen">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.4">
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <div class="state-text">{fileMissingInfo.isPlatform ? '需要外部播放器' : '本地文件已丢失'}</div>
      <div class="state-subtitle">{media.title || media.file_name}</div>
      {#if fileMissingInfo.hasNetwork && fileMissingInfo.isPlatform}
        <p class="missing-hint">此媒体为平台链接（YouTube/Bilibili 等），无法在播放器内联播放。点击下方按钮在新标签页中打开。</p>
        <div class="missing-actions">
          <button class="back-btn primary" onclick={playFromNetwork}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/>
            </svg>
            在新标签页打开
          </button>
          <button class="back-btn" onclick={exitPlayer}>返回</button>
        </div>
      {:else}
        <p class="missing-hint">无法播放此媒体。请恢复本地文件或从管理页删除此记录。</p>
        <div class="missing-actions">
          <button class="back-btn" onclick={exitPlayer}>返回</button>
        </div>
      {/if}
    </div>
  {:else if networkPlayError}
    <div class="state-screen">
      <div class="state-text err">{networkPlayError}</div>
      <div class="missing-actions">
        {#if canRefreshAdultSource}
          <button class="back-btn primary" onclick={refreshAdultSource} disabled={refreshingSource}>
            <svg viewBox="0 0 24 24" width="15" height="15"><path d="M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" fill="currentColor"/></svg>
            {refreshingSource ? '刷新中…' : '刷新源'}
          </button>
        {/if}
        <button class="back-btn" onclick={exitPlayer}>返回</button>
      </div>
    </div>
  {:else}
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div
      class="stage"
      role="presentation"
      class:cursor-hidden={!controlsVisible && isPlaying && !anyDialogOpen}
      onpointerdown={onStagePointerDown}
      onpointermove={onStagePointerMove}
      onpointerup={onStagePointerUp}
      onpointerleave={onStagePointerUp}
      onclick={onStageClick}
      onmousemove={onStageMouseMove}
    >
      {#if isImage}
        <img class="media-image" src={streamUrl} alt={title} draggable="false" />
      {:else}
        <!-- svelte-ignore a11y_media_has_caption -->
        <video
          bind:this={videoEl}
          bind:duration
          bind:paused
          bind:volume
          bind:muted
          bind:playbackRate
          src={networkMode === 'hls' ? undefined : streamUrl}
          poster={effectivePoster}
          preload="auto"
          playsinline
          onprogress={onProgress}
          ontimeupdate={onTimeUpdate}
          onloadedmetadata={onLoadedMetadata}
          onwaiting={() => (waiting = true)}
          onplaying={() => (waiting = false)}
          oncanplay={() => (waiting = false)}
          onended={onEnded}
          onerror={onVideoError}
        ></video>
      {/if}

      <!-- 限制内容遮罩 -->
      {#if isRestrictedMedia}
        <div class="restricted-mask">
          <span class="restricted-icon">🔞</span>
          <span class="restricted-text">限制内容</span>
        </div>
      {/if}

      <!-- 字幕轨道 -->
      <SubtitleTrack
        subtitle={currentSubtitle}
        mediaId={String(media.id)}
        currentTime={displayTime}
        enabled={captionsOn && !isImage}
      />

      <!-- 长按 2× 提示 -->
      {#if longPressActive}
        <div class="speed-badge">2× 长按快进</div>
      {/if}

      <!-- 缓冲 / Seek 加载指示 -->
      {#if (waiting || seeking) && !isImage}
        <div class="spinner big"></div>
      {/if}

      <!-- 顶部栏 -->
      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
      <div class="top-bar" role="presentation" class:visible={controlsVisible || paused} onclick={(e) => e.stopPropagation()} data-tauri-drag-region>
        <button class="ctl back" data-tauri-drag-region="false" onclick={exitPlayer} title="返回 (Esc)" aria-label="返回">‹</button>
        <div class="top-title" title={title} data-tauri-drag-region>{title}</div>
        {#if markStart != null}
          <div class="mark-chip" title="已标记片段起点">
            <span class="dot"></span>起点 {formatTime(markStart)} <span class="muted">按 O 结束</span>
          </div>
        {/if}
        <div class="top-spacer" data-tauri-drag-region></div>
        {#if isTauri}
          <div class="win-controls" data-tauri-drag-region="false">
            <button class="win-btn" onclick={minimizeWindow} aria-label="最小化" title="最小化">
              <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4">
                <line x1="3" y1="6" x2="9" y2="6" stroke-linecap="round"></line>
              </svg>
            </button>
            <button class="win-btn" onclick={toggleMaximizeWindow} aria-label="最大化/还原" title="最大化/还原">
              {#if isMaximized}
                <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4">
                  <rect x="3.5" y="4.5" width="5" height="5" rx="0.8"></rect>
                  <path d="M4.5 4.5V3.5h5v5h-1" stroke-opacity="0.55" stroke-linejoin="round"></path>
                </svg>
              {:else}
                <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4">
                  <rect x="3" y="3" width="6" height="6" rx="1"></rect>
                </svg>
              {/if}
            </button>
            <button class="win-btn close" onclick={closeWindow} aria-label="关闭" title="关闭">
              <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4">
                <line x1="3.5" y1="3.5" x2="8.5" y2="8.5" stroke-linecap="round"></line>
                <line x1="8.5" y1="3.5" x2="3.5" y2="8.5" stroke-linecap="round"></line>
              </svg>
            </button>
          </div>
        {/if}
      </div>

      <!-- 中央播放按钮（暂停时） -->
      {#if paused && !isImage && !waiting}
        <button
          class="play-center"
          class:mounted={playerMounted}
          onclick={(e) => {
            e.stopPropagation();
            void togglePlay();
          }}
          title="播放 (Space)"
          aria-label="播放"
        >▶</button>
      {/if}

      <!-- 底部控制层 -->
      <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
      <div class="bottom-controls" role="presentation" class:visible={controlsVisible || paused} onclick={(e) => e.stopPropagation()} onmousemove={() => showControls()}>
        <!-- 第 0 层：整理带（快捷键唤起）——置于进度条上方，
             出现/消失时不挤动进度条，避免进度条上下跳动 -->
        {#if organizeVisible}
          <div class="organize-row">
            <OrganizeStrip
              {rating}
              {favorite}
              {hasSubtitle}
              {captionsOn}
              {markStart}
              onMarkIn={markIn}
              onMarkOut={markOut}
              onQuickTag={openQuickTag}
              onAiTag={aiTag}
              onRate={(n) => rate(n)}
              onToggleFavorite={toggleFavorite}
              onScreenshot={(toFile) => screenshot(toFile)}
              onToggleCaptions={toggleCaptions}
            />
          </div>
        {/if}

        <!-- 第 1 层：进度条（播放时也常驻） -->
        <div class="progress-row">
          <ProgressBar
            current={displayTime}
            duration={displayDuration}
            buffered={displayBuffered}
            segments={segAnchors}
            onSeek={seek}
            mediaId={String(media.id)}
            thumbnailUrl={posterUrl}
          />
        </div>

        <!-- 第 1.5 层：多源切换（网络媒体有多个 source 时显示） -->
        {#if showSourceSwitch}
          <div class="source-switch-row">
            <span class="source-switch-label">源</span>
            {#each playableSources as s, i (s.id)}
              <button
                class="source-switch-btn"
                class:active={i === activeSourceIdx}
                onclick={() => switchSource(i)}
                title={s.url}
              >
                {s.platform || `源 ${i + 1}`}
              </button>
            {/each}
          </div>
        {/if}

        <!-- 第 2 层：按钮行（hover 显示） -->
        <div class="buttons-row">
          <button class="ctl" onclick={togglePlay} title="播放/暂停 (Space)" aria-label="播放/暂停">
            {paused ? '▶' : '❚❚'}
          </button>

          <!-- 音量：单击静音/恢复，悬停展开滑块 -->
          <div
            class="pop-wrap vol-hover-wrap"
            onmouseenter={() => (volumeOpen = true)}
            onmouseleave={() => (volumeOpen = false)}
          >
            <button
              class="ctl"
              onclick={toggleMute}
              title={muted || volume === 0 ? '点击恢复音量 (M)' : '点击静音 (M)'}
              aria-label="音量"
            >
              {muted || volume === 0 ? '🔇' : volume < 0.5 ? '🔉' : '🔊'}
            </button>
            {#if volumeOpen}
              <div class="pop vol-pop">
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={volume}
                  oninput={(e) => setVolume(Number((e.target as HTMLInputElement).value))}
                  aria-label="音量"
                />
                <button class="ctl mini" onclick={toggleMute} title="静音切换 (M)">{muted || volume === 0 ? '🔇' : '🔊'}</button>
              </div>
            {/if}
          </div>

          <div class="time">
            <span class="cur">{formatTime(displayTime)}</span>
            <span class="sep">/</span>
            <span class="dur">{formatTime(displayDuration)}</span>
          </div>

          <!-- 清晰度（仅 HLS 多档流显示） -->
          {#if showQualityMenu}
            <div class="pop-wrap">
              <button class="ctl" onclick={() => (qualityOpen = !qualityOpen)} title="清晰度" aria-label="清晰度">
                {currentQualityLabel}
              </button>
              {#if qualityOpen}
                <div class="pop quality-pop">
                  <button class="quality-item" class:active={currentLevelIdx === -1} onclick={() => setQuality(-1)}>自动</button>
                  {#each hlsLevels as lv, i (lv.height)}
                    <button class="quality-item" class:active={i === currentLevelIdx} onclick={() => setQuality(i)}>
                      {lv.height}p{lv.bitrate ? ` · ${Math.round(lv.bitrate / 1000)}kbps` : ''}
                    </button>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}

          <div class="spacer"></div>

          <!-- 速度 -->
          <div class="pop-wrap">
            <button
              class="ctl"
              class:on={playbackRate !== 1}
              onclick={() => (speedMenuOpen = !speedMenuOpen)}
              title="播放速度"
            >
              {playbackRate}×
            </button>
            {#if speedMenuOpen}
              <div class="backdrop" onclick={() => (speedMenuOpen = false)} role="presentation"></div>
              <div class="pop speed-pop">
                {#each SPEEDS as sp}
                  <button
                    class="menu-item"
                    class:active={sp === playbackRate}
                    onclick={() => setSpeed(sp)}
                  >
                    {sp}×{sp === 1 ? ' 正常' : ''}
                    {#if sp === playbackRate}<span class="tick">✓</span>{/if}
                  </button>
                {/each}
              </div>
            {/if}
          </div>

          <!-- 字幕 -->
          <div class="pop-wrap">
            <button
              class="ctl"
              class:on={captionsOn}
              onclick={() => (hasSubtitle ? (subtitleMenuOpen = !subtitleMenuOpen) : toggleCaptions())}
              disabled={!hasSubtitle}
              title="字幕 (C)"
            >
              CC
            </button>
            {#if subtitleMenuOpen}
              <div class="backdrop" onclick={() => (subtitleMenuOpen = false)} role="presentation"></div>
              <div class="pop sub-pop">
                <div class="menu-head">字幕轨道</div>
                <button
                  class="menu-item"
                  class:active={!captionsOn}
                  onclick={() => {
                    captionsOn = false;
                    subtitleMenuOpen = false;
                  }}
                >
                  关闭{!captionsOn ? ' ✓' : ''}
                </button>
                {#each media.subtitles ?? [] as sub (sub.id)}
                  <button
                    class="menu-item"
                    class:active={captionsOn && currentSubtitleId === sub.id}
                    onclick={() => pickSubtitle(sub.id)}
                  >
                    <span class="lang">{sub.language}</span>
                    <span class="muted">{sub.title ?? ''}</span>
                    {#if captionsOn && currentSubtitleId === sub.id}<span class="tick">✓</span>{/if}
                  </button>
                {/each}
              </div>
            {/if}
          </div>

          <!-- 将当前帧设为封面（本地文件专属：服务端从原文件抽帧） -->
          <button
            class="ctl"
            onclick={setCoverFromFrame}
            disabled={isImage || settingCover || !media?.file_path || !!media?.file_missing}
            title={media?.file_path ? '将当前帧设为封面' : '网络视频暂不支持从当前帧生成封面'}
            aria-label="将当前帧设为封面"
          >
            {settingCover ? '…' : '🖼'}
          </button>

          <!-- 整理带开关 -->
          <button
            class="ctl"
            class:on={organizePinned || organizeVisible}
            onclick={toggleOrganizePin}
            title="整理工具栏 (X)"
            aria-label="整理工具栏"
          >
            🔧
          </button>

          <!-- 片段列表 -->
          <button
            class="ctl seg-btn"
            class:on={segPanelOpen}
            onclick={() => { segPanelOpen = !segPanelOpen; showControls(); }}
            title="片段列表"
            aria-label="片段列表"
          >
            ⏱
            {#if media && (media.segments?.length ?? 0) > 0}
              <span class="seg-badge">{media.segments.length}</span>
            {/if}
          </button>

          <button class="ctl" onclick={openMiniWindow} title="迷你置顶小窗" aria-label="迷你置顶小窗">
            ⧉
          </button>

          <button class="ctl" onclick={toggleBrowserFullscreen} title="全屏 (F)" aria-label="全屏">
            {isFullscreen ? '🗗' : '⛶'}
          </button>
        </div>
      </div>

      <!-- 截图闪光 -->
      {#if flash}<div class="flash"></div>{/if}

      <!-- 片段列表面板 -->
      {#if segPanelOpen && media}
        <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
        <div class="seg-panel-backdrop" role="presentation" onclick={() => (segPanelOpen = false)}></div>
        <div class="seg-panel" onclick={(e) => e.stopPropagation()}>
          <div class="seg-panel-head">
            <span class="seg-panel-title">片段标记</span>
            <button class="seg-panel-close" onclick={() => (segPanelOpen = false)} aria-label="关闭片段列表">×</button>
          </div>
          {#if (media.segments?.length ?? 0) === 0}
            <div class="seg-panel-empty">
              <div class="seg-empty-icon">⏱</div>
              <div class="seg-empty-text">暂无片段</div>
              <div class="seg-empty-hint">按 I 标记起点，O 标记终点</div>
            </div>
          {:else}
            <div class="seg-list">
              {#each media.segments ?? [] as seg (seg.id)}
                <div class="seg-item" class:deleting={deletingSegId === seg.id}>
                  <button class="seg-item-main" onclick={() => seekToSegment(seg)} title="跳转到此片段">
                    <span
                      class="seg-color-dot"
                      style={seg.color ? `background:${seg.color}` : ''}
                    ></span>
                    <span class="seg-name">{seg.name}</span>
                    <span class="seg-time">
                      {formatTime(seg.start_time)}
                      {#if seg.end_time != null}–{formatTime(seg.end_time)}{/if}
                    </span>
                  </button>
                  <button
                    class="seg-del-btn"
                    onclick={() => deleteSegment(seg)}
                    disabled={deletingSegId === seg.id}
                    title="删除片段"
                    aria-label="删除片段"
                  >
                    {deletingSegId === seg.id ? '⋯' : '✕'}
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <!-- 播放结束：连播倒计时 / 推荐网格覆盖层 -->
    {#if endOverlayOpen}
      <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
      <div class="end-overlay" onclick={dismissEndOverlay}>
        <div class="end-panel" tabindex="-1" onclick={(e) => e.stopPropagation()} role="dialog" aria-label="播放结束">
          {#if endNextId != null && endCountdown > 0}
            <!-- 连播倒计时 -->
            <p class="end-label">本集播放结束</p>
            <h3 class="end-title">即将连播下一集</h3>
            <div class="end-countdown">{endCountdown}</div>
            <div class="end-actions">
              <button class="end-btn primary" onclick={() => void playNextNow()}>立即播放</button>
              <button class="end-btn" onclick={dismissEndOverlay}>取消</button>
            </div>
          {:else}
            <!-- 推荐网格 -->
            <p class="end-label">播放结束</p>
            <h3 class="end-title">接下来看</h3>
            <div class="rec-grid">
              {#each endRecItems as item (item.id)}
                <button class="rec-card" onclick={() => playRecItem(item)}>
                  <div class="rec-thumb">
                    {#if item.has_thumbnail}
                      <img src={mediaApi.thumbnailUrl(String(item.id))} alt={item.title} loading="lazy" />
                    {:else}
                      <span class="rec-thumb-empty">▶</span>
                    {/if}
                    {#if item.reason === 'series'}<span class="rec-badge">同系列</span>
                    {:else if item.reason === 'tag'}<span class="rec-badge">同标签</span>{/if}
                  </div>
                  <span class="rec-title">{item.title}</span>
                </button>
              {/each}
            </div>
            <div class="end-actions">
              <button class="end-btn" onclick={dismissEndOverlay}>关闭</button>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Toast -->
    {#if toastMsg}<div class="toast">{toastMsg}</div>{/if}

    <!-- 对话框 -->
    <SegmentDialog
      open={segmentDialogOpen}
      mediaId={String(media.id)}
      startTime={segmentStart}
      endTime={segmentEnd}
      onClose={() => (segmentDialogOpen = false)}
      onConfirm={onSegmentConfirm}
    />
    <QuickTagDialog
      open={quickTagOpen}
      mediaId={String(media.id)}
      preselectIds={aiPreselect}
      onClose={() => (quickTagOpen = false)}
    />
  {/if}
</div>

<style>
  .player-root {
    position: fixed;
    inset: 0;
    background: #000;
    color: #fff;
    overflow: hidden;
    z-index: 50;
  }
  .player-root:fullscreen {
    background: #000;
  }

  .state-screen {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    color: rgba(255, 255, 255, 0.8);
  }
  .state-text {
    font-size: 14px;
  }
  .state-text.err {
    color: #ff6b6b;
  }
  .back-btn {
    height: 34px;
    padding: 0 16px;
    border-radius: var(--radius);
    background: var(--accent);
    color: #fff;
    border: none;
    font-size: 13px;
    cursor: pointer;
    transition: filter 150ms;
  }
  .back-btn:hover {
    filter: brightness(1.1);
  }

  .file-missing-screen {
    background: rgba(0, 0, 0, 0.85);
  }
  .state-subtitle {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.5);
    max-width: 400px;
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .missing-hint {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.6);
    margin: 0;
    max-width: 360px;
    text-align: center;
    line-height: 1.5;
  }
  .missing-actions {
    display: flex;
    gap: 12px;
    margin-top: 8px;
  }
  .back-btn.primary {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .stage {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: default;
    user-select: none;
  }
  .stage.cursor-hidden {
    cursor: none;
  }
  .stage video,
  .stage .media-image {
    max-width: 100%;
    max-height: 100%;
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #000;
  }
  .media-image {
    object-fit: contain;
  }

  /* 顶部栏 */
  .top-bar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: linear-gradient(to bottom, rgba(0, 0, 0, 0.7), rgba(0, 0, 0, 0));
    opacity: 0;
    transform: translateY(-6px);
    transition: opacity 200ms ease, transform 200ms ease;
    pointer-events: none;
    z-index: 20;
  }
  .top-bar.visible {
    opacity: 1;
    transform: none;
    pointer-events: auto;
  }
  .top-title {
    font-size: 14px;
    font-weight: 600;
    color: #fff;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 60vw;
  }
  .mark-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--accent2);
    background: var(--accent2-soft);
    padding: 4px 10px;
    border-radius: var(--radius-full);
  }
  .mark-chip .dot {
    width: 7px;
    height: 7px;
    border-radius: var(--radius-full);
    background: var(--accent2);
  }
  .mark-chip .muted {
    color: rgba(255, 255, 255, 0.55);
  }
  .top-spacer {
    flex: 1;
  }

  /* 窗口控制按钮（Tauri 桌面端） */
  .win-controls {
    display: flex;
    align-items: center;
    gap: 2px;
    -webkit-app-region: no-drag;
    app-region: no-drag;
  }
  .win-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: none;
    border: none;
    border-radius: var(--radius);
    color: rgba(255, 255, 255, 0.85);
    cursor: default;
    transition: background 100ms ease, color 100ms ease;
  }
  .win-btn:hover {
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
  }
  .win-btn:active {
    transform: scale(0.92);
  }
  .win-btn.close:hover {
    background: var(--danger);
    color: #fff;
  }

  /* 中央播放按钮 */
  .play-center {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 72px;
    height: 72px;
    border-radius: var(--radius-full);
    border: none;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(6px);
    color: #fff;
    font-size: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    /* 首次渲染时不启用 transform 过渡，防止从默认位置漂移到居中位置 */
    transition: background 150ms;
    z-index: 15;
  }
  /* 挂载后才启用 transform 过渡（用于 hover 缩放效果） */
  .play-center.mounted {
    transition: transform 150ms, background 150ms;
  }
  .play-center:hover {
    background: var(--accent);
    transform: translate(-50%, -50%) scale(1.06);
  }

  /* 长按 2× 提示 */
  .speed-badge {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0, 0, 0, 0.7);
    color: var(--accent2);
    font-size: 14px;
    font-weight: 600;
    padding: 8px 16px;
    border-radius: var(--radius-full);
    pointer-events: none;
    z-index: 16;
  }

  /* 限制内容遮罩 */
  .restricted-mask {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.8);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    z-index: 20;
    pointer-events: none;
  }
  .restricted-icon {
    font-size: 48px;
    opacity: 0.7;
  }
  .restricted-text {
    color: rgba(255, 255, 255, 0.6);
    font-size: 16px;
    font-weight: 500;
    letter-spacing: 0.05em;
  }

  /* —— 播放结束覆盖层（连播 / 推荐网格）—— */
  .end-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.78);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 22;
    animation: end-fade 220ms ease;
  }
  @keyframes end-fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  .end-panel {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    max-width: 860px;
    max-height: 86%;
    padding: 28px 32px;
    overflow: auto;
  }
  .end-label {
    margin: 0;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.55);
    letter-spacing: 0.08em;
  }
  .end-title {
    margin: 0;
    font-size: 22px;
    font-weight: 600;
    color: #fff;
  }
  .end-countdown {
    width: 84px;
    height: 84px;
    border-radius: 50%;
    border: 3px solid rgba(255, 255, 255, 0.25);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 38px;
    font-weight: 700;
    color: var(--accent, #e5a95c);
  }
  .end-actions {
    display: flex;
    gap: 12px;
    margin-top: 4px;
  }
  .end-btn {
    padding: 9px 26px;
    border-radius: var(--radius-full, 999px);
    border: 1px solid rgba(255, 255, 255, 0.28);
    background: transparent;
    color: rgba(255, 255, 255, 0.85);
    font-size: 14px;
    cursor: pointer;
    transition: background 140ms, border-color 140ms;
  }
  .end-btn:hover {
    background: rgba(255, 255, 255, 0.12);
  }
  .end-btn.primary {
    background: var(--accent, #e5a95c);
    border-color: transparent;
    color: #1a1206;
    font-weight: 600;
  }
  .end-btn.primary:hover {
    filter: brightness(1.08);
  }
  .rec-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    width: 100%;
  }
  .rec-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 0;
    border: none;
    background: transparent;
    cursor: pointer;
    text-align: left;
  }
  .rec-thumb {
    position: relative;
    aspect-ratio: 16 / 9;
    border-radius: 8px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.08);
  }
  .rec-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 160ms ease;
  }
  .rec-card:hover .rec-thumb img {
    transform: scale(1.05);
  }
  .rec-thumb-empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: rgba(255, 255, 255, 0.4);
    font-size: 26px;
  }
  .rec-badge {
    position: absolute;
    top: 6px;
    left: 6px;
    padding: 2px 8px;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.65);
    color: var(--accent, #e5a95c);
    font-size: 11px;
    font-weight: 500;
  }
  .rec-title {
    font-size: 12.5px;
    color: rgba(255, 255, 255, 0.82);
    display: -webkit-box;
    -webkit-line-clamp: 1;
    line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  /* 缓冲 spinner */
  .spinner {
    width: 28px;
    height: 28px;
    border: 3px solid rgba(255, 255, 255, 0.25);
    border-top-color: #fff;
    border-radius: var(--radius-full);
    animation: spin 0.8s linear infinite;
  }
  .spinner.big {
    position: absolute;
    top: 50%;
    left: 50%;
    /* 用负 margin 居中而非 transform——transform 被 spin 动画的 rotate 占用，
       两者共用 transform 会导致动画期间 translate 失效、圆点向右下漂移 */
    margin: -24px 0 0 -24px;
    width: 48px;
    height: 48px;
    border-width: 4px;
    z-index: 14;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  /* 底部控制层 */
  .bottom-controls {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    padding: 36px 16px 12px;
    background: linear-gradient(to top, rgba(0, 0, 0, 0.85), rgba(0, 0, 0, 0.4) 60%, rgba(0, 0, 0, 0));
    opacity: 0;
    transform: translateY(8px);
    transition: opacity 200ms ease, transform 200ms ease;
    pointer-events: none;
    z-index: 20;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .bottom-controls.visible {
    opacity: 1;
    transform: none;
    pointer-events: auto;
  }

  .progress-row {
    padding: 0 4px;
  }

  .source-switch-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px 0;
    flex-wrap: wrap;
  }
  .source-switch-label {
    font-size: 11px;
    color: var(--ink-tertiary, #888);
    flex-shrink: 0;
  }
  .source-switch-btn {
    padding: 2px 10px;
    border: 1px solid var(--rule, rgba(255,255,255,0.12));
    border-radius: 999px;
    background: transparent;
    color: var(--ink-secondary, #aaa);
    font-size: 11.5px;
    cursor: pointer;
    transition: all 150ms ease;
  }
  .source-switch-btn:hover {
    border-color: var(--accent, #7c3aed);
    color: var(--ink, #fff);
  }
  .source-switch-btn.active {
    background: var(--accent, #7c3aed);
    border-color: var(--accent, #7c3aed);
    color: #fff;
  }

  .buttons-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 4px;
  }
  .spacer {
    flex: 1;
  }

  /* 控制按钮 */
  .ctl {
    height: 34px;
    min-width: 34px;
    padding: 0 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    border: none;
    background: transparent;
    color: rgba(255, 255, 255, 0.92);
    border-radius: var(--radius);
    font-size: 15px;
    cursor: pointer;
    transition: background 150ms, color 150ms, transform 120ms;
  }
  .ctl:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.12);
    color: var(--accent);
  }
  .ctl:active:not(:disabled) {
    transform: scale(0.94);
  }
  .ctl:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
  .ctl.on {
    color: var(--accent);
  }
  .ctl.back {
    font-size: 22px;
    width: 36px;
    height: 36px;
  }
  .ctl.mini {
    height: 28px;
    min-width: 28px;
    font-size: 13px;
  }

  .time {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 12.5px;
    font-variant-numeric: tabular-nums;
    color: rgba(255, 255, 255, 0.9);
    padding: 0 6px;
  }
  .time .sep {
    color: rgba(255, 255, 255, 0.4);
  }

  /* 弹出菜单 */
  .pop-wrap {
    position: relative;
  }
  /* 音量悬停区：面板紧贴按钮上方（无间隙），鼠标可直接移入 */
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 1;
  }
  .pop {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    background: rgba(20, 20, 22, 0.94);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: var(--radius-card);
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.5);
    z-index: 2;
    animation: pop 140ms ease;
  }
  @keyframes pop {
    from {
      opacity: 0;
      transform: translateX(-50%) translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
  }
  /* 无 X 偏移的弹出动画：供覆盖了 transform: none 的弹出框（音量/清晰度）使用。
     若沿用 pop 动画，其 from/to 帧硬编码 translateX(-50%)，播放时会先向一侧
     偏移再跳回正确位置。 */
  @keyframes pop-up {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  .vol-pop {
    /* Override .pop centering: volume button is near the left edge,
       so centering would push the popup off-screen to the left. */
    left: 0;
    transform: none;
    animation: pop-up 140ms ease;
    /* 紧贴按钮上方，不留间隙，避免鼠标移入时面板消失 */
    bottom: 100%;
    width: 200px;
    /* 滑块 + 静音按钮水平排列、垂直居中，拖动条在小框中间 */
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    box-sizing: border-box;
  }
  .quality-pop {
    left: auto;
    right: 0;
    transform: none;
    animation: pop-up 140ms ease;
    bottom: calc(100% + 8px);
    min-width: 150px;
    padding: 4px;
    max-height: 240px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .quality-item {
    text-align: left;
    padding: 5px 10px;
    border: none;
    background: none;
    color: rgba(255, 255, 255, 0.85);
    font-size: 12px;
    border-radius: 6px;
    cursor: pointer;
    white-space: nowrap;
  }
  .quality-item:hover {
    background: rgba(255, 255, 255, 0.1);
  }
  .quality-item.active {
    color: var(--accent, #7c3aed);
    background: rgba(124, 58, 237, 0.15);
    font-weight: 600;
  }
  @keyframes pop-left {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .vol-pop input[type='range'] {
    flex: 1;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: rgba(255, 255, 255, 0.25);
    border-radius: var(--radius-full);
    outline: none;
  }
  .vol-pop input[type='range']::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 14px;
    height: 14px;
    border-radius: var(--radius-full);
    background: var(--accent);
    cursor: pointer;
    border: none;
  }
  .vol-pop input[type='range']::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border-radius: var(--radius-full);
    background: var(--accent);
    cursor: pointer;
    border: none;
  }

  .speed-pop,
  .sub-pop {
    min-width: 150px;
    padding: 6px;
  }
  .menu-head {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: rgba(255, 255, 255, 0.45);
    padding: 6px 10px 4px;
  }
  .menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border: none;
    background: transparent;
    color: rgba(255, 255, 255, 0.88);
    font-size: 13px;
    text-align: left;
    border-radius: var(--radius);
    cursor: pointer;
    transition: background 120ms, color 120ms;
  }
  .menu-item:hover {
    background: rgba(255, 255, 255, 0.1);
    color: var(--accent);
  }
  .menu-item.active {
    color: var(--accent);
  }
  .menu-item .lang {
    font-weight: 600;
  }
  .menu-item .muted {
    color: rgba(255, 255, 255, 0.45);
    font-size: 12px;
  }
  .menu-item .tick {
    margin-left: auto;
    color: var(--accent);
  }

  /* 整理带行 */
  .organize-row {
    display: flex;
    justify-content: center;
    padding-top: 4px;
    animation: rise 180ms ease;
  }
  @keyframes rise {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: none;
    }
  }

  /* 闪光 */
  .flash {
    position: absolute;
    inset: 0;
    background: #fff;
    opacity: 0.6;
    pointer-events: none;
    z-index: 30;
    animation: flash 180ms ease-out;
  }
  @keyframes flash {
    from {
      opacity: 0.7;
    }
    to {
      opacity: 0;
    }
  }

  /* Toast */
  .toast {
    position: absolute;
    bottom: 110px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(20, 20, 22, 0.92);
    backdrop-filter: blur(10px);
    color: #fff;
    font-size: 13px;
    padding: 9px 16px;
    border-radius: var(--radius-full);
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
    pointer-events: none;
    z-index: 40;
    animation: toast 180ms ease;
    max-width: 80vw;
    text-align: center;
  }
  @keyframes toast {
    from {
      opacity: 0;
      transform: translateX(-50%) translateY(6px);
    }
    to {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
  }

  /* 片段按钮徽标 */
  .seg-btn {
    position: relative;
  }
  .seg-badge {
    position: absolute;
    top: -2px;
    right: -2px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: var(--radius-full);
    background: var(--accent2);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }

  /* 片段列表面板 */
  .seg-panel-backdrop {
    position: absolute;
    inset: 0;
    z-index: 24;
  }
  .seg-panel {
    position: absolute;
    top: 56px;
    right: 16px;
    bottom: 90px;
    width: min(320px, 90vw);
    background: rgba(20, 20, 22, 0.94);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: var(--radius-card);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
    z-index: 25;
    display: flex;
    flex-direction: column;
    animation: segPanelIn 180ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  @keyframes segPanelIn {
    from { opacity: 0; transform: translateX(20px); }
    to { opacity: 1; transform: none; }
  }
  .seg-panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-shrink: 0;
  }
  .seg-panel-title {
    font-size: 14px;
    font-weight: 700;
    color: #fff;
  }
  .seg-panel-close {
    width: 28px;
    height: 28px;
    border: none;
    background: none;
    color: rgba(255, 255, 255, 0.5);
    font-size: 20px;
    line-height: 1;
    border-radius: var(--radius);
    cursor: pointer;
    transition: background 150ms, color 150ms;
  }
  .seg-panel-close:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
  }

  /* 空状态 */
  .seg-panel-empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 24px;
  }
  .seg-empty-icon {
    font-size: 32px;
    opacity: 0.4;
  }
  .seg-empty-text {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.7);
    font-weight: 600;
  }
  .seg-empty-hint {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.4);
  }

  /* 片段列表 */
  .seg-list {
    flex: 1;
    overflow-y: auto;
    padding: 6px 8px;
    min-height: 0;
  }
  .seg-list::-webkit-scrollbar {
    width: 5px;
  }
  .seg-list::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.15);
    border-radius: 3px;
  }
  .seg-item {
    display: flex;
    align-items: center;
    gap: 2px;
    border-radius: var(--radius);
    transition: background 120ms;
  }
  .seg-item:hover {
    background: rgba(255, 255, 255, 0.06);
  }
  .seg-item.deleting {
    opacity: 0.5;
  }
  .seg-item-main {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 8px;
    border: none;
    background: none;
    color: rgba(255, 255, 255, 0.88);
    text-align: left;
    cursor: pointer;
    border-radius: var(--radius);
    min-width: 0;
    transition: color 120ms;
  }
  .seg-item-main:hover {
    color: var(--accent);
  }
  .seg-color-dot {
    width: 9px;
    height: 9px;
    border-radius: var(--radius-full);
    background: var(--neutral, #888);
    flex-shrink: 0;
    box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.15);
  }
  .seg-name {
    flex: 1;
    font-size: 13px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .seg-time {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.45);
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }
  .seg-del-btn {
    width: 28px;
    height: 28px;
    border: none;
    background: none;
    color: rgba(255, 255, 255, 0.35);
    font-size: 12px;
    cursor: pointer;
    border-radius: var(--radius);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 120ms, color 120ms;
  }
  .seg-del-btn:hover:not(:disabled) {
    background: rgba(255, 59, 48, 0.15);
    color: #ff3b30;
  }
  .seg-del-btn:disabled {
    cursor: wait;
  }
</style>
