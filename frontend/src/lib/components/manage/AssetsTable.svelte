<script lang="ts">
  // 资产表格 — 唯一列表层的表格皮肤。
  // 渲染用 CSS grid 而非 <table>：行能整体虚拟化/拖动，列宽由 columns.ts 定义。
  import { mediaApi, type Media, type MediaSortField } from '$lib/api/media';
  import { imageFallback } from '$lib/utils/image-fallback';
  import { formatDuration, formatSize } from '$lib/utils/format';
  import { ASSET_COLUMNS, SORTABLE_COLUMNS, gridTemplate, visibleColumns } from '$lib/media/columns';
  import { mediaStateChips } from '$lib/media/status';
  import { columnPrefs } from '$lib/media/columnPrefs.svelte';
  import { isEditableTarget, moveCursor, resolveNavKey } from '$lib/media/keyboardNav';
  import { computeWindow } from '$lib/media/virtualWindow';
  import { untrack } from 'svelte';

  let {
    items = [],
    selected = new Set<number>(),
    sort = 'created_at',
    order = 'desc',
    loading = false,
    libraryName = () => '',
    scroller = null,
    onToggle,
    onToggleAll,
    onSort,
    onOpen,
    onEdit,
    onIgnore
  }: {
    items?: Media[];
    selected?: Set<number>;
    sort?: MediaSortField;
    order?: 'asc' | 'desc';
    loading?: boolean;
    libraryName?: (libraryId: string) => string;
    onToggle: (id: string) => void;
    onToggleAll: (ids: string[], checked: boolean) => void;
    onSort: (field: MediaSortField) => void;
    onOpen: (media: Media) => void;
    onEdit: (media: Media) => void;
    onIgnore: (media: Media) => void;
    /** 外层滚动容器（.body）。用于虚拟滚动与键盘光标定位；缺省则全量渲染。 */
    scroller?: HTMLElement | null;
  } = $props();

  // ---- 虚拟滚动 ----
  // 行高必须与 CSS `.row { min-height }` 完全一致，否则滚动位置与内容会错位。
  const ROW_H = 72;
  const OVERSCAN = 6;
  /** 少于这个条数就全量渲染：虚拟化会让 Ctrl+F / 打印 / 屏幕阅读器失真，
   *  874 条以内没必要付出这个代价。 */
  const VIRTUAL_THRESHOLD = 200;

  let scrollTop = $state(0);
  let viewportH = $state(0);
  let headH = $state(0);

  const virtual = $derived(items.length > VIRTUAL_THRESHOLD && !!scroller);

  /** 可视窗口 [start, end)；非虚拟化时覆盖全集（窗口算法在 virtualWindow.ts 中单测）。 */
  const win = $derived(
    virtual
      ? computeWindow({
          scrollTop,
          headHeight: headH,
          viewportHeight: viewportH,
          rowHeight: ROW_H,
          total: items.length,
          overscan: OVERSCAN
        })
      : { start: 0, end: items.length, padTop: 0, padBottom: 0 }
  );
  const range = $derived({ start: win.start, end: win.end });

  const rows = $derived(items.slice(win.start, win.end));

  $effect(() => {
    if (!virtual) return;
    const el = scroller;
    if (!el) return;
    const measure = (): void => {
      viewportH = el.clientHeight;
      scrollTop = el.scrollTop;
    };
    measure();
    const onScroll = (): void => {
      scrollTop = el.scrollTop;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => {
      el.removeEventListener('scroll', onScroll);
      ro.disconnect();
    };
  });

  // ---- 列宽拖拽（持久化到 localStorage）----
  const WIDTH_KEY = 'vitoice.assets.colwidths';
  const MIN_COL_PX = 64;

  function readWidths(): Record<string, number> {
    if (typeof localStorage === 'undefined') return {};
    try {
      return JSON.parse(localStorage.getItem(WIDTH_KEY) ?? '{}') as Record<string, number>;
    } catch {
      return {};
    }
  }

  let widths = $state<Record<string, number>>(readWidths());

  // ---- 键盘导航 ----
  // 光标是"视觉焦点"，与"已选中"分开：j/k 移动光标，空格才切换选中。
  // 两者混在一起会让"浏览"变成"误选"。
  let cursor = $state(-1);
  let listEl = $state<HTMLDivElement | null>(null);

  // 列表变化（翻页/筛选）后光标归位，避免指向已不存在的行
  $effect(() => {
    const len = items.length;
    untrack(() => {
      if (cursor >= len) cursor = len > 0 ? len - 1 : -1;
    });
  });

  function scrollCursorIntoView(): void {
    if (cursor < 0) return;
    if (virtual) {
      // 虚拟化时光标行可能根本没渲染，不能靠 scrollIntoView；直接按行高算位置
      const sc = scroller;
      if (!sc) return;
      const rowTop = headH + cursor * ROW_H;
      const rowBottom = rowTop + ROW_H;
      const viewTop = sc.scrollTop + headH;
      const viewBottom = sc.scrollTop + sc.clientHeight;
      if (rowTop < viewTop) sc.scrollTop = rowTop - headH;
      else if (rowBottom > viewBottom) sc.scrollTop = rowBottom - sc.clientHeight;
      return;
    }
    const row = listEl?.querySelector<HTMLElement>(`[data-row-index="${cursor}"]`);
    row?.scrollIntoView({ block: 'nearest' });
  }

  function onWindowKeydown(e: KeyboardEvent): void {
    // 行内处理器已经消费掉的按键（Enter/空格）不再二次处理
    if (e.defaultPrevented) return;
    // 有模态框打开时，"x/e/i" 不该偷偷作用到背后的表格
    if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
    // 输入框/下拉里打字时不抢键；对话框打开时也不抢（由对话框自己处理）
    if (isEditableTarget(e.target as { tagName?: string; isContentEditable?: boolean } | null)) return;
    const action = resolveNavKey(e);
    if (action === 'none') return;
    if (items.length === 0) return;

    // 只在"表格里或页面上没有别的输入焦点"时接管方向键
    if (action === 'next' || action === 'prev') {
      e.preventDefault();
      cursor = moveCursor(cursor, action === 'next' ? 1 : -1, items.length);
      scrollCursorIntoView();
      return;
    }

    const current = items[cursor];
    if (action === 'toggleAll') {
      e.preventDefault();
      onHeaderToggle(!allSelected);
      return;
    }
    if (action === 'toggle' && current) {
      e.preventDefault();
      onToggle(current.id);
      return;
    }
    if (!current) return;
    if (action === 'open') {
      e.preventDefault();
      onOpen(current);
    } else if (action === 'edit') {
      e.preventDefault();
      onEdit(current);
    } else if (action === 'ignore') {
      e.preventDefault();
      onIgnore(current);
    }
  }

  /** 只渲染未被用户隐藏的列（`asset` / `actions` 恒显示）。 */
  const cols = $derived(visibleColumns(ASSET_COLUMNS, columnPrefs.hidden));

  // 有显式宽度的列用固定 px，其余沿用 columns.ts 的响应式轨道
  const template = $derived(
    gridTemplate(cols.map((c) => (widths[c.id] ? { ...c, track: `${widths[c.id]}px` } : c)))
  );

  let dragId = $state<string | null>(null);
  let dragStartX = 0;
  let dragStartW = 0;

  function startResize(e: PointerEvent, id: string, track: string): void {
    e.preventDefault();
    e.stopPropagation();
    dragId = id;
    dragStartX = e.clientX;
    // 首次拖拽：用一个合理起点（已保存则用之，否则按当前轨道的首数字兜底）
    dragStartW = widths[id] ?? Number(track.match(/(\d+)px/)?.[1] ?? 160);
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  }

  function onResizeMove(e: PointerEvent): void {
    if (!dragId) return;
    const next = Math.max(MIN_COL_PX, Math.round(dragStartW + (e.clientX - dragStartX)));
    widths = { ...widths, [dragId]: next };
  }

  function endResize(): void {
    if (!dragId) return;
    dragId = null;
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem(WIDTH_KEY, JSON.stringify(widths));
      } catch {
        /* 配额/隐私模式：列宽不持久化不影响使用 */
      }
    }
  }

  function resetWidths(): void {
    widths = {};
    if (typeof localStorage !== 'undefined') localStorage.removeItem(WIDTH_KEY);
  }

  const allSelected = $derived(items.length > 0 && items.every((m) => selected.has(Number(m.id))));

  function onHeaderToggle(checked: boolean): void {
    onToggleAll(
      items.map((m) => m.id),
      checked
    );
  }

  function sortIndicator(field?: MediaSortField): string {
    if (!field || field !== sort) return '';
    return order === 'asc' ? '↑' : '↓';
  }

  function thumbSrc(media: Media): string | null {
    if (media.poster) return mediaApi.posterUrl(media.id, media.updated_at);
    if (media.thumbnail) return mediaApi.thumbnailUrl(media.id, media.updated_at);
    return null;
  }

  const TYPE_ICON: Record<string, string> = { video: '▶', audio: '♪', image: '▣' };
</script>

<svelte:window onkeydown={onWindowKeydown} />

<div class="table" class:busy={loading} style="--cols: {template}" bind:this={listEl}>
  <div class="head" bind:clientHeight={headH}>
    <div class="cell check">
      <input
        type="checkbox"
        checked={allSelected}
        onchange={(e) => onHeaderToggle(e.currentTarget.checked)}
        aria-label="全选本页"
      />
    </div>
    {#each cols as col (col.id)}
      {@const sortable = SORTABLE_COLUMNS.some((c) => c.id === col.id)}
      <div
        class="cell head-cell"
        class:right={col.align === 'right'}
        class:center={col.align === 'center'}
        class:sortable
      >
        {#if sortable && col.sortField}
          <button type="button" class="sort-btn" onclick={() => onSort(col.sortField!)}>
            {col.label}<span class="ind">{sortIndicator(col.sortField)}</span>
          </button>
        {:else}
          {col.label}
        {/if}
        {#if col.id !== 'actions'}
          <span
            class="resizer"
            class:active={dragId === col.id}
            role="separator"
            aria-label={`调整 ${col.label || col.id} 列宽`}
            onpointerdown={(e) => startResize(e, col.id, col.track)}
            onpointermove={onResizeMove}
            onpointerup={endResize}
            onpointercancel={endResize}
            ondblclick={resetWidths}
          ></span>
        {/if}
      </div>
    {/each}
  </div>

  <!-- 虚拟滚动：上下留出未渲染行的高度，滚动条长度保持真实 -->
  {#if virtual && range.start > 0}
    <div class="vpad" style={`height:${range.start * ROW_H}px`} aria-hidden="true"></div>
  {/if}

  {#each rows as media, i (media.id)}
    {@const index = range.start + i}
    {@const id = Number(media.id)}
    {@const chips = mediaStateChips(media)}
    {@const src = thumbSrc(media)}
    <div
      class="row"
      class:selected={selected.has(id)}
      class:cursor={index === cursor}
      data-row-index={index}
      role="row"
      tabindex="0"
      aria-selected={selected.has(id)}
      onclick={() => (cursor = index)}
      onkeydown={(e) => {
        // 行内键盘：Enter 打开、空格切换选中（j/k 由窗口级处理器负责）
        if (e.key === 'Enter') {
          e.preventDefault();
          onOpen(media);
        } else if (e.key === ' ' || e.key === 'Spacebar') {
          e.preventDefault();
          onToggle(media.id);
        }
      }}
    >
      <div class="cell check">
        <input
          type="checkbox"
          checked={selected.has(id)}
          onchange={() => onToggle(media.id)}
          aria-label="选择"
        />
      </div>

      <div class="cell asset">
        <button type="button" class="thumb" onclick={() => onOpen(media)} title="查看详情">
          {#if src}
            <img {src} alt="" loading="lazy" onerror={(e) => imageFallback(e, media)} />
          {:else}
            <span class="fb">{TYPE_ICON[media.type] ?? '▶'}</span>
          {/if}
        </button>
        <div class="copy">
          <button type="button" class="title" onclick={() => onOpen(media)}>
            {media.title ?? media.filename}
          </button>
          <span class="sub" title={media.filename}>{media.filename}</span>
        </div>
      </div>

      {#if columnPrefs.isVisible('state')}
        <div class="cell">
          <div class="state">
            <span class="pill {chips.file.tone}">{chips.file.label}</span>
            <span class="pill {chips.metadata.tone}">{chips.metadata.label}</span>
          </div>
        </div>
      {/if}

      {#if columnPrefs.isVisible('library')}
        <div class="cell muted ellipsis">{libraryName(media.library_id)}</div>
      {/if}

      {#if columnPrefs.isVisible('tags')}
        <div class="cell tags">
          {#if media.tags.length === 0}
            <span class="muted">—</span>
          {:else}
            {#each media.tags.slice(0, 3) as tag (tag)}
              <span class="tag">{tag}</span>
            {/each}
            {#if media.tags.length > 3}
              <span class="tag more">+{media.tags.length - 3}</span>
            {/if}
          {/if}
        </div>
      {/if}

      {#if columnPrefs.isVisible('duration')}
        <div class="cell right mono">{media.duration ? formatDuration(media.duration) : '—'}</div>
      {/if}
      {#if columnPrefs.isVisible('size')}
        <div class="cell right mono">{media.size ? formatSize(media.size) : '—'}</div>
      {/if}
      {#if columnPrefs.isVisible('rating')}
        <div class="cell center stars" title={media.rating ? `评分 ${media.rating}` : '未评分'}>
          {#if media.rating}
            {'★'.repeat(Math.max(0, Math.min(5, media.rating)))}
          {:else}
            <span class="muted">—</span>
          {/if}
        </div>
      {/if}

      <div class="cell right actions">
        <button type="button" class="act" onclick={() => onOpen(media)}>详情</button>
        <button type="button" class="act" title="编辑标题/年份/简介/封面" onclick={() => onEdit(media)}>
          编辑
        </button>
        <button
          type="button"
          class="act"
          title={media.metadata_ignored ? '恢复刮削' : '忽略刮削'}
          onclick={() => onIgnore(media)}
        >
          {media.metadata_ignored ? '恢复' : '忽略'}
        </button>
      </div>
    </div>
  {/each}

  {#if virtual && range.end < items.length}
    <div
      class="vpad"
      style={`height:${(items.length - range.end) * ROW_H}px`}
      aria-hidden="true"
    ></div>
  {/if}

  {#if items.length === 0 && !loading}
    <div class="empty">
      <p>这个视图下没有条目</p>
      <p class="hint">换个视图，或清除筛选条件</p>
    </div>
  {/if}
</div>

<style>
  .table {
    display: flex;
    flex-direction: column;
    padding: 0 16px 16px;
    overflow-x: auto;
  }
  .head,
  .row {
    display: grid;
    grid-template-columns: 28px var(--cols);
    align-items: center;
    gap: 10px;
    min-width: 860px;
  }
  .head {
    position: sticky;
    top: 0;
    z-index: 1;
    padding: 8px 0;
    background: var(--bg);
    border-bottom: 1px solid var(--rule);
    font-size: 12px;
    color: var(--ink-tertiary);
  }
  .row {
    padding: 7px 0;
    /* 虚拟滚动按固定行高计算窗口，改动这里必须同步脚本里的 ROW_H */
    min-height: 72px;
    box-sizing: border-box;
    border-bottom: 1px solid var(--rule-light);
    font-size: 13px;
    color: var(--ink-secondary);
  }
  .vpad {
    flex: none;
  }
  .row:hover {
    background: var(--bg-hover);
  }
  .row.selected {
    background: var(--accent-soft);
  }
  /* 键盘光标：用内阴影而不是 outline，避免撑开行高影响对齐 */
  .row.cursor {
    box-shadow: inset 2px 0 0 var(--accent);
    background: color-mix(in srgb, var(--accent) 7%, transparent);
  }
  .row.cursor.selected {
    background: var(--accent-soft);
  }
  .cell {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .cell.right {
    justify-content: flex-end;
    text-align: right;
  }
  .cell.center {
    justify-content: center;
    text-align: center;
  }
  .head-cell.right {
    justify-content: flex-end;
  }
  .head-cell.center {
    justify-content: center;
  }
  .head-cell {
    position: relative;
  }
  .resizer {
    position: absolute;
    top: 0;
    right: -5px;
    width: 10px;
    height: 100%;
    cursor: col-resize;
    touch-action: none;
  }
  .resizer::after {
    content: '';
    position: absolute;
    top: 25%;
    right: 4px;
    width: 1px;
    height: 50%;
    background: transparent;
  }
  .resizer:hover::after,
  .resizer.active::after {
    background: var(--accent);
  }
  .sort-btn {
    font: inherit;
    font-size: 12px;
    padding: 0;
    border: none;
    background: none;
    color: inherit;
    cursor: pointer;
  }
  .sort-btn:hover {
    color: var(--ink);
  }
  .ind {
    margin-left: 3px;
    color: var(--accent);
  }
  .asset {
    gap: 10px;
  }
  .thumb {
    flex: none;
    width: 40px;
    height: 56px;
    border-radius: var(--radius-sm);
    overflow: hidden;
    border: 1px solid var(--rule);
    background: var(--bg-surface);
    padding: 0;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .thumb .fb {
    color: var(--ink-faint);
    font-size: 14px;
  }
  .copy {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .title {
    font: inherit;
    font-size: 13.5px;
    text-align: left;
    padding: 0;
    border: none;
    background: none;
    color: var(--ink);
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .title:hover {
    color: var(--accent);
  }
  .sub,
  .muted {
    color: var(--ink-tertiary);
    font-size: 12px;
  }
  .sub {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .state {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }
  .pill {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: var(--radius-full);
    border: 1px solid var(--rule);
    color: var(--ink-tertiary);
    white-space: nowrap;
  }
  .pill.danger {
    border-color: var(--danger);
    color: var(--danger);
  }
  .pill.warn {
    border-color: var(--warn);
    color: var(--warn);
  }
  .pill.ok {
    border-color: transparent;
    color: var(--ink-tertiary);
  }
  .tags {
    overflow: hidden;
  }
  .tag {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: var(--radius-xs);
    background: var(--bg-surface);
    color: var(--ink-secondary);
    white-space: nowrap;
  }
  .tag.more {
    background: transparent;
    color: var(--ink-tertiary);
  }
  .mono {
    font-family: var(--font-mono);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
  .stars {
    color: var(--warn);
    letter-spacing: 1px;
    font-size: 12px;
  }
  .actions {
    gap: 3px;
    flex-wrap: nowrap;
  }
  .act {
    font: inherit;
    font-size: 11.5px;
    padding: 3px 7px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--ink-tertiary);
    cursor: pointer;
    white-space: nowrap;
  }
  .act:hover {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .busy {
    opacity: 0.55;
    transition: opacity var(--dur-fast);
  }
  .empty {
    padding: 48px 0;
    text-align: center;
    color: var(--ink-tertiary);
  }
  .empty p {
    margin: 0;
  }
  .empty .hint {
    margin-top: 6px;
    font-size: 12.5px;
    color: var(--ink-faint);
  }
</style>
