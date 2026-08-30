<script lang="ts">
  // 作品详情：导演 / 编剧 / 类型 / 国家 / 语言 / 制作公司 / 系列 / 标语
  import type { ScrapeData } from '$lib/api/media';

  let {
    sd,
    hasScrapeData
  }: {
    sd: ScrapeData | undefined;
    hasScrapeData: boolean;
  } = $props();

  const directorList = $derived(sd?.directors ?? []);
  const writerList = $derived(sd?.writers ?? []);
  const countryText = $derived((sd?.production_countries ?? []).join(' / '));
  const companyText = $derived((sd?.production_companies ?? []).slice(0, 3).join(' / '));
  const languageText = $derived((sd?.spoken_languages ?? []).join(' / '));
  const genreText = $derived((sd?.genres ?? []).join(' / '));
  const collectionText = $derived(sd?.belongs_to_collection ?? null);
</script>

<section class="work-section">
  <div class="section-head">
    <h2 class="section-title">
      <span class="bar"></span>
      作品详情
    </h2>
    {#if hasScrapeData}
      <span class="source-badge">来源刮削数据</span>
    {/if}
  </div>
  {#if hasScrapeData}
    <div class="work-panel">
      {#if sd?.tagline}
        <div class="work-tagline">"{sd.tagline}"</div>
      {/if}
      <div class="work-grid">
        <div class="work-col">
          {#if directorList.length > 0}
            <div class="kv"><span>导演</span><b>{directorList.join('、')}</b></div>
          {/if}
          {#if writerList.length > 0}
            <div class="kv"><span>编剧</span><b>{writerList.join('、')}</b></div>
          {/if}
          {#if genreText}
            <div class="kv"><span>类型</span><b>{genreText}</b></div>
          {/if}
          {#if countryText}
            <div class="kv"><span>国家/地区</span><b>{countryText}</b></div>
          {/if}
        </div>
        <div class="work-col">
          {#if languageText}
            <div class="kv"><span>语言</span><b>{languageText}</b></div>
          {/if}
          {#if companyText}
            <div class="kv"><span>制作公司</span><b>{companyText}</b></div>
          {/if}
          {#if collectionText}
            <div class="kv"><span>系列</span><b>{collectionText}</b></div>
          {/if}
          {#if sd?.status}
            <div class="kv"><span>状态</span><b>{sd.status}</b></div>
          {/if}
        </div>
      </div>
      {#if sd?.imdb_id || sd?.homepage}
        <div class="work-links">
          {#if sd?.imdb_id}
            <a href="https://www.imdb.com/title/{sd.imdb_id}" target="_blank" rel="noopener noreferrer">IMDB {sd.imdb_id}</a>
          {/if}
          {#if sd?.homepage}
            <a href={sd.homepage} target="_blank" rel="noopener noreferrer">主页 访问 →</a>
          {/if}
        </div>
      {/if}
    </div>
  {:else}
    <div class="work-empty">
      暂无刮削数据 · 点击右上角「刮削」获取导演、演职人员、类型等信息
    </div>
  {/if}
</section>

<style>
  .work-section {
    padding: 24px 28px 26px;
    border-bottom: 1px solid var(--rule);
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

  .bar {
    width: 4px;
    height: 16px;
    border-radius: 2px;
    background: var(--accent);
    display: inline-block;
  }

  .source-badge {
    font-size: 11px;
    color: var(--accent);
    background: var(--accent-soft);
    border-radius: 10px;
    padding: 2px 8px;
    font-weight: 500;
  }

  .work-panel {
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    padding: 18px 20px;
  }

  .work-tagline {
    font-size: 13px;
    color: var(--muted);
    font-style: italic;
    margin-bottom: 14px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--rule);
  }

  .work-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0 32px;
  }

  .work-col {
    display: flex;
    flex-direction: column;
    gap: 9px;
    min-width: 0;
  }

  .kv {
    display: flex;
    align-items: baseline;
    gap: 10px;
    min-width: 0;
  }

  .kv span {
    flex-shrink: 0;
    width: 76px;
    font-size: 12px;
    color: var(--muted);
  }

  .kv b {
    font-size: 13px;
    color: var(--ink);
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .work-links {
    display: flex;
    gap: 16px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--rule);
  }

  .work-links a {
    color: var(--accent2);
    font-size: 12px;
    text-decoration: none;
  }

  .work-links a:hover {
    text-decoration: underline;
  }

  .work-empty {
    background: var(--bg2);
    border: 1px dashed var(--rule);
    border-radius: var(--radius-card);
    padding: 22px 20px;
    font-size: 12.5px;
    color: var(--muted);
    text-align: center;
  }
</style>
