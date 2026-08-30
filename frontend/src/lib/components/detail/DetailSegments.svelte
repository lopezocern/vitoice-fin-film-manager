<script lang="ts">
  // 详情页片段标记区：时间轴可视化 + 片段列表
  import { formatTime } from '$lib/utils/format';
  import type { Segment } from './types';

  let {
    segments,
    mediaDuration,
    onjump
  }: {
    segments: Segment[];
    mediaDuration?: number;
    onjump?: (seg: Segment) => void;
  } = $props();

  // 进度条锚点位置百分比
  function segmentPos(seg: Segment): number {
    if (!mediaDuration) return 0;
    return Math.max(0, Math.min(100, (seg.start / mediaDuration) * 100));
  }
</script>

<section class="section">
  <div class="section-head">
    <h2 class="section-title">片段标记</h2>
    {#if segments.length > 0}
      <span class="section-count">{segments.length}</span>
    {/if}
  </div>
  {#if mediaDuration && segments.length > 0}
    <div class="timeline-vis" title="点击片段跳转">
      <div class="timeline-bar">
        {#each segments as seg (seg.id)}
          {@const pos = segmentPos(seg)}
          <button
            class="timeline-anchor"
            style="left:{pos}%"
            title={`${seg.label ?? '片段'} · ${formatTime(seg.start)}`}
            onclick={() => onjump?.(seg)}
          ></button>
        {/each}
      </div>
    </div>
  {/if}
  {#if segments.length > 0}
    <div class="segment-list">
      {#each segments as seg (seg.id)}
        <div class="segment-item">
          <div class="seg-info">
            <span class="seg-name">{seg.label ?? '未命名片段'}</span>
            <span class="seg-range">
              {formatTime(seg.start)}{#if seg.end} – {formatTime(seg.end)}{/if}
            </span>
          </div>
          <button class="seg-jump" onclick={() => onjump?.(seg)} title="跳转到此处">
            <svg viewBox="0 0 24 24" width="14" height="14"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
            跳转
          </button>
        </div>
      {/each}
    </div>
  {:else}
    <div class="section-empty">暂无片段标记</div>
  {/if}
</section>

<style>
  /* ---- 共享 section 样式 ---- */
  .section {
    max-width: 1280px;
    margin: 0 auto 28px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--rule);
  }

  .section:last-child {
    border-bottom: none;
    margin-bottom: 0;
  }

  .section-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }

  .section-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 9px;
  }

  .section-title::before {
    content: '';
    width: 4px;
    height: 16px;
    border-radius: 2px;
    background: var(--accent);
    display: inline-block;
  }

  .section-count {
    font-size: 11px;
    color: var(--muted);
    background: var(--bg-soft);
    padding: 1px 8px;
    border-radius: var(--radius-full);
  }

  .section-empty {
    padding: 16px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    background: var(--bg-soft);
    border-radius: var(--radius);
  }

  /* ---- 片段标记 ---- */
  .timeline-vis {
    margin-bottom: 12px;
  }

  .timeline-bar {
    position: relative;
    height: 8px;
    background: var(--bg-soft);
    border-radius: var(--radius-full);
    overflow: visible;
  }

  .timeline-anchor {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    width: 12px;
    height: 12px;
    border: 2px solid var(--bg2);
    border-radius: var(--radius-full);
    background: var(--accent);
    cursor: pointer;
    transition: transform 200ms;
    padding: 0;
  }

  .timeline-anchor:hover {
    transform: translate(-50%, -50%) scale(1.4);
    z-index: 2;
  }

  .segment-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .segment-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    transition: background 200ms;
  }

  .segment-item:hover {
    background: var(--accent-soft);
  }

  .seg-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .seg-name {
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
  }

  .seg-range {
    font-size: 11.5px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }

  .seg-jump {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--accent);
    font-size: 12px;
    transition: all 200ms ease;
  }

  .seg-jump:hover {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }
</style>
