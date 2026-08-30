<script lang="ts">
  // 确认对话框：标题 + 描述 + 确认/取消按钮
  // 确认按钮可设为危险样式（红色，用于删除等破坏性操作）
  // 通过 bind:open 控制显示，onconfirm / oncancel 回调

  let {
    open = $bindable(false),
    title = '确认操作',
    description = '',
    confirmText = '确认',
    cancelText = '取消',
    danger = false,
    disableConfirm = false,
    extraButtonText = '',
    onconfirm,
    oncancel,
    onextra
  }: {
    open?: boolean;
    title?: string;
    description?: string;
    confirmText?: string;
    cancelText?: string;
    danger?: boolean;
    disableConfirm?: boolean;
    /** 可选第三按钮（显示在取消按钮左侧，用于"二次确认时提供另一操作"等场景） */
    extraButtonText?: string;
    onconfirm?: () => void;
    oncancel?: () => void;
    onextra?: () => void;
  } = $props();

  function handleConfirm(): void {
    if (disableConfirm) return;
    open = false;
    onconfirm?.();
  }

  function handleCancel(): void {
    open = false;
    oncancel?.();
  }

  function handleBackdrop(e: MouseEvent): void {
    if (e.target === e.currentTarget) {
      handleCancel();
    }
  }

  function handleKeydown(e: KeyboardEvent): void {
    if (!open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    } else if (e.key === 'Enter' && !disableConfirm) {
      e.preventDefault();
      handleConfirm();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
  <div class="backdrop" onclick={handleBackdrop} onkeydown={(e) => { if (e.key === 'Escape') handleCancel(); }} role="presentation">
    <div
      class="dialog"
      class:danger
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
    >
      <div class="dialog-head">
        <div class="icon-wrap" class:danger aria-hidden="true">
          {#if danger}
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path d="M12 2L1 21h22L12 2zm0 6l7.53 13H4.47L12 8zm-1 4v4h2v-4h-2zm0 5v2h2v-2h-2z" fill="currentColor" />
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" fill="currentColor" />
            </svg>
          {/if}
        </div>
        <h2 id="confirm-title">{title}</h2>
      </div>
      {#if description}
        <div class="dialog-body">{description}</div>
      {/if}
      <div class="dialog-foot">
        {#if extraButtonText && onextra}
          <button class="btn btn-extra" onclick={() => { open = false; onextra(); }}>{extraButtonText}</button>
        {/if}
        <button class="btn btn-cancel" onclick={handleCancel}>{cancelText}</button>
        <button
          class="btn"
          class:btn-danger={danger}
          class:btn-primary={!danger}
          disabled={disableConfirm}
          onclick={handleConfirm}
        >
          {confirmText}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.32);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fade 200ms ease;
  }

  @keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .dialog {
    width: 100%;
    max-width: 420px;
    background: var(--bg2);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
    overflow: hidden;
    animation: pop 200ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }

  @keyframes pop {
    from { opacity: 0; transform: translateY(-8px) scale(0.96); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .dialog-head {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 20px 24px 0;
  }

  .icon-wrap {
    width: 36px;
    height: 36px;
    flex-shrink: 0;
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--accent-soft);
    color: var(--accent);
  }

  .icon-wrap.danger {
    background: var(--accent2-soft);
    color: var(--accent2);
  }

  .dialog-head h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
  }

  .dialog-body {
    padding: 10px 24px 20px 24px;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.6;
    white-space: pre-wrap;
  }

  .dialog-foot {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 12px 24px 20px;
  }

  .btn {
    height: 34px;
    padding: 0 16px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
  }

  .btn:hover {
    border-color: var(--muted);
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-cancel {
    background: var(--bg-soft);
  }

  .btn-extra {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
    margin-right: auto;
  }

  .btn-extra:hover:not(:disabled) {
    background: var(--accent);
    color: #fff;
  }

  .btn-cancel:hover {
    background: var(--bg2);
  }

  .btn-primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .btn-primary:hover:not(:disabled) {
    filter: brightness(1.08);
    border-color: var(--accent);
  }

  .btn-danger {
    background: #ff3b30;
    border-color: #ff3b30;
    color: #fff;
  }

  .btn-danger:hover:not(:disabled) {
    filter: brightness(1.08);
  }
</style>
