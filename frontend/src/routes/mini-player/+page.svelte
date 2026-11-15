<script lang="ts">
  /**
   * 迷你置顶小窗（由主播放器「小窗」按钮经 Rust open_mini_window 创建的
   * Tauri WebviewWindow，label=mini）。极简播放：自动续播 + 播放/暂停 + 进度条
   * + 音量 + 回到主窗。
   *
   * 与主播放页共用 PlayerKernel：桌面端画面由 mpv 子窗口渲染（因此窗口建的时候
   * 就把 WebView2 底刷成透明），浏览器调试时回退 <video>。进度仍写后端
   * /media/{id}/progress，主播放器下次打开自动续上。
   */
  import { onMount, onDestroy, untrack } from 'svelte';
  import { client } from '$lib/api/client';
  import { mediaApi, type MediaPayload } from '$lib/api/media';
  import { realQueryParam } from '$lib/utils/urlState';
  import { PlayerKernel } from '$lib/player/kernel.svelte';
  import { resolveWindowLabel } from '$lib/player/mpv';

  // 读 window.location 而非 $page.url：popstate 重挂载时 page store 会丢 query。
  const mediaId = realQueryParam('id') ?? '';

  const kernel = new PlayerKernel(resolveWindowLabel());

  let stageEl = $state<HTMLDivElement | null>(null);
  let videoEl = $state<HTMLVideoElement | null>(null);
  let title = $state('');
  let loadError = $state<string | null>(null);
  let playing = $state(false);
  let duration = $state(0);
  let position = $state(0);
  let volume = $state(1);
  let muted = $state(false);

  let lastSaved = 0;
  let streamUrl = $state('');

  /** 迷你窗只播本地文件：mpv 直接读绝对路径，浏览器回退走后端 HTTP 流。 */
  async function resolveStreamUrl(): Promise<string> {
    if (!mediaId) return '';
    try {
      const raw = await client.get<Partial<MediaPayload>>(`/media/${mediaId}`);
      title = raw?.title ?? raw?.file_name ?? '';
      if (raw?.file_missing || raw?.media_type === 'network') {
        loadError = '迷你小窗仅支持本地文件播放';
        return '';
      }
      // file_path 已被后端脱敏，mpv 只能吃未脱敏的 local_path（详情接口才有）。
      return kernel.native ? raw?.local_path ?? '' : mediaApi.streamUrl(mediaId);
    } catch {
      loadError = '加载媒体失败';
      return '';
    }
  }

  async function saveProgress(force = false): Promise<void> {
    if (!mediaId || !kernel.ready) return;
    const now = Date.now();
    if (!force && now - lastSaved < 8000) return;
    lastSaved = now;
    void client
      .post(`/media/${mediaId}/progress`, { position: kernel.currentTime, speed: 1 })
      .catch(() => {});
  }

  onMount(() => {
    if (!mediaId) {
      loadError = '缺少媒体 ID';
      return;
    }
    // mpv 模式下 WebView 必须整体透明，否则会盖住下层 mpv 子窗口的画面。
    if (kernel.native) document.documentElement.classList.add('vitoice-player-native');

    kernel.onLoadedMetadata = () => {
      void kernel.play();
    };

    void (async () => {
      await kernel.init();
      const url = await resolveStreamUrl();
      if (!url) {
        if (!loadError) loadError = '无法播放此媒体';
        return;
      }
      streamUrl = url;
      // 续播：主播放器暂停时已把进度写后端，这里读回并作为起播位置交给内核。
      let pos = 0;
      try {
        const raw = await client.get<Partial<MediaPayload>>(`/media/${mediaId}`);
        pos = raw?.playback_position ?? 0;
      } catch {
        /* 无进度 → 从头播 */
      }
      kernel.setResume(pos > 1 ? pos : 0);
      await kernel.load({ url });
    })();

    // 窗口关闭/隐藏前尽力保存进度
    const onHide = () => void saveProgress(true);
    window.addEventListener('pagehide', onHide);
    document.addEventListener('visibilitychange', onHide);
    return () => {
      window.removeEventListener('pagehide', onHide);
      document.removeEventListener('visibilitychange', onHide);
      void saveProgress(true);
    };
  });

  onDestroy(() => {
    document.documentElement.classList.remove('vitoice-player-native');
    void kernel.destroy();
  });

  // 内核状态 → 页面镜像（进度条/按钮只读这几个变量）。
  $effect(() => {
    if (!kernel.native) return;
    playing = !kernel.paused;
    position = kernel.currentTime;
    duration = kernel.duration;
  });

  // 音量/静音由页面偏好单向驱动内核。
  $effect(() => {
    if (!kernel.native || !kernel.ready) return;
    void kernel.setVolume(volume);
  });
  $effect(() => {
    if (!kernel.native || !kernel.ready) return;
    void kernel.setMuted(muted);
  });

  // 舞台矩形 → mpv 画面内缩比例：mpv 子窗口铺满整个客户区，必须把画面限制在
  // 标题条与进度条之间的视频区，否则画面会被两侧控制层压扁/错位。
  $effect(() => {
    if (!kernel.native || !kernel.ready) return;
    const el = stageEl;
    if (!el) return;
    let lastKey = '';
    const apply = (): void => {
      const r = el.getBoundingClientRect();
      const vw = window.innerWidth || 1;
      const vh = window.innerHeight || 1;
      if (r.width <= 0 || r.height <= 0) return;
      const ratio = {
        left: Math.max(0, r.left) / vw,
        top: Math.max(0, r.top) / vh,
        right: Math.max(0, vw - r.right) / vw,
        bottom: Math.max(0, vh - r.bottom) / vh
      };
      const key = `${ratio.left.toFixed(4)}|${ratio.top.toFixed(4)}|${ratio.right.toFixed(4)}|${ratio.bottom.toFixed(4)}`;
      if (key === lastKey) return;
      lastKey = key;
      void kernel.setMarginRatio(ratio);
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    window.addEventListener('resize', apply);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', apply);
    };
  });

  function onTimeUpdate(): void {
    if (!videoEl) return;
    position = videoEl.currentTime;
    void saveProgress();
  }

  async function togglePlay(): Promise<void> {
    if (kernel.native) {
      if (playing) await kernel.pause();
      else await kernel.play();
      if (!playing) void saveProgress(true);
      return;
    }
    if (!videoEl) return;
    if (videoEl.paused) {
      void videoEl.play().catch(() => {});
    } else {
      videoEl.pause();
      void saveProgress(true);
    }
  }

  function seekTo(v: number): void {
    if (kernel.native) {
      void kernel.seek(v);
      position = v;
    } else {
      if (!videoEl) return;
      videoEl.currentTime = v;
    }
    void saveProgress(true);
  }

  function setVolume(v: number): void {
    volume = Math.max(0, Math.min(1, v));
    muted = volume === 0;
  }

  // 关闭小窗（进度已落盘）；主窗口保持打开，用户回到主窗口继续
  async function closeMini(): Promise<void> {
    await saveProgress(true);
    const { getCurrentWindow } = await import('@tauri-apps/api/window');
    await getCurrentWindow().close();
  }

  function fmt(t: number): string {
    if (!Number.isFinite(t)) return '0:00';
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
  }
</script>

<svelte:head><title>迷你播放 — vitoice</title></svelte:head>

<div class="mini-root">
  {#if loadError}
    <div class="mini-error">{loadError}</div>
  {:else}
    <!-- 拖拽标题条：decorations:false 的窗口唯一可拖动区域，含标题 + 关闭 -->
    <div class="mini-titlebar" data-tauri-drag-region>
      <span class="tb-title" data-tauri-drag-region>{title || '迷你播放'}</span>
      <button class="mini-btn" onclick={closeMini} aria-label="关闭小窗" title="关闭小窗">
        <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M5 5l14 14M19 5L5 19" fill="none" />
        </svg>
      </button>
    </div>
    <!-- 视频舞台：桌面端画面由 mpv 子窗口渲染，此容器只用于量出画面区矩形。 -->
    <div class="mini-stage" bind:this={stageEl}>
      {#if !kernel.native}
        <!-- svelte-ignore a11y_no_static_element_interactions, a11y_media_has_caption -->
        <video
          bind:this={videoEl}
          class="mini-video"
          src={streamUrl}
          playsinline
          onloadedmetadata={() => {
            if (videoEl) {
              duration = videoEl.duration;
              void videoEl.play().catch(() => {});
            }
          }}
          ontimeupdate={onTimeUpdate}
          onplay={() => (playing = true)}
          onpause={() => (playing = false)}
          onclick={togglePlay}
          onvolumechange={() => {
            if (videoEl) {
              volume = videoEl.volume;
              muted = videoEl.muted;
            }
          }}
        ></video>
      {/if}
    </div>
    <div class="mini-bar">
      <button class="mini-btn" onclick={togglePlay} aria-label={playing ? '暂停' : '播放'} title={playing ? '暂停' : '播放'}>
        {#if playing}
          <svg viewBox="0 0 24 24" width="15" height="15"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" fill="currentColor"/></svg>
        {:else}
          <svg viewBox="0 0 24 24" width="15" height="15"><path d="M8 5v14l11-7L8 5z" fill="currentColor"/></svg>
        {/if}
      </button>
      <span class="time">{fmt(position)}</span>
      <input
        class="seek"
        type="range"
        min="0"
        max={duration || 100}
        step="0.1"
        value={position}
        oninput={(e) => seekTo(Number((e.currentTarget as HTMLInputElement).value))}
        aria-label="播放进度"
      />
      <span class="time">{fmt(duration)}</span>
      <input
        class="vol"
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={muted ? 0 : volume}
        oninput={(e) => {
          const v = Number((e.currentTarget as HTMLInputElement).value);
          setVolume(v);
          if (!kernel.native && videoEl) {
            videoEl.volume = volume;
            videoEl.muted = muted;
          }
        }}
        aria-label="音量"
      />
    </div>
  {/if}
</div>

<style>
  .mini-root {
    width: 100vw;
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: #000;
    overflow: hidden;
    user-select: none;
  }
  .mini-titlebar {
    display: flex;
    align-items: center;
    gap: 4px;
    height: 30px;
    flex-shrink: 0;
    padding-left: 10px;
    background: rgba(16, 18, 20, 0.98);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }
  .tb-title {
    flex: 1;
    min-width: 0;
    color: rgba(255, 255, 255, 0.75);
    font-size: 11.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* 视频舞台：mpv 画面按此矩形的比例内缩；浏览器回退时 <video> 撑满。 */
  .mini-stage {
    flex: 1;
    min-height: 0;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .mini-video {
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #000;
    cursor: pointer;
  }
  .mini-error {
    flex: 1;
    display: grid;
    place-items: center;
    color: #fff;
    font-size: 13px;
    opacity: 0.8;
  }
  .mini-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 10px;
    background: rgba(16, 18, 20, 0.95);
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }
  .mini-btn {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: #e8e8e8;
    cursor: pointer;
    flex-shrink: 0;
  }
  .mini-btn:hover { background: rgba(255, 255, 255, 0.1); }
  .time {
    color: rgba(255, 255, 255, 0.65);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }
  .seek { flex: 1; min-width: 0; accent-color: #3ddc97; }
  .vol { width: 64px; flex-shrink: 0; accent-color: #3ddc97; }
</style>