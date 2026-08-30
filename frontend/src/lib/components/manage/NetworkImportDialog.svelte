<script lang="ts">
  import { untrack } from 'svelte';
  import { client, ApiError } from '$lib/api/client';
  import { librariesApi, type Library } from '$lib/api/libraries';
  import { adultNetworkApi, type AdultResolveResult } from '$lib/api/networkSources';
  import { settingsStore } from '$lib/stores/settings.svelte';

  let {
    open = $bindable(false),
    onsuccess
  }: {
    open: boolean;
    onsuccess?: () => void;
  } = $props();

  let libraries = $state<Library[]>([]);
  let url = $state('');
  let title = $state('');
  let libraryId = $state<string>('');
  let platform = $state('');
  let submitting = $state(false);
  let error = $state<string | null>(null);

  // ---- 成人聚合站解析（受 show_restricted + network_allow_adult 双门控） ----
  const showAdultResolve = $derived(settingsStore.showRestricted && settingsStore.allowAdultNetwork);
  let adultFancode = $state('');
  let adultResolving = $state(false);
  let adultResults = $state<AdultResolveResult[]>([]);
  let adultError = $state<string | null>(null);

  $effect(() => {
    if (open) {
      untrack(() => loadLibraries());
      url = ''; title = ''; libraryId = ''; platform = ''; error = null;
      adultFancode = ''; adultResults = []; adultError = null;
    }
  });

  async function loadLibraries() {
    try { libraries = await librariesApi.list(); } catch { /* ignore */ }
  }

  // Auto-detect platform from URL
  // F10 fix: only overwrite the field while it still holds the previous
  // auto-detect value (or is empty) — a manually typed platform is kept.
  let lastDetectedPlatform = '';
  $effect(() => {
    const lower = url.toLowerCase();
    let detected = '';
    if (lower.includes('youtube.com') || lower.includes('youtu.be')) detected = 'youtube';
    else if (lower.includes('bilibili.com') || lower.includes('b23.tv')) detected = 'bilibili';
    else if (lower.includes('vimeo.com')) detected = 'vimeo';
    if (platform === lastDetectedPlatform || platform === '') {
      platform = detected;
    }
    lastDetectedPlatform = detected;
  });

  // Auto-fill title from URL if empty
  $effect(() => {
    if (!title && url) {
      const path = url.split('?')[0].split('#')[0];
      const name = path.split('/').pop() || '';
      if (name && name.includes('.')) title = name.replace(/\.[^.]+$/, '');
    }
  });

  const canSubmit = $derived(url.trim().length > 0 && title.trim().length > 0 && libraryId && !submitting);

  // ---- 聚合站解析 ----
  async function resolveAdult(): Promise<void> {
    const code = adultFancode.trim();
    if (!code || adultResolving) return;
    adultResolving = true;
    adultError = null;
    adultResults = [];
    try {
      const res = await adultNetworkApi.resolve(code);
      if (res.status !== 'ok') {
        adultError = res.message || '未解析到可播放源';
      } else {
        adultResults = res.results;
      }
    } catch (e) {
      const status = (e as { status?: number })?.status;
      const detail = (e as { body?: { detail?: string } })?.body?.detail;
      if (status === 403) adultError = detail || '成人网络源功能未开启（设置 → 内容管理）';
      else if (detail) adultError = detail;
      else adultError = '解析失败，请检查后端服务';
    } finally {
      adultResolving = false;
    }
  }

  // 把解析出的直链填入下方表单，走正常导入流程
  function useAdultResult(r: AdultResolveResult): void {
    if (!r.m3u8_url) return;
    url = r.m3u8_url;
    if (!title) title = adultFancode.trim().toUpperCase();
    platform = r.server || '';
  }

  async function handleSubmit() {
    if (!canSubmit) return;
    submitting = true; error = null;
    try {
      await client.post('/media/import-network', {
        library_id: Number(libraryId),
        url: url.trim(),
        title: title.trim(),
        url_role: 'source',
        platform: platform.trim() || null,
      });
      open = false;
      onsuccess?.();
    } catch (e) {
      error = e instanceof ApiError ? (e.message || '导入失败') : '导入失败，请检查后端服务';
    } finally {
      submitting = false;
    }
  }
</script>

{#if open}
  <div class="modal-overlay" onclick={() => (open = false)}>
    <div class="modal-card" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h2>网络媒体导入</h2>
        <button class="close-btn" onclick={() => (open = false)}>✕</button>
      </div>
      <div class="modal-body">
        {#if error}<div class="error-banner">{error}</div>{/if}

        {#if showAdultResolve}
          <!-- 聚合站解析（成人内容，双门控显示） -->
          <div class="adult-section">
            <div class="adult-head">
              聚合站解析
              <span class="adult-badge">成人内容</span>
            </div>
            <div class="adult-row">
              <input
                type="text"
                bind:value={adultFancode}
                placeholder="输入番号，如 SNOS-334"
                disabled={adultResolving}
                onkeydown={(e) => { if (e.key === 'Enter') resolveAdult(); }}
              />
              <button class="btn-secondary" onclick={resolveAdult} disabled={adultResolving || !adultFancode.trim()}>
                {adultResolving ? '解析中…' : '解析'}
              </button>
            </div>
            {#if adultError}<div class="adult-error">{adultError}</div>{/if}
            {#if adultResults.length > 0}
              <div class="adult-results">
                {#each adultResults as r (r.server)}
                  <button class="adult-result" onclick={() => useAdultResult(r)} disabled={!r.m3u8_url} title={r.m3u8_url ? '填入下方表单' : r.error}>
                    <span class="adult-srv">{r.server}</span>
                    <span class="adult-url">{r.m3u8_url ?? (r.error || '解析失败')}</span>
                    {#if r.expires_in}<span class="adult-exp">有效 {Math.round(r.expires_in / 3600)}h</span>{/if}
                  </button>
                {/each}
              </div>
              <div class="form-hint">点击某条结果将自动填入下方 URL 表单，再选择目标库导入</div>
            {/if}
          </div>
          <hr class="adult-divider" />
        {/if}

        <div class="form-group">
          <label for="net-url">网络 URL *</label>
          <input id="net-url" type="url" bind:value={url} placeholder="https://example.com/video.mp4 或 .m3u8" disabled={submitting} />
          <div class="form-hint">支持直链视频 (mp4/webm)、HLS 流 (m3u8) 或平台链接</div>
        </div>
        <div class="form-group">
          <label for="net-title">标题 *</label>
          <input id="net-title" type="text" bind:value={title} placeholder="媒体标题" disabled={submitting} />
        </div>
        <div class="form-group">
          <label for="net-library">目标库 *</label>
          <select id="net-library" bind:value={libraryId} disabled={submitting}>
            <option value="">选择库…</option>
            {#each libraries as lib}<option value={lib.id}>{lib.name}</option>{/each}
          </select>
        </div>
        <div class="form-group">
          <label for="net-platform">平台 (可选)</label>
          <input id="net-platform" type="text" bind:value={platform} placeholder="自动检测或手动输入" disabled={submitting} />
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" onclick={() => (open = false)} disabled={submitting}>取消</button>
        <button class="btn-primary" onclick={handleSubmit} disabled={!canSubmit}>
          {submitting ? '导入中…' : '导入'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .modal-card { background: var(--bg-elevated, #1e1e2e); border: 1px solid var(--border, rgba(255,255,255,0.1)); border-radius: 12px; width: 520px; max-width: 90vw; max-height: 85vh; display: flex; flex-direction: column; }
  .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, rgba(255,255,255,0.1)); }
  .modal-header h2 { font-size: 16px; font-weight: 600; margin: 0; }
  .close-btn { background: none; border: none; color: var(--text-muted, #888); cursor: pointer; font-size: 18px; padding: 4px 8px; border-radius: 6px; }
  .close-btn:hover { background: rgba(255,255,255,0.1); }
  .modal-body { padding: 20px; overflow-y: auto; flex: 1; }
  .form-group { margin-bottom: 16px; }
  .form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 6px; }
  .form-group input, .form-group select { width: 100%; padding: 8px 12px; background: var(--bg-surface, #2a2a3a); border: 1px solid var(--border, rgba(255,255,255,0.1)); border-radius: 8px; color: var(--text, #fff); font-size: 14px; outline: none; box-sizing: border-box; }
  .form-group input:focus, .form-group select:focus { border-color: var(--accent, #7c3aed); }
  .form-hint { font-size: 12px; color: var(--text-muted, #888); margin-top: 4px; }
  .error-banner { background: rgba(239,68,68,0.15); color: #f87171; padding: 8px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 16px; }
  .adult-section { margin-bottom: 14px; }
  .adult-head { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; margin-bottom: 8px; }
  .adult-badge { font-size: 10.5px; color: #f87171; border: 1px solid rgba(239,68,68,0.4); border-radius: 999px; padding: 1px 8px; font-weight: 500; }
  .adult-row { display: flex; gap: 8px; }
  .adult-row input { flex: 1; }
  .adult-error { color: #f87171; font-size: 12.5px; margin-top: 8px; }
  .adult-results { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; max-height: 200px; overflow-y: auto; }
  .adult-result { display: flex; align-items: center; gap: 8px; padding: 7px 10px; background: var(--bg-surface, #2a2a3a); border: 1px solid var(--border, rgba(255,255,255,0.1)); border-radius: 8px; cursor: pointer; text-align: left; }
  .adult-result:hover:not(:disabled) { border-color: var(--accent, #7c3aed); }
  .adult-result:disabled { opacity: 0.55; cursor: default; }
  .adult-srv { font-size: 11px; font-weight: 600; color: var(--accent, #7c3aed); border: 1px solid var(--accent, #7c3aed); border-radius: 6px; padding: 1px 6px; flex-shrink: 0; }
  .adult-url { flex: 1; min-width: 0; font-size: 11.5px; color: var(--text-muted, #888); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .adult-exp { font-size: 10.5px; color: var(--text-muted, #888); flex-shrink: 0; }
  .adult-divider { border: none; border-top: 1px solid var(--border, rgba(255,255,255,0.1)); margin: 4px 0 16px; }
  .modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 16px 20px; border-top: 1px solid var(--border, rgba(255,255,255,0.1)); }
  .btn-primary, .btn-secondary { padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
  .btn-primary { background: var(--accent, #7c3aed); color: #fff; border: none; }
  .btn-primary:hover:not(:disabled) { background: var(--accent-hover, #6d28d9); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-secondary { background: transparent; color: var(--text-muted, #888); border: 1px solid var(--border, rgba(255,255,255,0.1)); }
  .btn-secondary:hover:not(:disabled) { background: rgba(255,255,255,0.05); }
</style>
