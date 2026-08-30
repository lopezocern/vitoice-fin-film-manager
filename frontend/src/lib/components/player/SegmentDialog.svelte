<script lang="ts">
  // 片段标记对话框：显示起止时间、命名、选色，确认后调用
  // POST /media/{mediaId}/segments { name, start_time, end_time, color }。
  import { formatTime } from '$lib/utils/format';
  import { client, ApiError } from '$lib/api/client';

  let {
    open = false,
    mediaId = '',
    startTime = 0,
    endTime = 0,
    onClose,
    onConfirm
  }: {
    open?: boolean;
    mediaId?: string;
    startTime?: number;
    endTime?: number;
    onClose?: () => void;
    onConfirm?: (seg: {
      id?: number;
      media_id?: number;
      name: string;
      start_time: number;
      end_time: number;
      color: string | null;
    }) => void;
  } = $props();

  const COLORS = [
    '#635bff', '#f59e0b', '#34c759', '#ff3b30',
    '#ff2d55', '#af52de', '#5ac8fa', '#8e8e93'
  ];

  let name = $state('');
  let color = $state<string | null>('#f59e0b');
  let saving = $state(false);
  let error = $state<string | null>(null);
  let nameInput = $state<HTMLInputElement | null>(null);

  const duration = $derived(Math.max(0, endTime - startTime));
  const valid = $derived(endTime > startTime && name.trim().length > 0);

  // 打开时重置表单并聚焦输入框
  $effect(() => {
    if (open) {
      name = `片段 ${formatTime(startTime)} - ${formatTime(endTime)}`;
      color = '#f59e0b';
      error = null;
      saving = false;
      // 等待 DOM 渲染后聚焦
      queueMicrotask(() => nameInput?.focus());
    }
  });

  async function confirm(): Promise<void> {
    if (!valid || saving) return;
    saving = true;
    error = null;
    try {
      const created = await client.post<{
        id?: number;
        media_id?: number;
        name: string;
        start_time: number;
        end_time: number;
        color: string | null;
      }>(`/media/${mediaId}/segments`, {
        name: name.trim(),
        start_time: startTime,
        end_time: endTime,
        color
      });
      onConfirm?.(created ?? {
        name: name.trim(),
        start_time: startTime,
        end_time: endTime,
        color
      });
      onClose?.();
    } catch (e) {
      if (e instanceof ApiError) {
        const detail =
          e.body && typeof e.body === 'object' && 'detail' in e.body
            ? String((e.body as any).detail)
            : `HTTP ${e.status}`;
        error = `保存片段失败：${detail}`;
      } else if (e instanceof Error) {
        error = `保存片段失败：${e.message}`;
      } else {
        error = '保存片段失败，请检查后端服务后重试';
      }
      console.error('[SegmentDialog] 保存片段失败:', e);
    } finally {
      saving = false;
    }
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose?.();
    } else if (e.key === 'Enter' && valid && !saving) {
      e.preventDefault();
      confirm();
    }
  }
</script>

<svelte:window onkeydown={open ? onKeydown : undefined} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="overlay" onclick={onClose} role="presentation">
    <!-- svelte-ignore a11y_interactive_supports_focus a11y_click_events_have_key_events -->
    <div
      class="dialog"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-label="标记片段"
    >
      <div class="head">
        <h3>标记片段</h3>
        <button class="x" onclick={onClose} aria-label="关闭">×</button>
      </div>

      <div class="times">
        <div class="time">
          <span class="lbl">开始</span>
          <span class="val">{formatTime(startTime)}</span>
        </div>
        <div class="arrow">→</div>
        <div class="time">
          <span class="lbl">结束</span>
          <span class="val">{formatTime(endTime)}</span>
        </div>
        <div class="dur">时长 {formatTime(duration)}</div>
      </div>

      <label class="field">
        <span class="lbl">名称</span>
        <input
          bind:this={nameInput}
          type="text"
          bind:value={name}
          placeholder="为这段内容命名"
          maxlength="120"
        />
      </label>

      <div class="field">
        <span class="lbl">颜色</span>
        <div class="colors">
          <button
            class="swatch none"
            class:active={color === null}
            onclick={() => (color = null)}
            title="无颜色"
            type="button"
          >∅</button>
          {#each COLORS as c}
            <button
              class="swatch"
              class:active={color === c}
              style={`background:${c}`}
              onclick={() => (color = c)}
              title={c}
              type="button"
              aria-label={`颜色 ${c}`}
            ></button>
          {/each}
        </div>
      </div>

      {#if error}
        <div class="error">{error}</div>
      {/if}

      <div class="actions">
        <button class="btn ghost" onclick={onClose} disabled={saving} type="button">取消</button>
        <button class="btn primary" onclick={confirm} disabled={!valid || saving} type="button">
          {saving ? '保存中…' : '保存片段'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    animation: fade 150ms ease;
  }
  @keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .dialog {
    width: min(440px, 92vw);
    background: var(--bg2);
    color: var(--ink);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
    padding: 18px 20px 16px;
    animation: pop 160ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  @keyframes pop {
    from { opacity: 0; transform: translateY(8px) scale(0.98); }
    to { opacity: 1; transform: none; }
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
  }
  .head h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 700;
  }
  .x {
    border: none;
    background: none;
    font-size: 20px;
    line-height: 1;
    color: var(--muted);
    width: 28px;
    height: 28px;
    border-radius: var(--radius);
    transition: background 150ms, color 150ms;
  }
  .x:hover {
    background: var(--bg-soft);
    color: var(--ink);
  }

  .times {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    background: var(--bg-soft);
    border-radius: var(--radius);
    margin-bottom: 14px;
  }
  .time {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .time .lbl,
  .field .lbl {
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .time .val {
    font-size: 16px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--ink);
  }
  .arrow {
    color: var(--muted);
    font-size: 14px;
  }
  .dur {
    margin-left: auto;
    font-size: 12px;
    color: var(--accent2);
    font-variant-numeric: tabular-nums;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 14px;
  }
  .field input {
    height: 36px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 150ms;
  }
  .field input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .colors {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .swatch {
    width: 26px;
    height: 26px;
    border-radius: var(--radius-full);
    border: 2px solid transparent;
    cursor: pointer;
    transition: transform 120ms, border-color 120ms;
    padding: 0;
  }
  .swatch:hover {
    transform: scale(1.12);
  }
  .swatch.active {
    border-color: var(--ink);
  }
  .swatch.none {
    background: var(--bg-soft);
    color: var(--muted);
    font-size: 13px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .error {
    color: #ff3b30;
    font-size: 12.5px;
    margin-bottom: 12px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  .btn {
    height: 34px;
    padding: 0 16px;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 500;
    transition: all 150ms;
  }
  .btn.ghost {
    background: var(--bg-soft);
    color: var(--ink);
    border: 1px solid var(--rule);
  }
  .btn.ghost:hover {
    background: var(--bg);
  }
  .btn.primary {
    background: var(--accent);
    color: #fff;
    border: none;
  }
  .btn.primary:hover:not(:disabled) {
    filter: brightness(1.06);
  }
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
