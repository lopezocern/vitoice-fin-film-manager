<script lang="ts">
  import type { SortState, SortField } from './types';

  let {
    sort,
    total = 0,
    onChange
  }: {
    sort: SortState;
    total?: number;
    onChange?: (sort: SortState) => void;
  } = $props();

  interface SortOption {
    field: SortField;
    label: string;
  }

  const options: SortOption[] = [
    { field: 'created_at', label: '添加时间' },
    { field: 'filename', label: '标题' },
    { field: 'rating', label: '评分' },
    { field: 'duration', label: '时长' },
    { field: 'progress', label: '进度' }
  ];

  function select(field: SortField): void {
    if (sort.field === field) {
      // 同一字段：切换升降序
      onChange?.({ field, order: sort.order === 'asc' ? 'desc' : 'asc' });
    } else {
      // 新字段默认降序
      onChange?.({ field, order: 'desc' });
    }
  }
</script>

<div class="sort-bar">
  <div class="sort-options">
    {#each options as o (o.field)}
      <button
        class="sort-btn"
        class:active={sort.field === o.field}
        onclick={() => select(o.field)}
      >
        <span>{o.label}</span>
        {#if sort.field === o.field}
          <span class="arrow">{sort.order === 'asc' ? '↑' : '↓'}</span>
        {/if}
      </button>
    {/each}
  </div>
  <div class="total">共 {total.toLocaleString('zh-CN')} 项</div>
</div>

<style>
  .sort-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .sort-options {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }

  .sort-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 28px;
    padding: 0 10px;
    border: none;
    background: none;
    border-radius: var(--radius);
    color: var(--muted);
    font-size: 12.5px;
    transition: background 150ms, color 150ms;
  }

  .sort-btn:hover {
    background: var(--bg-soft);
    color: var(--ink);
  }

  .sort-btn.active {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 500;
  }

  .arrow {
    font-size: 11px;
  }

  .total {
    font-size: 12.5px;
    color: var(--muted);
    white-space: nowrap;
    flex-shrink: 0;
  }
</style>
