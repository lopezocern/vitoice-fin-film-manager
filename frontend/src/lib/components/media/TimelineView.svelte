<script lang="ts">
  import type { Media } from '$lib/api/media';
  import PosterWall from './PosterWall.svelte';

  let {
    items,
    onSelect,
    onplay,
    density = 180
  }: {
    items: Media[];
    onSelect?: (media: Media) => void;
    onplay?: (media: Media) => void;
    density?: number;
  } = $props();

  interface Group {
    key: string;
    label: string;
    items: Media[];
  }

  /**
   * 时间轴按【电影发布年份】分组（release_year / year），而非添加时间。
   * 无发布信息的媒体归入"未知年份"（排在最后）。
   * 每组内部直接复用 PosterWall 渲染（卡片样式/比例/受限遮罩与海报墙完全一致）。
   * 注意：数据须全量（媒体页在 timeline 视图下不分页，循环拉满 total），
   * 否则年份组会缺失媒体（只显示已加载的分页部分）。
   */
  function yearOf(media: Media): number {
    const y = media.year;
    if (y && y > 1900) return y;
    const rd = media.release_date;
    if (rd) {
      const parsed = parseInt(rd.slice(0, 4), 10);
      if (!isNaN(parsed) && parsed > 1900) return parsed;
    }
    return 0;
  }

  function groupKey(media: Media): { key: string; label: string } {
    const y = yearOf(media);
    if (!y) return { key: 'unknown', label: '未知年份' };
    return { key: String(y), label: `${y}年` };
  }

  const groups = $derived.by(() => {
    const map = new Map<string, Group>();
    for (const m of items) {
      const { key, label } = groupKey(m);
      if (!map.has(key)) map.set(key, { key, label, items: [] });
      map.get(key)!.items.push(m);
    }
    // 年份降序（新片在前），未知年份最后
    return Array.from(map.values()).sort((a, b) => {
      if (a.key === 'unknown') return 1;
      if (b.key === 'unknown') return -1;
      return Number(b.key) - Number(a.key);
    });
  });
</script>

<div class="timeline">
  {#each groups as group (group.key)}
    <section class="tl-group">
      <div class="tl-head">
        <span class="tl-label">{group.label}</span>
        <span class="tl-count">{group.items.length} 项</span>
      </div>
      <PosterWall items={group.items} onSelect={onSelect} onplay={onplay} mode="mixed" {density} />
    </section>
  {:else}
    <div class="tl-empty">暂无媒体</div>
  {/each}
</div>

<style>
  .timeline {
    display: flex;
    flex-direction: column;
    gap: 28px;
  }

  .tl-group {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .tl-head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--rule);
  }

  .tl-label {
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
  }

  .tl-count {
    font-size: 12px;
    color: var(--muted);
  }

  .tl-empty {
    padding: 60px 0;
    text-align: center;
    color: var(--muted);
    font-size: 14px;
  }
</style>
