<script lang="ts">
  // 整理带组件：浮在视频上方的底部工具栏，快捷键唤起。
  // 主要为展示层，重逻辑由父级（player 页面）通过回调处理。
  let {
    rating = 0,
    favorite = false,
    hasSubtitle = false,
    captionsOn = false,
    markStart = null,
    onMarkIn,
    onMarkOut,
    onQuickTag,
    onAiTag,
    onRate,
    onToggleFavorite,
    onScreenshot,
    onToggleCaptions
  }: {
    rating?: number;
    favorite?: boolean;
    hasSubtitle?: boolean;
    captionsOn?: boolean;
    markStart?: number | null;
    onMarkIn?: () => void;
    onMarkOut?: () => void;
    onQuickTag?: () => void;
    onAiTag?: () => void;
    onRate?: (n: number) => void;
    onToggleFavorite?: () => void;
    onScreenshot?: (toFile: boolean) => void;
    onToggleCaptions?: () => void;
  } = $props();

  let ratingOpen = $state(false);
  let ratingTimer: ReturnType<typeof setTimeout> | null = null;

  function enterRating(): void {
    if (ratingTimer) {
      clearTimeout(ratingTimer);
      ratingTimer = null;
    }
    ratingOpen = true;
  }
  function leaveRating(): void {
    ratingTimer = setTimeout(() => (ratingOpen = false), 220);
  }
  function pickRate(n: number): void {
    onRate?.(n);
    ratingOpen = false;
  }
</script>

<div class="organize-strip" role="toolbar" aria-label="整理工具">
  <!-- 标记片段 -->
  <button class="obtn" class:active={markStart !== null} title="标记片段起点 (I)" onclick={onMarkIn} type="button">
    <span class="ico">⏱</span>
    <span class="lbl">{markStart !== null ? '已标记起点' : '片段起点'}</span>
    <span class="key">I</span>
  </button>
  <button class="obtn" title="标记片段终点 (O)" onclick={onMarkOut} disabled={markStart === null} type="button">
    <span class="ico">⏹</span>
    <span class="lbl">片段终点</span>
    <span class="key">O</span>
  </button>

  <div class="divider"></div>

  <!-- 打标 -->
  <button class="obtn" title="快速打标 (T)" onclick={onQuickTag} type="button">
    <span class="ico">🏷</span>
    <span class="lbl">快速打标</span>
    <span class="key">T</span>
  </button>
  <button class="obtn" title="AI 自动打标 (A)" onclick={onAiTag} type="button">
    <span class="ico">🤖</span>
    <span class="lbl">AI 打标</span>
    <span class="key">A</span>
  </button>

  <div class="divider"></div>

  <!-- 评分（hover 弹 5 星） -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="rating-wrap" role="presentation" onpointerenter={enterRating} onpointerleave={leaveRating}>
    <button class="obtn" title="评分 (1-5)" type="button">
      <span class="ico stars">{#each [0, 1, 2, 3, 4] as _, i}{#if i < rating}<span class="s on">★</span>{:else}<span class="s">☆</span>{/if}{/each}</span>
      <span class="lbl">评分</span>
      <span class="key">1-5</span>
    </button>
    {#if ratingOpen}
      <div class="star-pop">
        {#each [1, 2, 3, 4, 5] as n}
          <button
            class="star-btn"
            class:filled={n <= rating}
            onclick={() => pickRate(n)}
            title={`${n} 星`}
            type="button"
          >★</button>
        {/each}
      </div>
    {/if}
  </div>

  <!-- 收藏 -->
  <button class="obtn" class:on={favorite} title="收藏切换 (R)" onclick={onToggleFavorite} type="button">
    <span class="ico">{favorite ? '♥' : '♡'}</span>
    <span class="lbl">收藏</span>
    <span class="key">R</span>
  </button>

  <div class="divider"></div>

  <!-- 截图 -->
  <button class="obtn" title="截图到剪贴板 (S) / Shift+S 存文件" onclick={() => onScreenshot?.(false)} type="button">
    <span class="ico">📸</span>
    <span class="lbl">截图</span>
    <span class="key">S</span>
  </button>

  <!-- 字幕 -->
  <button class="obtn" class:on={captionsOn} title="字幕切换 (C)" onclick={onToggleCaptions} disabled={!hasSubtitle} type="button">
    <span class="ico">💬</span>
    <span class="lbl">字幕</span>
    <span class="key">C</span>
  </button>
</div>

<style>
  .organize-strip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 10px;
    background: rgba(20, 20, 22, 0.78);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: var(--radius-card);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }

  .divider {
    width: 1px;
    height: 22px;
    background: rgba(255, 255, 255, 0.12);
    margin: 0 4px;
    flex-shrink: 0;
  }

  .obtn {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    height: 34px;
    padding: 0 10px;
    border: none;
    background: transparent;
    color: rgba(255, 255, 255, 0.88);
    border-radius: var(--radius);
    font-size: 12.5px;
    transition: background 150ms, color 150ms, transform 120ms;
    cursor: pointer;
    white-space: nowrap;
  }
  .obtn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
    color: var(--accent);
  }
  .obtn:active:not(:disabled) {
    transform: scale(0.96);
  }
  .obtn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .obtn.on {
    color: var(--accent2);
  }
  .obtn.active {
    color: var(--accent2);
    background: var(--accent2-soft);
  }

  .ico {
    font-size: 15px;
    line-height: 1;
    display: inline-flex;
    align-items: center;
  }
  .ico.stars {
    gap: 0;
    letter-spacing: 0;
  }
  .ico.stars .s {
    font-size: 13px;
    color: rgba(255, 255, 255, 0.3);
  }
  .ico.stars .s.on {
    color: var(--accent2);
  }

  .lbl {
    font-weight: 500;
  }

  .key {
    font-size: 10px;
    color: rgba(255, 255, 255, 0.45);
    background: rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    padding: 1px 5px;
    letter-spacing: 0.02em;
  }

  .rating-wrap {
    position: relative;
  }
  .star-pop {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 2px;
    background: rgba(20, 20, 22, 0.92);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: var(--radius);
    padding: 6px 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    animation: pop 140ms ease;
  }
  @keyframes pop {
    from { opacity: 0; transform: translateX(-50%) translateY(4px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
  .star-btn {
    width: 30px;
    height: 30px;
    border: none;
    background: none;
    color: rgba(255, 255, 255, 0.35);
    font-size: 18px;
    cursor: pointer;
    transition: color 120ms, transform 120ms;
    line-height: 1;
  }
  .star-btn:hover {
    color: var(--accent2);
    transform: scale(1.18);
  }
  .star-btn.filled {
    color: var(--accent2);
  }
</style>
