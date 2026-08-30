<script lang="ts">
  /** 重复文件检测向导：查重 → 组内勾选保留 → 其余批量移入回收站 */
  import { client } from '$lib/api/client';
  import { librariesStore } from '$lib/stores/libraries.svelte';

  interface DupItem {
    id: number;
    title: string | null;
    file_name: string | null;
    file_path: string | null;
    library_id: number;
    library_name: string | null;
    file_size: number | null;
    duration: number | null;
    has_poster: boolean;
    created_at: string | null;
  }
  interface DupGroup {
    key: string;
    items: DupItem[];
  }

  let { open = $bindable(false) }: { open?: boolean } = $props();
  let mode = $state<'hash' | 'name' | 'size'>('hash');
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  let groups = $state<DupGroup[]>([]);
  /** 每组保留的媒体 id（key=组 key） */
  let keepMap = $state<Map<string, number>>(new Map());
  let cleaning = $state(false);
  let toast = $state<{ msg: string; type: 'ok' | 'err' } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;

  const MODE_INFO: Record<string, { label: string; hint: string }> = {
    hash: { label: '内容哈希', hint: '同一 64KB 前缀哈希 = 高置信重复，可放心清理' },
    name: { label: '同名文件', hint: '文件名相同但内容可能不同（如不同清晰度），请逐组确认' },
    size: { label: '同大小', hint: '大于 10MB 且字节数完全一致，中等置信度' },
  };

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

  async function load(): Promise<void> {
    loading = true;
    loadError = null;
    groups = [];
    keepMap = new Map();
    try {
      const res = await client.get<{ mode: string; groups: DupGroup[]; truncated: boolean }>(
        '/duplicates',
        { mode }
      );
      groups = res.groups;
      // 默认每组保留最大文件（后端已按 size desc 排序 → 第一项）
      const m = new Map<string, number>();
      for (const g of groups) {
        if (g.items.length > 0) m.set(g.key, g.items[0].id);
      }
      keepMap = m;
    } catch (e) {
      loadError = e instanceof Error ? e.message : '查重请求失败';
    } finally {
      loading = false;
    }
  }

  function keep(key: string, id: number): void {
    const m = new Map(keepMap);
    m.set(key, id);
    keepMap = m;
  }

  const toRemoveIds = $derived(
    groups.flatMap((g) => g.items.filter((i) => keepMap.get(g.key) !== i.id).map((i) => i.id))
  );

  async function cleanUp(): Promise<void> {
    const ids = toRemoveIds;
    if (ids.length === 0 || cleaning) return;
    cleaning = true;
    try {
      const resp = await client.post<{ success_count: number; failed: { id: number }[] }>(
        '/media/batch',
        { action: 'delete', media_ids: ids, params: { permanent: false } }
      );
      const fail = resp.failed.length;
      showToast(`已移入回收站 ${resp.success_count} 项${fail ? `，${fail} 项失败` : ''}`, fail ? 'err' : 'ok');
      librariesStore.notifyChanged();
      await load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : '清理失败', 'err');
    } finally {
      cleaning = false;
    }
  }

  function close(): void {
    if (cleaning) return;
    open = false;
    if (toastTimer) clearTimeout(toastTimer);
  }
</script>

{#if open}
  <div class="backdrop" role="presentation" onclick={(e) => e.target === e.currentTarget && close()}>
    <div class="dialog" role="dialog" aria-modal="true" aria-label="重复文件检测" tabindex="-1">
      <header class="head">
        <div>
          <h2>重复文件检测</h2>
          <p>{MODE_INFO[mode].hint}</p>
        </div>
        <button class="icon-btn" aria-label="关闭" onclick={close}>×</button>
      </header>

      <div class="mode-row" role="tablist" aria-label="查重模式">
        {#each Object.entries(MODE_INFO) as [m, info] (m)}
          <button
            class="mode-tab"
            class:active={mode === m}
            role="tab"
            aria-selected={mode === m}
            onclick={() => { mode = m as 'hash' | 'name' | 'size'; void load(); }}
          >{info.label}</button>
        {/each}
        <span class="spacer"></span>
        {#if groups.length > 0}
          <span class="count">{groups.length} 组重复，{toRemoveIds.length} 项待清理</span>
        {/if}
      </div>

      <div class="body">
        {#if loading}
          <div class="state">查重中…</div>
        {:else if loadError}
          <div class="state err">{loadError}</div>
        {:else if groups.length === 0}
          <div class="state">🎉 没有发现重复文件</div>
        {:else}
          {#each groups as g (g.key)}
            <section class="group">
              <div class="group-head">
                <span class="group-key" title={g.key}>{mode === 'hash' ? `哈希 ${g.key.slice(0, 12)}…` : g.key}</span>
                <span class="group-count">{g.items.length} 项</span>
              </div>
              {#each g.items as it (it.id)}
                <label class="item" class:keep={keepMap.get(g.key) === it.id}>
                  <input
                    type="radio"
                    name={`keep-${g.key}`}
                    checked={keepMap.get(g.key) === it.id}
                    onchange={() => keep(g.key, it.id)}
                  />
                  <div class="item-main">
                    <div class="item-name">{it.file_name}</div>
                    <div class="item-meta">
                      <span class="lib">{it.library_name ?? '未知库'}</span>
                      <span>{fmtSize(it.file_size)}</span>
                      {#if it.duration}<span>{Math.round(it.duration / 60)} 分钟</span>{/if}
                      <span class="path" title={it.file_path ?? ''}>{it.file_path}</span>
                    </div>
                  </div>
                  <span class="keep-tag">{keepMap.get(g.key) === it.id ? '保留' : '清理'}</span>
                </label>
              {/each}
            </section>
          {/each}
        {/if}
      </div>

      <footer class="foot">
        {#if toast}
          <span class="toast" class:err={toast.type === 'err'}>{toast.msg}</span>
        {/if}
        <span class="spacer"></span>
        <button class="btn" onclick={close}>关闭</button>
        <button class="btn primary" disabled={toRemoveIds.length === 0 || cleaning || loading} onclick={cleanUp}>
          {cleaning ? '清理中…' : `移入回收站（${toRemoveIds.length}）`}
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
    width: min(760px, 100%);
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
  .head p { margin: 5px 0 0; color: var(--ink-tertiary); font-size: 12.5px; }
  .icon-btn {
    border: 0;
    background: transparent;
    color: var(--ink-faint);
    font-size: 18px;
    cursor: pointer;
  }
  .icon-btn:hover { color: var(--ink); }

  .mode-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 20px;
    border-bottom: 1px solid var(--rule);
  }
  .mode-tab {
    border: 1px solid var(--rule);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--ink-secondary);
    font: inherit;
    font-size: 12.5px;
    padding: 5px 14px;
    cursor: pointer;
  }
  .mode-tab.active {
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 650;
  }
  .spacer { flex: 1; }
  .count { color: var(--ink-tertiary); font-size: 12.5px; }

  .body {
    flex: 1;
    min-height: 200px;
    overflow-y: auto;
    padding: 14px 20px;
  }
  .state { padding: 60px 0; text-align: center; color: var(--muted); font-size: 14px; }
  .state.err { color: var(--danger, #e26d78); }

  .group { margin-bottom: 18px; }
  .group-head {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
  }
  .group-key { font-weight: 650; font-size: 13px; }
  .group-count { color: var(--ink-tertiary); font-size: 12px; }

  .item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 9px 12px;
    border: 1px solid var(--rule);
    border-radius: 8px;
    margin-bottom: 6px;
    cursor: pointer;
    background: var(--bg);
  }
  .item.keep { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 7%, var(--bg)); }
  .item-main { flex: 1; min-width: 0; }
  .item-name { font-size: 13.5px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .item-meta {
    display: flex;
    gap: 12px;
    margin-top: 3px;
    color: var(--ink-tertiary);
    font-size: 12px;
    overflow: hidden;
  }
  .item-meta .lib { color: var(--accent); }
  .item-meta .path { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .keep-tag { font-size: 12px; font-weight: 650; color: var(--ink-faint); flex-shrink: 0; }
  .item.keep .keep-tag { color: var(--accent); }

  .foot {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 20px;
    border-top: 1px solid var(--rule);
  }
  .toast { color: var(--accent); font-size: 12.5px; }
  .toast.err { color: var(--danger, #e26d78); }
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
