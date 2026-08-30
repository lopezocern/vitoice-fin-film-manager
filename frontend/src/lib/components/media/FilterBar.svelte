<script lang="ts">
  import type { FilterState, ResolutionFilter, DurationFilter, FilterOptions } from './types';

  let {
    filter,
    filterOptions,
    onChange
  }: {
    filter: FilterState;
    filterOptions?: FilterOptions;
    onChange?: (filter: FilterState) => void;
  } = $props();

  let openMenu = $state<string | null>(null);

  type Option = { value: string; label: string };

  const typeOptions: Option[] = [
    { value: '', label: '全部媒体' },
    { value: 'video', label: '视频' },
    { value: 'audio', label: '音频' },
    { value: 'image', label: '图片' }
  ];

  const resolutionOptions: Option[] = [
    { value: '', label: '全部分辨率' },
    { value: '4k', label: '4K 及以上' },
    { value: '1080p', label: '1080p' },
    { value: '720p', label: '720p' },
    { value: '480p', label: '480p' },
    { value: 'other', label: '其他' }
  ];

  const ratingOptions: Option[] = [
    { value: '', label: '全部评分' },
    { value: '1', label: '★ 1 星及以上' },
    { value: '2', label: '★ 2 星及以上' },
    { value: '3', label: '★ 3 星及以上' },
    { value: '4', label: '★ 4 星及以上' },
    { value: '5', label: '★ 5 星' }
  ];

  const durationOptions: Option[] = [
    { value: '', label: '全部时长' },
    { value: 'short', label: '< 10 分钟' },
    { value: 'medium', label: '10 - 60 分钟' },
    { value: 'long', label: '> 60 分钟' }
  ];

  // 题材选项（从后端动态获取）
  const genreOptions = $derived<Option[]>([
    { value: '', label: '全部题材' },
    ...(filterOptions?.genres ?? []).map((g) => ({ value: g, label: g }))
  ]);

  // 国家/地区选项
  const countryOptions = $derived<Option[]>([
    { value: '', label: '全部地区' },
    ...(filterOptions?.countries ?? []).map((c) => ({ value: c, label: c }))
  ]);

  // 年份选项：全部年份 → 未知年份(year=0 对应后端 Media.year IS NULL)→ 具体年份
  const yearOptions = $derived<Option[]>([
    { value: '', label: '全部年份' },
    { value: '0', label: '未知年份' },
    ...(filterOptions?.years ?? []).map((y) => ({ value: String(y), label: String(y) }))
  ]);

  const typeLabel = $derived(
    typeOptions.find((o) => o.value === (filter.type ?? ''))?.label ?? '媒体'
  );
  const genreLabel = $derived(
    genreOptions.find((o) => o.value === (filter.genre ?? ''))?.label ?? '题材'
  );
  const countryLabel = $derived(
    countryOptions.find((o) => o.value === (filter.country ?? ''))?.label ?? '地区'
  );
  const yearLabel = $derived(
    yearOptions.find((o) => o.value === String(filter.year ?? ''))?.label ?? '年份'
  );
  const resLabel = $derived(
    resolutionOptions.find((o) => o.value === (filter.resolution ?? ''))?.label ?? '分辨率'
  );
  const ratingLabel = $derived(
    ratingOptions.find((o) => o.value === String(filter.ratingMin ?? ''))?.label ?? '评分'
  );
  const durationLabel = $derived(
    durationOptions.find((o) => o.value === (filter.duration ?? ''))?.label ?? '时长'
  );

  const activeCount = $derived(
    (filter.type ? 1 : 0) +
      (filter.genre ? 1 : 0) +
      (filter.country ? 1 : 0) +
      (filter.year !== undefined ? 1 : 0) +
      (filter.resolution ? 1 : 0) +
      (filter.ratingMin ? 1 : 0) +
      (filter.duration ? 1 : 0)
  );

  function toggleMenu(name: string): void {
    openMenu = openMenu === name ? null : name;
    menuActiveIdx = -1;
    if (openMenu) {
      // 打开后聚焦第一个选项（键盘可达）
      requestAnimationFrame(() => {
        const first = document.querySelector<HTMLElement>(
          `.chip-wrap[data-menu="${openMenu}"] .menu-item`
        );
        if (first) {
          first.focus();
          menuActiveIdx = 0;
        }
      });
    }
  }

  // ---- 键盘导航（listbox 模式）：↑↓ 移动 / Enter 选择 / Esc 关闭 ----
  let menuActiveIdx = $state(-1);

  function onChipKeydown(e: KeyboardEvent, name: string): void {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      toggleMenu(name);
    }
  }

  function onMenuKeydown(e: KeyboardEvent): void {
    const menu = e.currentTarget as HTMLElement;
    const opts = Array.from(menu.querySelectorAll<HTMLElement>('.menu-item'));
    if (opts.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      menuActiveIdx = (menuActiveIdx + 1) % opts.length;
      opts[menuActiveIdx]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      menuActiveIdx = (menuActiveIdx - 1 + opts.length) % opts.length;
      opts[menuActiveIdx]?.focus();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (menuActiveIdx >= 0 && menuActiveIdx < opts.length) opts[menuActiveIdx].click();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeMenus();
    }
  }

  function closeMenus(): void {
    openMenu = null;
  }

  function patch(p: Partial<FilterState>): void {
    onChange?.({ ...filter, ...p });
    closeMenus();
  }

  function pickType(value: string): void {
    patch({ type: value || undefined });
  }
  function pickGenre(value: string): void {
    patch({ genre: value || undefined });
  }
  function pickCountry(value: string): void {
    patch({ country: value || undefined });
  }
  function pickYear(value: string): void {
    patch({ year: value ? Number(value) : undefined });
  }
  function pickRes(value: string): void {
    patch({ resolution: (value || '') as ResolutionFilter });
  }
  function pickRating(value: string): void {
    patch({ ratingMin: value ? Number(value) : undefined });
  }
  function pickDuration(value: string): void {
    patch({ duration: (value || '') as DurationFilter });
  }

  function clearAll(): void {
    onChange?.({});
    closeMenus();
  }

  function onWindowClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    if (!target.closest('.chip-wrap')) closeMenus();
  }

  $effect(() => {
    if (openMenu) {
      window.addEventListener('click', onWindowClick);
      return () => window.removeEventListener('click', onWindowClick);
    }
  });
</script>

<div class="filter-bar">
  <div class="chips">
    <!-- 媒体类型 -->
    <div class="chip-wrap" data-menu="type">
      <button class="chip" class:active={!!filter.type} onclick={() => toggleMenu('type')} onkeydown={(e) => onChipKeydown(e, 'type')} aria-haspopup="listbox" aria-expanded={openMenu === 'type'}>
        <span>{typeLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'type'}
        <div class="menu" onkeydown={onMenuKeydown} role="listbox" aria-label="媒体类型">
          {#each typeOptions as o}
            <button class="menu-item" role="option" aria-selected={o.value === (filter.type ?? '')} class:active={o.value === (filter.type ?? '')} onclick={() => pickType(o.value)}>{o.label}</button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- 题材 -->
    <div class="chip-wrap" data-menu="genre">
      <button class="chip" class:active={!!filter.genre} onclick={() => toggleMenu('genre')} onkeydown={(e) => onChipKeydown(e, 'genre')} aria-haspopup="listbox" aria-expanded={openMenu === 'genre'}>
        <span>{genreLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'genre'}
        <div class="menu menu-scroll" onkeydown={onMenuKeydown} role="listbox" aria-label="题材">
          {#if genreOptions.length <= 1}
            <div class="menu-empty">暂无题材数据（需先刮削媒体）</div>
          {:else}
            {#each genreOptions as o}
              <button class="menu-item" role="option" aria-selected={o.value === (filter.genre ?? '')} class:active={o.value === (filter.genre ?? '')} onclick={() => pickGenre(o.value)}>{o.label}</button>
            {/each}
          {/if}
        </div>
      {/if}
    </div>

    <!-- 国家/地区 -->
    <div class="chip-wrap" data-menu="country">
      <button class="chip" class:active={!!filter.country} onclick={() => toggleMenu('country')} onkeydown={(e) => onChipKeydown(e, 'country')} aria-haspopup="listbox" aria-expanded={openMenu === 'country'}>
        <span>{countryLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'country'}
        <div class="menu menu-scroll" onkeydown={onMenuKeydown} role="listbox" aria-label="地区">
          {#if countryOptions.length <= 1}
            <div class="menu-empty">暂无地区数据（需先刮削媒体）</div>
          {:else}
            {#each countryOptions as o}
              <button class="menu-item" role="option" aria-selected={o.value === (filter.country ?? '')} class:active={o.value === (filter.country ?? '')} onclick={() => pickCountry(o.value)}>{o.label}</button>
            {/each}
          {/if}
        </div>
      {/if}
    </div>

    <!-- 年份 -->
    <div class="chip-wrap" data-menu="year">
      <button class="chip" class:active={!!filter.year} onclick={() => toggleMenu('year')} onkeydown={(e) => onChipKeydown(e, 'year')} aria-haspopup="listbox" aria-expanded={openMenu === 'year'}>
        <span>{yearLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'year'}
        <div class="menu menu-scroll" onkeydown={onMenuKeydown} role="listbox" aria-label="年份">
          {#if yearOptions.length <= 1}
            <div class="menu-empty">暂无年份数据（需先刮削媒体）</div>
          {:else}
            {#each yearOptions as o}
              <button class="menu-item" role="option" aria-selected={o.value === String(filter.year ?? '')} class:active={o.value === String(filter.year ?? '')} onclick={() => pickYear(o.value)}>{o.label}</button>
            {/each}
          {/if}
        </div>
      {/if}
    </div>

    <!-- 分辨率 -->
    <div class="chip-wrap" data-menu="resolution">
      <button class="chip" class:active={!!filter.resolution} onclick={() => toggleMenu('resolution')} onkeydown={(e) => onChipKeydown(e, 'resolution')} aria-haspopup="listbox" aria-expanded={openMenu === 'resolution'}>
        <span>{resLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'resolution'}
        <div class="menu" onkeydown={onMenuKeydown} role="listbox" aria-label="分辨率">
          {#each resolutionOptions as o}
            <button class="menu-item" role="option" aria-selected={o.value === (filter.resolution ?? '')} class:active={o.value === (filter.resolution ?? '')} onclick={() => pickRes(o.value)}>{o.label}</button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- 评分 -->
    <div class="chip-wrap" data-menu="rating">
      <button class="chip" class:active={!!filter.ratingMin} onclick={() => toggleMenu('rating')} onkeydown={(e) => onChipKeydown(e, 'rating')} aria-haspopup="listbox" aria-expanded={openMenu === 'rating'}>
        <span>{ratingLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'rating'}
        <div class="menu" onkeydown={onMenuKeydown} role="listbox" aria-label="评分">
          {#each ratingOptions as o}
            <button class="menu-item" role="option" aria-selected={o.value === String(filter.ratingMin ?? '')} class:active={o.value === String(filter.ratingMin ?? '')} onclick={() => pickRating(o.value)}>{o.label}</button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- 时长 -->
    <div class="chip-wrap" data-menu="duration">
      <button class="chip" class:active={!!filter.duration} onclick={() => toggleMenu('duration')} onkeydown={(e) => onChipKeydown(e, 'duration')} aria-haspopup="listbox" aria-expanded={openMenu === 'duration'}>
        <span>{durationLabel}</span><span class="caret">▾</span>
      </button>
      {#if openMenu === 'duration'}
        <div class="menu" onkeydown={onMenuKeydown} role="listbox" aria-label="时长">
          {#each durationOptions as o}
            <button class="menu-item" role="option" aria-selected={o.value === (filter.duration ?? '')} class:active={o.value === (filter.duration ?? '')} onclick={() => pickDuration(o.value)}>{o.label}</button>
          {/each}
        </div>
      {/if}
    </div>

    {#if activeCount > 0}
      <button class="clear" onclick={clearAll}>清除筛选 ({activeCount})</button>
    {/if}
  </div>
</div>

<style>
  .filter-bar {
    display: flex;
    align-items: center;
  }

  .chips {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .chip-wrap {
    position: relative;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-full);
    color: var(--ink);
    font-size: 12.5px;
    transition: all 150ms;
  }

  .chip:hover {
    border-color: var(--muted);
  }

  .chip.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
  }

  .caret {
    font-size: 9px;
    color: var(--muted);
  }

  .chip.active .caret {
    color: var(--accent);
  }

  .menu {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    min-width: 180px;
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
    padding: 4px;
    z-index: 500;
    animation: pop 120ms ease;
  }

  @keyframes pop {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .menu-scroll {
    max-height: 320px;
    overflow-y: auto;
  }

  .menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border: none;
    background: none;
    border-radius: var(--radius);
    color: var(--ink);
    font-size: 13px;
    text-align: left;
    transition: background 120ms;
  }

  .menu-item:hover {
    background: var(--bg-soft);
  }

  .menu-item.active {
    color: var(--accent);
    background: var(--accent-soft);
  }

  .menu-empty {
    padding: 12px;
    text-align: center;
    color: var(--muted);
    font-size: 12.5px;
  }

  .clear {
    background: none;
    border: none;
    color: var(--muted);
    font-size: 12.5px;
    padding: 4px 8px;
    border-radius: var(--radius);
    transition: color 150ms;
  }

  .clear:hover {
    color: var(--accent);
  }
</style>
