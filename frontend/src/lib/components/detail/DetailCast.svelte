<script lang="ts">
  // 详情页演员阵容区：8 列头像大卡（真实头像 + 首字母占位降级）
  import type { ScrapeData } from '$lib/api/media';

  let { cast = [] }: { cast?: ScrapeData['cast'] } = $props();
</script>

{#if cast.length > 0}
<section class="cast-section">
  <div class="section-head">
    <h2 class="section-title">演员阵容</h2>
    <span class="count-hint">查看全部 {cast.length} 人 ›</span>
  </div>
  <div class="cast-row">
    {#each cast as c, i (i)}
      <div class="cast-card">
        <div class="cast-avatar-wrap">
          {#if c.profile_path}
            <img
              class="cast-avatar"
              src={`https://image.tmdb.org/t/p/w185${c.profile_path}`}
              alt={c.name}
              loading="lazy"
              onerror={(e) => {
                const el = e.currentTarget as HTMLImageElement;
                el.style.display = 'none';
                const fb = el.nextElementSibling as HTMLElement | null;
                fb?.classList.remove('hidden');
              }}
            />
            <div class="cast-avatar fallback hidden">{c.name.charAt(0)}</div>
          {:else}
            <div class="cast-avatar fallback">{c.name.charAt(0)}</div>
          {/if}
        </div>
        <div class="cast-name" title={c.name}>{c.name}</div>
        {#if c.character}<div class="cast-role" title={c.character}>{c.character}</div>{/if}
      </div>
    {/each}
  </div>
</section>
{/if}

<style>
  .cast-section {
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

  .section-title::before {
    content: '';
    width: 4px;
    height: 16px;
    border-radius: 2px;
    background: var(--accent);
    display: inline-block;
  }

  .count-hint {
    font-size: 12px;
    color: var(--muted);
  }

  .cast-row {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 12px;
  }

  .cast-card {
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    padding: 10px;
    text-align: center;
    overflow: hidden;
  }

  .cast-avatar-wrap {
    width: 100%;
    aspect-ratio: 1;
    border-radius: var(--radius);
    overflow: hidden;
    background: var(--bg3);
    margin-bottom: 8px;
  }

  .cast-avatar {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .cast-avatar.fallback {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--accent2);
    font-size: 26px;
    font-weight: 600;
    background: var(--accent2-soft);
  }

  .cast-avatar.fallback.hidden {
    display: none;
  }

  .cast-name {
    font-size: 12.5px;
    color: var(--ink);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cast-role {
    font-size: 11px;
    color: var(--muted);
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  @media (max-width: 1250px) {
    .cast-row { grid-template-columns: repeat(6, 1fr); }
  }
  @media (max-width: 900px) {
    .cast-row { grid-template-columns: repeat(4, 1fr); }
    .cast-section { padding: 18px 16px; }
  }
</style>
