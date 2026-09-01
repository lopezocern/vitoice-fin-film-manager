<script lang="ts">
  /** 缺失文件找回：匹配「缺失记录 → 存活同名记录」影子重复对，
   *  合并用户数据到存活记录，旧记录移入回收站。 */
  import { untrack } from 'svelte';
  import { mediaApi, type ReconcilePair } from '$lib/api/media';
  import { librariesStore } from '$lib/stores/libraries.svelte';

  let { open = $bindable(false) }: { open?: boolean } = $props();

  let loading = $state(false);
  let loadError = $state<string | null>(null);
  let pairs = $state<ReconcilePair[]>([]);
  /** 每对是否执行合并（key = missing_id，默认全选） */
  let enabled = $state<Set<number>>(new Set());
  let executing = $state(false);
  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  function showToast(msg: string, type: 'ok' | 'err' = 'ok'): void {
    toast = { msg, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 3200);
  }

  function fmtSize(bytes: number | null): string {
    if (!bytes) return '—';
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
    if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    return `${Math.round(bytes / 1024)} KB`;
  }

  function fmtProgress(sec: number): string {
    if (!sec) return '无进度';
    return `${Math.round(sec / 60)} 分钟进度`;
  }

  async function load(): Promise<void> {
    loading = true;
    loadError = null;
    pairs = [];
    enabled = new Set();
    try {
      const res = await mediaApi.reconcilePreview();
      pairs = res.pairs;
      enabled = new Set(res.pairs.map((p) => p.missing_id));
    } catch (e) {
      loadError = e instanceof Error ? e.message : '扫描缺失文件失败';
    } finally {
      loading = false;
    }
  }

  function toggle(missingId: number): void {
    const s = new Set(enabled);
    if (s.has(missingId)) s.delete(missingId);
    else s.add(missingId);
    enabled = s;
  }

  const selectedCount = $derived(pairs.filter((p) => enabled.has(p.missing_id)).length);

  async function execute(): Promise<void> {
    const chosen = pairs.filter((p) => enabled.has(p.missing_id));
    if (chosen.length === 0 || executing) return;
    executing = true;
    try {
      const resp = await mediaApi.reconcileExecute(
        chosen.map((p) => ({ missing_id: p.missing_id, live_id: p.live_id }))
      );
      const fail = resp.failed.length;
      showToast(`已找回 ${resp.merged_count} 个文件${fail ? `，${fail} 个失败` : ''}`, fail ? 'err' : 'ok');
      librariesStore.notifyChanged();
      await load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : '找回失败', 'err');
    } finally {
      executing = false;
    }
  }

  function close(): void {
    if (executing) return;
    open = false;
    if (toastTimer) clearTimeout(toastTimer);
  }

  // 打开时自动扫描
  $effect(() => {
    if (open) untrack(() => void load());
  });
</script>

{#if open}
  <div class="backdrop" role="presentation" onclick={(e) => e.target === e.currentTarget && close()}>
    <div class="dialog" role="dialog" aria-modal="true" aria-label="找回缺失文件" tabindex="-1">
      <header class="head">
        <div>
          <h2>找回缺失文件</h2>
          <p>文件被移动后重新扫描会产生「缺失 + 新记录」并存。找到同名同大小的存活记录后，可将其找回：观看进度、标签等合并到新记录，旧记录移入回收站。</p>
        </div>
        <button class="icon-btn" aria-label="关闭" onclick={close}>×</button>
      </header>

      <div class="body">
        {#if loading}
          <div class="state">扫描缺失文件中…</div>
        {:else if loadError}
          <div class="state err">{loadError}</div>
        {:else if pairs.length === 0}
          <div class="state">没有可找回的缺失文件 — 所有缺失记录都没有匹配到同名文件</div>
        {:else}
          {#each pairs as p (p.missing_id)}
            <label class="item" class:on={enabled.has(p.missing_id)}>
              <input
                type="checkbox"
                checked={enabled.has(p.missing_id)}
                onchange={() => toggle(p.missing_id)}
              />
              <div class="item-main">
                <div class="item-name">
                  <span class="fname">{p.file_name}</span>
                  {#if p.size_matched}
                    <span class="conf high">大小匹配</span>
                  {:else}
                    <span class="conf low">仅同名</span>
                  {/if}
                </div>
                <div class="paths">
                  <div class="path old" title={p.missing_path ?? ''}>
                    <span class="tag">缺失</span>{p.missing_path}
                    <span class="prog">{fmtProgress(p.missing_progress)}</span>
                  </div>
                  <div class="path new" title={p.live_path ?? ''}>
                    <span class="tag">现位置</span>{p.live_path}
                    <span class="prog">{fmtProgress(p.live_progress)}{p.live_watched ? ' · 已看完' : ''}{p.live_tag_count ? ` · ${p.live_tag_count} 标签` : ''}</span>
                  </div>
                </div>
              </div>
            </label>
          {/each}
        {/if}
      </div>

      <footer class="foot">
        {#if toast}
          <span class="toast" class:err={toast.type === 'err'}>{toast.msg}</span>
        {/if}
        <span class="spacer"></span>
        <button class="btn" onclick={close}>关闭</button>
        <button class="btn primary" disabled={selectedCount === 0 || executing || loading} onclick={execute}>
          {executing ? '找回中…' : `找回（${selectedCount}）`}
        </button>
      </footer>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    z-index: 1500;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 24px;
    background: rgba(0, 0, 0, 0.5);
  }
  .dialog {
    width: min(820px, 100%);
    max-height: 84vh;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--rule);
    border-radius: 10px;
    background: var(--bg-elevated);
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35);
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 18px 20px 12px;
    border-bottom: 1px solid var(--rule);
  }
  .head h2 { margin: 0; font-size: 17px; }
  .head p { margin: 5px 0 0; color: var(--ink-tertiary); font-size: 12.5px; max-width: 640px; }
  .icon-btn {
    border: 0;
    background: transparent;
    color: var(--ink-faint);
    font-size: 18px;
    cursor: pointer;
  }
  .icon-btn:hover { color: var(--ink); }

  .body {
    flex: 1;
    min-height: 200px;
    overflow-y: auto;
    padding: 14px 20px;
  }
  .state { padding: 60px 0; text-align: center; color: var(--muted); font-size: 14px; }
  .state.err { color: var(--danger, #e26d78); }

  .item {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 10px 12px;
    border: 1px solid var(--rule);
    border-radius: 8px;
    margin-bottom: 8px;
    cursor: pointer;
    background: var(--bg);
  }
  .item.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 7%, var(--bg)); }
  .item-main { flex: 1; min-width: 0; }
  .item-name {
    font-size: 13.5px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .item-name .fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .conf {
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 650;
    border-radius: var(--radius-full, 999px);
    padding: 1px 8px;
  }
  .conf.high { color: var(--accent); border: 1px solid var(--accent); }
  .conf.low { color: var(--warn, #fbbf24); border: 1px solid var(--warn, #fbbf24); }

  .paths { margin-top: 6px; display: flex; flex-direction: column; gap: 3px; }
  .path {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--ink-tertiary);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .path .tag {
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 650;
    color: var(--ink-faint);
    border: 1px solid var(--rule);
    border-radius: 4px;
    padding: 0 5px;
  }
  .path.new .tag { color: var(--accent); border-color: var(--accent); }
  .path .prog { color: var(--ink-faint); flex-shrink: 0; margin-left: auto; padding-left: 12px; }

  .foot {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 20px;
    border-top: 1px solid var(--rule);
  }
  .toast { color: var(--accent); font-size: 12.5px; }
  .toast.err { color: var(--danger, #e26d78); }
  .spacer { flex: 1; }
  .btn {
    min-height: 34px;
    border: 1px solid var(--rule);
    border-radius: 6px;
    background: var(--bg);
    color: var(--ink);
    font: inherit;
    font-size: 13px;
    padding: 0 16px;
    cursor: pointer;
  }
  .btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
  .btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #061812;
    font-weight: 700;
  }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
