<script lang="ts">
  // 详情页附加信息区：字幕 / 片段 / 外部链接 计数卡片
  let {
    subtitleCount = 0,
    segmentCount = 0,
    linkCount = 0
  }: {
    subtitleCount?: number;
    segmentCount?: number;
    linkCount?: number;
  } = $props();
</script>

<section class="info-section">
  <div class="section-head">
    <h2 class="section-title">附加信息</h2>
  </div>
  <div class="info-cards">
    <div class="info-card">
      <div class="info-icon">▣</div>
      <div class="info-body">
        <div class="info-num">{subtitleCount}</div>
        <div class="info-label">条字幕</div>
      </div>
    </div>
    <div class="info-card">
      <div class="info-icon">▧</div>
      <div class="info-body">
        <div class="info-num">{segmentCount}</div>
        <div class="info-label">个片段标记</div>
      </div>
    </div>
    <div class="info-card">
      <div class="info-icon">↗</div>
      <div class="info-body">
        <div class="info-num">{linkCount}</div>
        <div class="info-label">条外部链接</div>
      </div>
    </div>
  </div>
</section>

<style>
  .info-section {
    padding: 24px 0 8px;
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
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }

  .info-card {
    display: flex;
    align-items: center;
    gap: 12px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    padding: 14px 16px;
  }

  .info-icon {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    background: var(--accent2-soft);
    color: var(--accent2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
  }

  .info-body {
    display: flex;
    align-items: baseline;
    gap: 6px;
  }

  .info-num {
    font-size: 22px;
    font-weight: 600;
    color: var(--ink);
  }

  .info-label {
    font-size: 12px;
    color: var(--muted);
  }

  @media (max-width: 900px) {
    .info-section { padding: 18px 0 6px; }
    .info-cards { grid-template-columns: 1fr; }
  }
</style>
