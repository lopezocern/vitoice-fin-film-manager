<script lang="ts">
  // 评分星星组件：5 颗星，hover 预览，点击设置评分
  // onrate 回调接收 0-5 的值，0 表示清除评分

  let {
    value = $bindable(0),
    size = 16,
    readonly = false,
    allowClear = true,
    onrate
  }: {
    value?: number;
    size?: number;
    readonly?: boolean;
    allowClear?: boolean;
    onrate?: (value: number) => void;
  } = $props();

  let hover = $state(0);

  const display = $derived(hover || value);

  function enter(v: number): void {
    if (readonly) return;
    hover = v;
  }

  function leave(): void {
    hover = 0;
  }

  function rate(v: number): void {
    if (readonly) return;
    // 再次点击当前评分且允许清除时，清除评分
    const next = (allowClear && v === value) ? 0 : v;
    onrate?.(next);
  }

  function starLabel(i: number): string {
    return `${i} 星`;
  }
</script>

<div
  class="rating-stars"
  class:readonly
  style="--star-size:{size}px"
  role={readonly ? 'img' : 'slider'}
  aria-valuenow={value}
  aria-valuemin={0}
  aria-valuemax={5}
  onmouseleave={leave}
>
  {#each Array(5) as _, i (i)}
    {@const idx = i + 1}
    <button
      type="button"
      class="star"
      class:filled={idx <= display}
      class:dim={idx > display}
      disabled={readonly}
      aria-label={starLabel(idx)}
      onmouseenter={() => enter(idx)}
      onclick={() => rate(idx)}
    >
      <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
        <path
          d="M12 2.5l2.95 5.98 6.6.96-4.77 4.65 1.13 6.57L12 17.55l-5.91 3.11 1.13-6.57L2.45 9.44l6.6-.96L12 2.5z"
        />
      </svg>
    </button>
  {/each}
</div>

<style>
  .rating-stars {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    line-height: 0;
  }

  .star {
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
    transition: transform 150ms ease;
  }

  .star:disabled {
    cursor: default;
  }

  .rating-stars:not(.readonly) .star:not(:disabled):hover {
    transform: scale(1.15);
  }

  .star svg {
    display: block;
    fill: var(--rule);
    stroke: none;
    transition: fill 200ms ease;
  }

  .star.filled svg {
    fill: var(--accent2);
  }

  .star.dim svg {
    fill: var(--rule);
  }

  .readonly .star.filled svg {
    fill: var(--accent2);
  }
</style>
