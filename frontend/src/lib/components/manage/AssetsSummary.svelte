<script lang="ts">
  // 摘要条 — 概览页删除后承接它的数字（决策 1）。
  // 只读展示 + 点击切视图；不承载任何列表。
  import { SAVED_VIEWS, type StatsCountKey } from '$lib/media/views';
  import type { SavedViewId } from '$lib/media/status';

  let {
    counts = {},
    view = 'all',
    loading = false,
    onSelect
  }: {
    counts?: Partial<Record<StatsCountKey, number>>;
    view?: SavedViewId;
    loading?: boolean;
    onSelect: (id: SavedViewId) => void;
  } = $props();

  // 概览页原来展示的四个数字：总量 / 问题 / 缺失 / 待处理。
  // 「已忽略」放进来是因为它能解释「为什么待处理数字里没有它」。
  const CHIPS: SavedViewId[] = ['all', 'problem', 'missing', 'no_poster', 'metadata', 'ignored'];

  const chips = $derived(
    CHIPS.map((id) => SAVED_VIEWS.find((v) => v.id === id)).filter(
      (v): v is (typeof SAVED_VIEWS)[number] => Boolean(v)
    )
  );
</script>

<div class="summary" class:loading>
  {#each chips as chip (chip.id)}
    {@const value = chip.countKey ? counts[chip.countKey] : undefined}
    <button
      type="button"
      class="chip"
      class:active={view === chip.id}
      class:danger={chip.tone === 'danger' && (value ?? 0) > 0}
      class:warn={chip.tone === 'warn' && (value ?? 0) > 0}
      title={chip.hint}
      onclick={() => onSelect(chip.id)}
    >
      <span class="label">{chip.label}</span>
      <span class="value">{value ?? '—'}</span>
    </button>
  {/each}
</div>

<style>
  .summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px 16px 0;
  }
  .chip {
    appearance: none;
    display: flex;
    align-items: baseline;
    gap: 8px;
    font: inherit;
    padding: 7px 12px;
    border-radius: var(--radius);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    cursor: pointer;
    transition:
      border-color var(--dur-fast) var(--ease-out),
      background var(--dur-fast) var(--ease-out);
  }
  .chip:hover {
    border-color: var(--ink-faint);
    background: var(--bg-hover);
  }
  .chip.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--ink);
  }
  .chip .label {
    font-size: 12px;
  }
  .chip .value {
    font-family: var(--font-mono);
    font-size: 15px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--ink);
  }
  .chip.danger .value {
    color: var(--danger);
  }
  .chip.warn .value {
    color: var(--warn);
  }
  .chip.active .value {
    color: var(--accent);
  }
  .loading .value {
    opacity: 0.5;
  }
</style>
