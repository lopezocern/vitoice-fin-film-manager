<script lang="ts">
  // SourceManager — unified scrape source chains (movie / tv / av).
  // Reads/writes the backend `scrape_sources` JSON setting. The av group
  // is visually flagged as adult content and only accepts html sources;
  // movie/tv groups only accept tmdb sources (backend-enforced too).
  import { onDestroy, onMount } from 'svelte';
  import { sourcesApi, type ScrapeSources, type ScrapeSourceItem } from '$lib/api/settingsSources';
  import { settingsStore } from '$lib/stores/settings.svelte';

  type Kind = 'movie' | 'tv' | 'av';

  // Adult-content isolation: when "显示限制内容" (show_restricted) is OFF,
  // the AV source group is hidden entirely — adult sources are not exposed
  // for configuration at all.
  const showRestricted = $derived(settingsStore.showRestricted);

  const KIND_META: Record<Kind, { label: string; hint: string; adult: boolean }> = {
    movie: { label: '电影数据源', hint: '使用默认源：TMDB（现有 API Key / Base URL 设置）', adult: false },
    tv: { label: '电视剧数据源', hint: '使用默认源：TMDB（现有 API Key / Base URL 设置）', adult: false },
    av: { label: '限制内容数据源', hint: '使用默认源：JavBus → JavDB → JavLibrary', adult: true },
  };

  const KIND_ORDER: Kind[] = ['movie', 'tv', 'av'];
  const PARSER_OPTIONS = [
    { value: '', label: '自动识别' },
    { value: 'javbus', label: 'JavBus 格式' },
    { value: 'javdb', label: 'JavDB 格式' },
    { value: 'javlibrary', label: 'JavLibrary 格式' },
  ];

  let sources = $state<ScrapeSources>({ movie: [], tv: [], av: [] });
  let loading = $state(true);
  let loadError = $state('');
  let dirty = $state(false);
  let saving = $state(false);
  let saveMsg = $state('');
  let testing = $state<Record<string, boolean>>({});
  let testResults = $state<Record<string, string>>({});

  // "已保存"提示的自动消失定时器：组件若在 2.5s 内卸载，回调仍会写已销毁的
  // $state。持句柄并在 onDestroy 清理，避免悬挂写入。
  let saveMsgTimer: ReturnType<typeof setTimeout> | null = null;

  onDestroy(() => {
    if (saveMsgTimer) clearTimeout(saveMsgTimer);
    saveMsgTimer = null;
  });

  function keyOf(kind: Kind, idx: number): string {
    return `${kind}-${idx}`;
  }

  async function load(): Promise<void> {
    loading = true;
    loadError = '';
    try {
      sources = await sourcesApi.get();
    } catch (e) {
      loadError = e instanceof Error ? e.message : '加载数据源失败';
    } finally {
      loading = false;
    }
  }

  async function save(): Promise<void> {
    saving = true;
    saveMsg = '';
    try {
      await sourcesApi.put(sources);
      dirty = false;
      saveMsg = '已保存';
      if (saveMsgTimer) clearTimeout(saveMsgTimer);
      saveMsgTimer = setTimeout(() => {
        saveMsg = '';
        saveMsgTimer = null;
      }, 2500);
    } catch (e) {
      const body = (e as { body?: { detail?: string } })?.body;
      saveMsg = typeof body?.detail === 'string' ? body.detail : '保存失败';
    } finally {
      saving = false;
    }
  }

  async function testSource(kind: Kind, idx: number): Promise<void> {
    const k = keyOf(kind, idx);
    const src = sources[kind][idx];
    if (!src?.base_url.trim()) {
      testResults[k] = '请先填写 base_url';
      return;
    }
    testing[k] = true;
    testResults[k] = '';
    try {
      const res = await sourcesApi.test(kind, src);
      testResults[k] = res.message;
    } catch (e) {
      const body = (e as { body?: { detail?: string } })?.body;
      testResults[k] = typeof body?.detail === 'string' ? body.detail : '测试失败';
    } finally {
      testing[k] = false;
    }
  }

  function addSource(kind: Kind, type: 'tmdb' | 'html'): void {
    const base: ScrapeSourceItem = {
      name: type === 'html' ? '新源' : 'TMDB 镜像',
      kind: type,
      base_url: '',
      image_base: type === 'tmdb' ? 'https://image.tmdb.org/t/p/w500' : undefined,
      api_key: type === 'tmdb' ? '' : undefined,
      language: type === 'tmdb' ? 'zh-CN' : undefined,
      timeout: 30,
      enabled: true,
      parser: type === 'html' ? '' : undefined,
    };
    sources[kind] = [...sources[kind], base];
    dirty = true;
  }

  function removeSource(kind: Kind, idx: number): void {
    sources[kind] = sources[kind].filter((_, i) => i !== idx);
    dirty = true;
  }

  function move(kind: Kind, idx: number, dir: -1 | 1): void {
    const arr = [...sources[kind]];
    const j = idx + dir;
    if (j < 0 || j >= arr.length) return;
    [arr[idx], arr[j]] = [arr[j], arr[idx]];
    sources[kind] = arr;
    dirty = true;
  }

  function patch(kind: Kind, idx: number, p: Partial<ScrapeSourceItem>): void {
    const arr = [...sources[kind]];
    arr[idx] = { ...arr[idx], ...p };
    sources[kind] = arr;
    dirty = true;
  }

  onMount(load);
</script>

<div class="source-manager">
  <div class="sm-head">
    <div class="sm-title">
      数据源管理
      <span class="sm-sub">按优先级回退，源失效自动切换下一个</span>
    </div>
    <button
      class="sm-save"
      class:accent={dirty}
      onclick={save}
      disabled={saving || !dirty}
      title={dirty ? '有未保存的修改' : '无变更'}
    >
      {saving ? '保存中…' : '保存数据源'}
    </button>
  </div>
  {#if saveMsg}
    <div class="sm-msg" class:err={saveMsg !== '已保存'}>{saveMsg}</div>
  {/if}

  {#if loading}
    <div class="sm-state">加载中…</div>
  {:else if loadError}
    <div class="sm-state err">{loadError}</div>
  {:else}
    {#each KIND_ORDER as kind (kind)}
      {@const meta = KIND_META[kind]}
      {#if !(meta.adult && !showRestricted)}
        <section class="sm-group" class:adult={meta.adult}>
          <header class="sm-group-head">
            <span class="sm-group-label">{meta.label}</span>
            {#if meta.adult}
              <span class="sm-badge">成人内容</span>
            {/if}
            <span class="sm-group-count">{sources[kind].length} 个自定义源</span>
          </header>

          {#if sources[kind].length === 0}
            <div class="sm-default-hint">{meta.hint}</div>
          {:else}
            <div class="sm-list">
              {#each sources[kind] as src, idx (keyOf(kind, idx))}
                <div class="sm-row">
                  <div class="sm-row-main">
                    <div class="sm-row-top">
                      <input
                        class="sm-input sm-name"
                        placeholder="源名称"
                        value={src.name ?? ''}
                        oninput={(e) => patch(kind, idx, { name: (e.target as HTMLInputElement).value })}
                      />
                      <span class="sm-kind" class:html={src.kind === 'html'}>{src.kind === 'html' ? 'HTML' : 'TMDB API'}</span>
                      {#if src.kind === 'html'}
                        <select
                          class="sm-select"
                          value={src.parser ?? ''}
                          onchange={(e) => patch(kind, idx, { parser: (e.target as HTMLSelectElement).value as ScrapeSourceItem['parser'] })}
                        >
                          {#each PARSER_OPTIONS as opt}
                            <option value={opt.value}>{opt.label}</option>
                          {/each}
                        </select>
                      {/if}
                    </div>
                    <div class="sm-row-fields">
                      <input
                        class="sm-input"
                        placeholder="base_url（必填）"
                        value={src.base_url ?? ''}
                        oninput={(e) => patch(kind, idx, { base_url: (e.target as HTMLInputElement).value })}
                      />
                      {#if src.kind === 'tmdb'}
                        <input
                          class="sm-input"
                          placeholder="image_base"
                          value={src.image_base ?? ''}
                          oninput={(e) => patch(kind, idx, { image_base: (e.target as HTMLInputElement).value })}
                        />
                        <input
                          class="sm-input"
                          type="password"
                          placeholder="api_key（留空继承全局）"
                          value={src.api_key ?? ''}
                          oninput={(e) => patch(kind, idx, { api_key: (e.target as HTMLInputElement).value })}
                        />
                        <input
                          class="sm-input sm-short"
                          placeholder="语言"
                          value={src.language ?? ''}
                          oninput={(e) => patch(kind, idx, { language: (e.target as HTMLInputElement).value })}
                        />
                      {/if}
                      <input
                        class="sm-input sm-short"
                        type="number"
                        min="5"
                        max="120"
                        placeholder="超时s"
                        value={src.timeout ?? 30}
                        oninput={(e) => patch(kind, idx, { timeout: Number((e.target as HTMLInputElement).value) || 30 })}
                      />
                    </div>
                    {#if testResults[keyOf(kind, idx)]}
                      <div class="sm-test-result">{testResults[keyOf(kind, idx)]}</div>
                    {/if}
                  </div>
                  <div class="sm-row-actions">
                    <button class="sm-btn" title="启用/停用" onclick={() => patch(kind, idx, { enabled: !src.enabled })}>
                      {src.enabled ? '✓' : '○'}
                    </button>
                    <button class="sm-btn" title="上移" onclick={() => move(kind, idx, -1)} disabled={idx === 0}>↑</button>
                    <button class="sm-btn" title="下移" onclick={() => move(kind, idx, 1)} disabled={idx === sources[kind].length - 1}>↓</button>
                    <button class="sm-btn" title="测试连通" onclick={() => testSource(kind, idx)} disabled={testing[keyOf(kind, idx)]}>
                      {testing[keyOf(kind, idx)] ? '…' : '测试'}
                    </button>
                    <button class="sm-btn danger" title="删除" onclick={() => removeSource(kind, idx)}>×</button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}

          <div class="sm-add">
            {#if kind === 'av'}
              <button class="sm-add-btn" onclick={() => addSource(kind, 'html')}>+ 添加源（成人站点）</button>
            {:else}
              <button class="sm-add-btn" onclick={() => addSource(kind, 'tmdb')}>+ 添加镜像/回退源</button>
            {/if}
          </div>
        </section>
      {/if}
    {/each}
  {/if}
</div>

<style>
  .source-manager {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 4px 0 14px;
    border-bottom: 1px solid var(--rule);
    margin-bottom: 14px;
  }
  .sm-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .sm-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--ink);
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .sm-sub {
    font-size: 11.5px;
    font-weight: 400;
    color: var(--ink-tertiary);
  }
  .sm-save {
    padding: 4px 14px;
    border: 1px solid var(--rule);
    border-radius: var(--radius-xs);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    font-size: 12px;
    cursor: pointer;
  }
  .sm-save.accent {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }
  .sm-save:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .sm-msg {
    font-size: 12px;
    color: var(--success, #2e8b57);
  }
  .sm-msg.err {
    color: var(--danger, #c0392b);
  }
  .sm-state {
    font-size: 12.5px;
    color: var(--ink-tertiary);
    padding: 12px 0;
  }
  .sm-state.err {
    color: var(--danger, #c0392b);
  }
  .sm-group {
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .sm-group.adult {
    border-color: color-mix(in srgb, var(--accent) 45%, var(--rule));
  }
  .sm-group-head {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .sm-group-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--ink);
  }
  .sm-badge {
    font-size: 10.5px;
    color: var(--danger, #c0392b);
    border: 1px solid var(--danger, #c0392b);
    border-radius: var(--radius-full, 999px);
    padding: 1px 8px;
    opacity: 0.85;
  }
  .sm-group-count {
    font-size: 11px;
    color: var(--ink-tertiary);
    margin-left: auto;
  }
  .sm-default-hint {
    font-size: 12px;
    color: var(--ink-tertiary);
    background: var(--bg-hover);
    border-radius: var(--radius-xs);
    padding: 8px 10px;
  }
  .sm-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .sm-row {
    display: flex;
    gap: 8px;
    align-items: flex-start;
    background: var(--bg-surface);
    border: 1px solid var(--rule);
    border-radius: var(--radius-xs);
    padding: 8px 10px;
  }
  .sm-row-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .sm-row-top {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .sm-row-fields {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .sm-input {
    flex: 1;
    min-width: 110px;
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 12px;
    padding: 4px 8px;
    border-radius: var(--radius-xs);
    outline: none;
    box-sizing: border-box;
  }
  .sm-input:focus {
    box-shadow: 0 0 0 2px var(--accent-soft);
  }
  .sm-input.sm-name {
    max-width: 180px;
    flex: 0 0 auto;
    font-weight: 500;
  }
  .sm-input.sm-short {
    max-width: 110px;
    flex: 0 0 auto;
  }
  .sm-select {
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink);
    font-size: 12px;
    padding: 4px 6px;
    border-radius: var(--radius-xs);
    outline: none;
  }
  .sm-kind {
    font-size: 10.5px;
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: var(--radius-full, 999px);
    padding: 1px 8px;
    flex-shrink: 0;
  }
  .sm-kind.html {
    color: var(--danger, #c0392b);
    border-color: var(--danger, #c0392b);
  }
  .sm-test-result {
    font-size: 11.5px;
    color: var(--ink-secondary);
  }
  .sm-row-actions {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex-shrink: 0;
  }
  .sm-btn {
    width: 26px;
    height: 22px;
    border: 1px solid var(--rule);
    border-radius: var(--radius-xs);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    font-size: 12px;
    line-height: 1;
    cursor: pointer;
    padding: 0;
  }
  .sm-btn:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }
  .sm-btn.danger:hover {
    color: var(--danger, #c0392b);
    border-color: var(--danger, #c0392b);
  }
  .sm-btn:disabled {
    opacity: 0.35;
    cursor: default;
  }
  .sm-add-btn {
    align-self: flex-start;
    padding: 4px 12px;
    border: 1px dashed var(--rule);
    border-radius: var(--radius-xs);
    background: none;
    color: var(--ink-tertiary);
    font-size: 12px;
    cursor: pointer;
  }
  .sm-add-btn:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
</style>
