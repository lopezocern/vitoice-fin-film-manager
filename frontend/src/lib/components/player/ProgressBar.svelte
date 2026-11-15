<script lang="ts">
  // 进度条组件：可拖拽 seek、缓冲区域、片段锚点、Hover 时间提示。
  // Svelte 5 runes 写法；通过 onSeek 回调上抛跳转（等价于 dispatch('seek', time)）。
  //
  // 拖拽策略：拖拽过程中只更新进度条视觉位置（dragTime），不触发 onSeek。
  //   原因：对转码流（MKV），每次 seek 到未缓冲区域都会触发 streamStart 变更
  //   → 视频 src 变更 → 整体重载 → 画面回到第一帧（poster）。
  //   松手时才执行一次 seek，避免反复重载。
  //   同时，不触发 seek 也就不会引发组件重渲染，hover tooltip 始终保持可见。
  import { formatTime } from '$lib/utils/format';
  import { BASE_URL } from '$lib/api/client';

  interface SegmentAnchor {
    start: number;
    end?: number | null;
    color?: string | null;
    label?: string;
  }

  let {
    current = 0,
    duration = 0,
    buffered = 0,
    segments = [],
    onSeek,
    mediaId,
    thumbnailUrl = ''
  }: {
    current?: number;
    duration?: number;
    buffered?: number;
    segments?: SegmentAnchor[];
    onSeek?: (time: number) => void;
    mediaId?: string;
    thumbnailUrl?: string;
  } = $props();

  let trackEl = $state<HTMLDivElement | null>(null);
  let dragging = $state(false);
  let hoverX = $state<number | null>(null);
  // 拖拽中的视觉位置（不触发实际 seek，仅更新进度条外观）
  let dragTime = $state<number | null>(null);

  // 实际显示的当前位置：拖拽中跟随鼠标，非拖拽时使用传入的 current
  const visualCurrent = $derived(dragTime ?? current);
  const progressPct = $derived(
    Number.isFinite(duration) && duration > 0 ? Math.min(100, Math.max(0, (visualCurrent / duration) * 100)) : 0
  );
  const bufferedPct = $derived(
    Number.isFinite(duration) && duration > 0 ? Math.min(100, Math.max(0, (buffered / duration) * 100)) : 0
  );

  const hoverTime = $derived.by(() => {
    // duration 可能为 NaN（视频元数据未加载）——NaN <= 0 为 false 会漏过守卫，
    // 导致 Math.round(NaN) = NaN 传给后端 t=NaN 422
    if (hoverX === null || !trackEl || !Number.isFinite(duration) || duration <= 0) return null;
    const w = trackEl.clientWidth || 1;
    return Math.max(0, Math.min(duration, (hoverX / w) * duration));
  });

  // —— Hover 缩略图预览 ——
  // 使用后端截图端点 /api/media/{id}/screenshot?t={time} 获取指定时间戳的帧。
  // 若截图失败（如媒体无文件路径）则回退到静态缩略图。
  // 时间取整到秒以减少请求数并利用浏览器缓存。
  //
  // 防抖+预加载策略：鼠标快速滑动时 screenshotUrl 频繁变化，直接绑定到 <img src>
  // 会导致浏览器不断取消旧请求（ERR_ABORTED）。改为：
  //   1. URL 变化后延迟 120ms 才开始预加载（防抖）
  //   2. 用 Image() 预加载，完成后才更新 imgSrc（避免 <img> 产生 abort）
  const previewRoundedTime = $derived(
    hoverTime !== null ? Math.round(hoverTime) : null
  );
  const screenshotUrl = $derived(
    mediaId && previewRoundedTime !== null
      ? `${BASE_URL}/media/${mediaId}/screenshot?t=${previewRoundedTime}`
      : ''
  );
  // 截图端点最近一次失败的时间戳（0 = 未失败）。
  // 用「冷却窗口」而非永久标记：抽帧繁忙时的一次瞬时失败不该让整支视频的
  // hover 预览从此消失（缩略图缺失时甚至完全空白），冷却结束会自动重试。
  let screenshotFailedAt = $state(0);
  const SCREENSHOT_RETRY_MS = 4000;
  // 缩略图是否也失败（标记后不再显示图片）
  let thumbnailFailed = $state(false);
  // 实际加载的图片 URL（只有预加载完成后才会更新）
  let imgSrc = $state('');
  // 当前 imgSrc 是否来自截图端点（渲染失败时决定冷却重试还是彻底放弃）
  let imgIsScreenshot = $state(false);

  // 切换媒体时重置失败标记，让新媒体重新尝试截图端点
  $effect(() => {
    mediaId;
    screenshotFailedAt = 0;
    thumbnailFailed = false;
    imgIsScreenshot = false;
  });

  // 防抖+预加载：URL 变化时不会立即更新 imgSrc
  $effect(() => {
    const url = screenshotUrl;

    // 离开进度条或无 URL：清空图片
    if (!url) {
      imgSrc = '';
      return;
    }
    if (thumbnailFailed) {
      imgSrc = '';
      return;
    }

    // 截图端点刚失败过 → 冷却期内退回缩略图，冷却结束后恢复尝试截图
    const usingScreenshot = Date.now() - screenshotFailedAt >= SCREENSHOT_RETRY_MS;
    const targetUrl = usingScreenshot ? url : thumbnailUrl;
    if (!targetUrl) {
      imgSrc = '';
      return;
    }

    // 如果 URL 没变（例如 hoverTime 取整后相同），不做任何事
    if (imgSrc === targetUrl) return;

    // 防抖：60ms 后才开始预加载（原本 120ms；已缓存帧几乎瞬时，缩短可让
    // 缩略图更早出现，又不至于在快速划过时频繁触发新抽帧请求）
    let cancelled = false;
    const timer = setTimeout(() => {
      if (cancelled) return;

      // 用 Image() 预加载，完成后才更新 <img src>
      const preloader = new Image();
      preloader.onload = () => {
        if (cancelled) return;
        imgSrc = targetUrl;
        imgIsScreenshot = usingScreenshot;
      };
      preloader.onerror = () => {
        if (cancelled) return;
        if (usingScreenshot) {
          // 截图瞬时失败（后端抽帧繁忙/超时）：进入冷却，稍后自动重试
          screenshotFailedAt = Date.now();
        } else {
          thumbnailFailed = true;
        }
      };
      preloader.src = targetUrl;
    }, 60);

    // 清理函数：取消未完成的防抖/预加载
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  });

  function onPreviewError(): void {
    // <img> 已预加载成功却仍渲染失败（例如缓存被清）：截图则进入冷却重试，
    // 缩略图则彻底放弃。
    if (imgIsScreenshot) {
      screenshotFailedAt = Date.now();
    } else {
      thumbnailFailed = true;
    }
  }

  // Tooltip 水平位置 + 预览图宽度：钳制在进度条范围内，防止边缘溢出。
  // 预览图默认 320px；进度条比预览图还窄时（小窗口/窄容器）收缩到可用宽度，
  // 否则靠边时会被容器裁掉、看起来像"被压扁"。
  // 注意 clientWidth 不是响应式值——依赖 hoverX 让每次指针移动都重算。
  const tooltipLayout = $derived.by(() => {
    if (hoverX === null) return { left: 0, width: 320 };
    if (!trackEl) return { left: hoverX, width: 320 };
    const w = trackEl.clientWidth || 1;
    if (!mediaId) {
      // 无预览图：只有时间文字，窄条即可
      const margin = Math.min(30, Math.max(4, w / 2 - 4));
      return { left: Math.max(margin, Math.min(w - margin, hoverX)), width: 0 };
    }
    const width = Math.max(120, Math.min(320, w - 8));
    // 半宽 + 余量，保证预览图完整落在进度条范围内
    const half = width / 2 + 4;
    const margin = Math.min(half, Math.max(4, w / 2 - 4));
    return { left: Math.max(margin, Math.min(w - margin, hoverX)), width };
  });

  // F4 fix: NaN duration (metadata not loaded yet) must be treated as
  // "no duration" — `duration <= 0` alone does not catch NaN.
  const hasDuration = $derived(Number.isFinite(duration) && duration > 0);

  function clientXToTime(clientX: number): number {
    if (!trackEl || !hasDuration) return 0;
    const rect = trackEl.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return ratio * duration;
  }

  function onPointerDown(e: PointerEvent): void {
    if (!hasDuration) return;
    e.preventDefault();
    dragging = true;
    trackEl?.setPointerCapture?.(e.pointerId);
    // 只更新视觉位置，不实际 seek
    dragTime = clientXToTime(e.clientX);
  }
  function onPointerMove(e: PointerEvent): void {
    if (!trackEl) return;
    const rect = trackEl.getBoundingClientRect();
    hoverX = e.clientX - rect.left;
    if (dragging) {
      // 拖拽中只更新视觉位置，不调用 onSeek
      // 避免 MKV 转码流在拖拽过程中反复重载导致画面回到第一帧
      dragTime = clientXToTime(e.clientX);
    }
  }
  function onPointerUp(e: PointerEvent): void {
    if (!dragging) return;
    trackEl?.releasePointerCapture?.(e.pointerId);
    dragging = false;
    // 松手时执行一次实际 seek
    if (dragTime !== null) {
      onSeek?.(dragTime);
      dragTime = null;
    }
  }
  function onPointerLeave(): void {
    if (!dragging) hoverX = null;
  }

  function onKeydown(e: KeyboardEvent): void {
    if (!hasDuration) return;
    if (e.key === 'Escape' && dragging) {
      e.preventDefault();
      dragging = false;
      dragTime = null;
      return;
    }
    if (e.key === 'ArrowLeft') { e.preventDefault(); onSeek?.(Math.max(0, visualCurrent - 5)); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); onSeek?.(Math.min(duration, visualCurrent + 5)); }
  }

  function segLeftPct(seg: SegmentAnchor): number {
    return hasDuration ? Math.min(100, Math.max(0, (seg.start / duration) * 100)) : 0;
  }
  function segWidthPct(seg: SegmentAnchor): number {
    if (!hasDuration || seg.end == null) return 0;
    return Math.min(100, Math.max(0, ((seg.end - seg.start) / duration) * 100));
  }
</script>

<div
  class="progress-bar"
  class:dragging
  class:idle={duration <= 0}
  bind:this={trackEl}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={onPointerUp}
  onpointerleave={onPointerLeave}
  onkeydown={onKeydown}
  role="slider"
  tabindex="0"
  aria-label="播放进度"
  aria-valuemin={0}
  aria-valuemax={Math.round(duration)}
  aria-valuenow={Math.round(current)}
>
  <!-- 缓冲区域 -->
  <div class="buffered" style={`width:${bufferedPct}%`}></div>

  <!-- 片段区间高亮 -->
  {#each segments as seg, i (i)}
    {#if seg.end != null && seg.end > seg.start}
      <div
        class="seg-region"
        style={`left:${segLeftPct(seg)}%; width:${segWidthPct(seg)}%;${seg.color ? `--seg:${seg.color};` : ''}`}
      ></div>
    {/if}
  {/each}

  <!-- 已播放进度 -->
  <div class="played" style={`width:${progressPct}%`}></div>

  <!-- 片段锚点（垂直线） -->
  {#each segments as seg, i (i)}
    <div
      class="seg-anchor"
      style={`left:${segLeftPct(seg)}%;${seg.color ? `--seg:${seg.color};` : ''}`}
      title={seg.label ?? (seg.end != null ? `片段 ${formatTime(seg.start)} - ${formatTime(seg.end)}` : `标记 ${formatTime(seg.start)}`)}
    ></div>
  {/each}

  <!-- 拖动手柄 -->
  <div class="knob" style={`left:${progressPct}%`}></div>

  <!-- Hover 时间提示 + 缩略图预览 -->
  {#if hoverTime !== null && hoverX !== null}
    <div class="tooltip" style={`left:${tooltipLayout.left}px; --preview-w:${tooltipLayout.width}px`}>
      {#if imgSrc}
        <img class="preview-img" src={imgSrc} onerror={onPreviewError} alt="" draggable="false" />
      {/if}
      <span class="tooltip-time">{formatTime(hoverTime)}</span>
    </div>
  {/if}
</div>

<style>
  .progress-bar {
    position: relative;
    height: 14px;
    display: flex;
    align-items: center;
    cursor: pointer;
    user-select: none;
    outline: none;
  }

  /* 进度条上方防误触带：鼠标想拖进度条但略偏上时，点到的仍是进度条
     （被进度条捕获，最多就近 seek），不会穿透到视频层触发暂停。 */
  .progress-bar::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: 100%;
    height: 10px;
  }

  .progress-bar.idle {
    cursor: default;
    opacity: 0.45;
  }
  .progress-bar::before {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    height: 4px;
    background: rgba(255, 255, 255, 0.25);
    border-radius: var(--radius-full);
    transition: height 150ms ease;
  }
  .progress-bar:hover::before,
  .progress-bar.dragging::before,
  .progress-bar:focus-visible::before {
    height: 6px;
  }

  .buffered,
  .played,
  .seg-region {
    position: absolute;
    left: 0;
    height: 4px;
    border-radius: var(--radius-full);
    transition: height 150ms ease;
  }
  .buffered { background: rgba(255, 255, 255, 0.35); }
  .played { background: var(--accent); }
  .seg-region {
    background: var(--seg, var(--accent2));
    opacity: 0.35;
  }
  .progress-bar:hover .buffered,
  .progress-bar:hover .played,
  .progress-bar:hover .seg-region,
  .progress-bar.dragging .buffered,
  .progress-bar.dragging .played,
  .progress-bar.dragging .seg-region {
    height: 6px;
  }

  .seg-anchor {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 2px;
    height: 12px;
    background: var(--seg, var(--accent2));
    border-radius: 1px;
    pointer-events: none;
    box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
  }

  .knob {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 16px;
    height: 16px;
    background: #fff;
    border-radius: var(--radius-full);
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.2), 0 2px 6px rgba(0, 0, 0, 0.45);
    opacity: 0;
    transition: opacity 150ms ease, transform 150ms ease;
    pointer-events: none;
  }
  .progress-bar:hover .knob,
  .progress-bar.dragging .knob,
  .progress-bar:focus-visible .knob {
    opacity: 1;
  }
  .progress-bar.dragging .knob {
    transform: translate(-50%, -50%) scale(1.18);
  }

  .tooltip {
    position: absolute;
    bottom: calc(100% + 8px);
    transform: translateX(-50%);
    /* 关键：绝对定位元素的宽度默认会被"包含块宽度 - left"截断，
       tooltip 越靠右可用宽度越小，320px 的预览图会被裁掉/压扁。
       width: max-content 让宽度只由内容决定，水平位置交给 tooltipLeft 钳制。 */
    width: max-content;
    background: rgba(0, 0, 0, 0.88);
    color: #fff;
    border-radius: var(--radius);
    pointer-events: none;
    white-space: nowrap;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .preview-img {
    display: block;
    /* 宽度由 --preview-w 决定（进度条过窄时收缩），保持 16:9 不被压扁 */
    width: var(--preview-w, 320px);
    aspect-ratio: 16 / 9;
    height: auto;
    /* 绝对定位 + flex 子项都可能触发收缩，显式禁止，保证不被压扁 */
    flex: none;
    max-width: none;
    object-fit: cover;
    background: rgba(255, 255, 255, 0.06);
    pointer-events: none;
  }
  .tooltip-time {
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    padding: 3px 7px;
    text-align: center;
  }
</style>
