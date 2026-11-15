<script lang="ts">
  // Renders the shared toast queue (lib/stores/toast.svelte.ts).
  import { toasts } from '$lib/stores/toast.svelte';
</script>

<div class="toasts" role="status" aria-live="polite">
  {#each toasts.items as t (t.id)}
    <div class="toast" class:err={t.tone === 'err'} class:warn={t.tone === 'warn'}>
      <span class="msg">{t.message}</span>
      {#if t.action}
        <button type="button" class="act" onclick={() => void toasts.runAction(t.id)}>
          {t.action.label}
        </button>
      {/if}
      <button type="button" class="close" aria-label="关闭提示" onclick={() => toasts.dismiss(t.id)}>
        ✕
      </button>
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    left: 50%;
    bottom: 26px;
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 90;
    pointer-events: none;
  }
  .toast {
    pointer-events: auto;
    display: flex;
    align-items: center;
    gap: 10px;
    font: inherit;
    font-size: 13px;
    line-height: 1.4;
    padding: 9px 12px 9px 15px;
    border-radius: var(--radius-lg);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink);
    box-shadow: var(--shadow-md);
    max-width: min(560px, 80vw);
    text-align: left;
    animation: toast-in var(--dur) var(--ease-out);
  }
  .toast .msg {
    flex: 1;
    min-width: 0;
  }
  .toast .act {
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: var(--radius-full);
    border: 1px solid var(--accent);
    background: var(--accent-soft);
    color: var(--accent);
    cursor: pointer;
    white-space: nowrap;
  }
  .toast .act:hover {
    background: var(--accent);
    color: #04120d;
  }
  .toast .close {
    font: inherit;
    font-size: 11px;
    padding: 0 3px;
    border: none;
    background: transparent;
    color: var(--ink-faint);
    cursor: pointer;
  }
  .toast .close:hover {
    color: var(--ink);
  }
  .toast.err {
    border-color: var(--danger);
    color: var(--danger);
  }
  .toast.warn {
    border-color: var(--warn);
    color: var(--warn);
  }
  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translateY(6px);
    }
    to {
      opacity: 1;
      transform: none;
    }
  }
</style>
