<script lang="ts">
  import type { Series } from '$lib/api/series';
  import { seriesApi } from '$lib/api/series';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';

  let {
    items,
    onSelect,
    mode = 'poster',
    density = 180
  }: {
    items: Series[];
    onSelect?: (series: Series) => void;
    mode?: 'mixed' | 'poster' | 'list' | 'timeline';
    density?: number;
  } = $props();

  const restrictedLibIds = $derived(
    new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id)))
  );

  function shouldMask(series: Series): boolean {
    return settingsStore.maskRestricted && restrictedLibIds.has(String(series.library_id));
  }

  const groups = $derived.by(() => {
    const grouped = new Map<string, Series[]>();
    for (const series of items) {
      const key = series.year ? String(series.year) : 'unknown';
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(series);
    }
    return [...grouped.entries()]
      .sort(([a], [b]) => a === 'unknown' ? 1 : b === 'unknown' ? -1 : Number(b) - Number(a))
      .map(([key, series]) => ({ key, label: key === 'unknown' ? '未知年份' : `${key}年`, series }));
  });
</script>

{#snippet seriesCard(s: Series)}
    <button class="series-card" data-id={s.id} onclick={() => onSelect?.(s)}>
      <div class="card-thumb">
        {#if s.poster_path}
          <img src={seriesApi.posterUrl(s.id)} alt={s.title} loading="lazy" />
        {:else}
          <div class="thumb-fallback">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <line x1="2" y1="8" x2="22" y2="8" />
              <polyline points="9,14 12,14 12,11" />
            </svg>
          </div>
        {/if}
        <span class="ep-count">{s.episode_count} 集</span>
        {#if shouldMask(s)}
          <div class="content-mask" title="限制内容 — 点击查看">
            <span class="mask-icon">🔞</span>
          </div>
        {/if}
      </div>
      <div class="card-info">
        <div class="card-title" title={s.title}>{s.title}</div>
        <div class="card-meta">
          {#if s.year}<span class="muted">{s.year}</span>{/if}
          {#if s.total_seasons}<span class="muted">{s.total_seasons} 季</span>{/if}
        </div>
      </div>
    </button>
{/snippet}

<div class="series-view" class:list-mode={mode === 'list'} class:timeline-mode={mode === 'timeline'} style={`--media-card-width:${density}px`}>
  {#if mode === 'timeline'}
    {#each groups as group (group.key)}
      <section class="series-year">
        <div class="year-head"><strong>{group.label}</strong><span>{group.series.length} 部</span></div>
        <div class="series-wall">
          {#each group.series as s (s.id)}{@render seriesCard(s)}{/each}
        </div>
      </section>
    {/each}
  {:else}
    <div class="series-wall">
      {#each items as s (s.id)}{@render seriesCard(s)}{/each}
    </div>
  {/if}
</div>

<style>
  .series-view { display: block; }
  .series-wall {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--media-card-width, 180px), 1fr));
    grid-auto-flow: dense;
    gap: 16px;
    align-items: start;
  }

  .series-card {
    display: flex;
    flex-direction: column;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    overflow: hidden;
    padding: 0;
    cursor: pointer;
    text-align: left;
    transition: transform 200ms ease, box-shadow 200ms ease, border-color 200ms;
    /* Skip rendering/layout for off-screen cards */
    content-visibility: auto;
    contain-intrinsic-size: 180px 320px;
  }

  .series-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    border-color: var(--accent);
  }

  .card-thumb {
    position: relative;
    aspect-ratio: 2 / 3;
    background: var(--bg-soft);
    overflow: hidden;
  }

  .card-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: right center; /* 横版封面右侧裁切（主体多在右侧）；竖版海报不受影响 */
    display: block;
  }

  .content-mask {
    position: absolute;
    inset: 0;
    z-index: 5;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: inherit;
    background: rgba(0, 0, 0, 0.75);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
  }

  .mask-icon {
    font-size: 28px;
    opacity: 0.8;
  }

  .series-card:hover .content-mask {
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(3px);
    -webkit-backdrop-filter: blur(3px);
  }

  .thumb-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    background: linear-gradient(135deg, var(--bg-soft), var(--bg2));
  }

  .ep-count {
    position: absolute;
    bottom: 6px;
    right: 6px;
    background: rgba(0, 0, 0, 0.75);
    color: #fff;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    font-variant-numeric: tabular-nums;
  }

  .card-info {
    padding: 8px 10px 10px;
  }

  .card-title {
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    min-height: 2.7em;
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 5px;
    font-size: 11.5px;
  }

  .muted {
    color: var(--muted);
  }

  .series-view.list-mode .series-wall {
    grid-template-columns: 1fr;
    gap: 7px;
  }

  .series-view.list-mode .series-card {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr);
    min-height: 88px;
  }

  .series-view.list-mode .card-thumb { width: 64px; height: 88px; aspect-ratio: auto; }
  .series-view.list-mode .card-info { align-self: center; }
  .series-view.list-mode .card-title { min-height: 0; -webkit-line-clamp: 1; line-clamp: 1; }

  .timeline-mode { display: flex; flex-direction: column; gap: 28px; }
  .series-year { display: flex; flex-direction: column; gap: 12px; }
  .year-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--rule);
    color: var(--ink);
  }
  .year-head strong { font-size: 15px; }
  .year-head span { color: var(--muted); font-size: 12px; }

  @media (max-width: 520px) {
    .series-wall {
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 12px;
    }
  }
</style>
