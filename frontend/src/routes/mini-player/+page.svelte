<script lang="ts">
  /**
   * 迷你置顶小窗（由主播放器「小窗」按钮创建的 Tauri WebviewWindow，label=mini）。
   * 极简播放：自动续播 + 播放/暂停 + 进度条 + 音量 + 回到主窗。
   * 进度仍写后端 /media/{id}/progress，主播放器下次打开自动续上。
   */
  import { onMount } from 'svelte';
  import { client } from '$lib/api/client';
  import { mediaApi } from '$lib/api/media';
  import { realQueryParam } from '$lib/utils/urlState';

  // 读 window.location 而非 $page.url：popstate 重挂载时 page store 会丢 query。
  const mediaId = realQueryParam('id') ?? '';

  let videoEl: HTMLVideoElement | null = $state(null);
  let title = $state('');
  let loadError = $state<string | null>(null);
  let playing = $state(false);
  let duration = $state(0);
  let position = $state(0);
  let volume = $state(1);
  let muted = $state(false);

  let resumed = false;
  let lastSaved = 0;

  const streamUrl = $derived(mediaId ? mediaApi.streamUrl(mediaId) : '');

  async function saveProgress(force = false): Promise<void> {
    if (!mediaId || !videoEl || !videoEl.duration) return;
    const now = Date.now();
    if (!force && now - lastSaved < 8000) return;
    lastSaved = now;
    void client
      .post(`/media/${mediaId}/progress`, { position: videoEl.currentTime, speed: 1 })
      .catch(() => {});
  }

  onMount(() => {
    if (!mediaId) {
      loadError = '缺少媒体 ID';
      return;
    }
    const init = async (): Promise<void> => {
      try {
        const raw = await client.get<any>(`/media/${mediaId}`);
        title = raw?.title ?? raw?.file_name ?? '';
      } catch {
        loadError = '加载媒体失败';
      }
    };
    void init();
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

  function onLoadedMetadata(): void {
    if (!videoEl) return;
    duration = videoEl.duration;
    // 续播：主播放器暂停时已把进度写后端，这里读回并跳转（仅一次）
    void client
      .get<any>(`/media/${mediaId}`)
      .then((raw) => {
        const pos = raw?.playback_position ?? 0;
        if (!resumed && pos > 1 && pos < (videoEl?.duration ?? Infinity) - 5) {
          if (videoEl) videoEl.currentTime = pos;
        }
        resumed = true;
      })
      .catch(() => {
        resumed = true;
      });
    void videoEl.play().catch(() => {});
  }

  function onTimeUpdate(): void {
    if (!videoEl) return;
    position = videoEl.currentTime;
    void saveProgress();
  }

  function togglePlay(): void {
    if (!videoEl) return;
    if (videoEl.paused) {
      void videoEl.play().catch(() => {});
    } else {
      videoEl.pause();
      void saveProgress(true);
    }
  }

  function seekTo(v: number): void {
    if (!videoEl) return;
    videoEl.currentTime = v;
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
    <!-- svelte-ignore a11y_no_static_element_interactions, a11y_media_has_caption -->
    <video
      bind:this={videoEl}
      class="mini-video"
      src={streamUrl}
      playsinline
      onloadedmetadata={onLoadedMetadata}
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
          if (videoEl) {
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
  .mini-video {
    flex: 1;
    min-height: 0;
    width: 100%;
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
