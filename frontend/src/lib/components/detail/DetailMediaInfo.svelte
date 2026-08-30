<script lang="ts">
  // 详情页媒体信息区：视频 / 音频 / 字幕 / 文件 四卡
  import type { Subtitle } from './types';

  let {
    resolutionText = '',
    codec = '',
    fpsText = '',
    bitrateText = '',
    subtitles = [],
    containerText = '',
    durationText = '',
    sizeText = ''
  }: {
    resolutionText?: string;
    codec?: string;
    fpsText?: string;
    bitrateText?: string;
    subtitles?: Subtitle[];
    containerText?: string;
    durationText?: string;
    sizeText?: string;
  } = $props();

  function subtitleTypeLabel(t: Subtitle['type']): string {
    if (t === 'external') return '外部';
    if (t === 'embedded') return '内嵌';
    if (t === 'network') return '网络';
    return t;
  }
</script>

<section class="media-section">
  <div class="section-head">
    <h2 class="section-title">媒体信息</h2>
  </div>
  <div class="info-cards">
    <div class="info-card">
      <div class="card-head">▣ 视频</div>
      {#if resolutionText}
        <div class="kv"><span>分辨率</span><b>{resolutionText}</b></div>
      {/if}
      {#if codec}
        <div class="kv"><span>编码</span><b>{codec}</b></div>
      {/if}
      {#if fpsText}
        <div class="kv"><span>帧率</span><b>{fpsText}</b></div>
      {/if}
      {#if bitrateText}
        <div class="kv"><span>码率</span><b>{bitrateText}</b></div>
      {/if}
      {#if !resolutionText && !codec}
        <div class="kv empty">暂无视频信息</div>
      {/if}
    </div>

    <div class="info-card">
      <div class="card-head">◖ 音频</div>
      {#if subtitles.some((s) => s.type === 'embedded')}
        <div class="kv"><span>内嵌音轨</span><b>随文件</b></div>
      {:else}
        <div class="kv empty">暂无音轨信息</div>
      {/if}
    </div>

    <div class="info-card">
      <div class="card-head">▤ 字幕</div>
      {#if subtitles.length > 0}
        {#each subtitles.slice(0, 4) as sub (sub.id)}
          <div class="kv"><span>{sub.language || '未知'}</span><b>{subtitleTypeLabel(sub.type)}{sub.default ? ' · 默认' : ''}</b></div>
        {/each}
      {:else}
        <div class="kv empty">暂无字幕</div>
      {/if}
    </div>

    <div class="info-card">
      <div class="card-head">▱ 文件</div>
      {#if containerText}
        <div class="kv"><span>封装</span><b>{containerText}</b></div>
      {/if}
      {#if durationText}
        <div class="kv"><span>时长</span><b>{durationText}</b></div>
      {/if}
      {#if sizeText}
        <div class="kv"><span>大小</span><b>{sizeText}</b></div>
      {/if}
    </div>
  </div>
</section>

<style>
  .media-section {
    padding: 20px 28px;
    max-width: 1280px;
    margin: 0 auto;
  }

  .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 9px;
    margin: 0;
  }

  .section-title::before {
    content: '';
    width: 4px;
    height: 16px;
    border-radius: 2px;
    background: var(--accent);
    display: inline-block;
  }

  .info-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }

  .info-card {
    background: var(--panel, var(--bg2));
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    padding: 14px 16px;
  }

  .card-head {
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 12px;
  }

  .kv {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    font-size: 12px;
    border-bottom: 1px solid var(--rule-light);
  }

  .kv:last-child { border-bottom: 0; }

  .kv span { color: var(--muted); }

  .kv b {
    color: var(--ink2);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .kv.empty {
    justify-content: center;
    color: var(--faint, var(--muted2));
  }

  @media (max-width: 1250px) {
    .info-cards { grid-template-columns: repeat(2, 1fr); }
  }

  @media (max-width: 900px) {
    .media-section { padding: 6px 16px; }
    .info-cards { grid-template-columns: 1fr; }
  }
</style>
