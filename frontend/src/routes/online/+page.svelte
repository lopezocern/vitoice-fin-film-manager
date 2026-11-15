<script lang="ts">
  /**
   * 在线 — 自定义源聚合搜索 + 在线播放。
   *
   * 数据流：输入关键词 → 并发查所有启用源（后端 `/sources/search`）→
   * 按「标题 + 年份」合并同名结果 → 选一个源解析线路 → 在线播放或入库。
   *
   * 为什么不做成"直接播放"：采集站给的地址可能是 m3u8 直链，也可能是需要
   * 二次解析的原站页面。两种情况都要让用户看见并可选（`direct` 标记）。
   */
  import { onMount, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import {
    onlineSourcesApi,
    type AggregatedResult,
    type OnlinePlayGroup,
    type OnlineSource,
    type OnlineSourceInput,
    type SourceSearchReport
  } from '$lib/api/mediaSources';
  import { client } from '$lib/api/client';
  import { errorMessage } from '$lib/utils/errors';
  import { toasts } from '$lib/stores/toast.svelte';
  import { librariesStore } from '$lib/stores/libraries.svelte';
  import { liveQueryParam } from '$lib/stores/urlState.svelte';
  import ToastHost from '$lib/components/common/ToastHost.svelte';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

  let keyword = $state('');
  let searching = $state(false);
  let results = $state<AggregatedResult[]>([]);
  let sources = $state<SourceSearchReport[]>([]);
  let skipped = $state<string[]>([]);
  let searched = $state(false);

  // 已配置源 + 源管理面板
  let configs = $state<OnlineSource[]>([]);
  let showManage = $state(false);
  let draft = $state<OnlineSourceInput>({ name: '', base_url: '' });
  let testing = $state(false);
  let saving = $state(false);
  // 删除确认：id 与开关分开，ConfirmDialog 的 open 是 boolean
  let removeId = $state<string | null>(null);
  let removeOpen = $state(false);

  // 当前展开的结果与解析出的线路
  let activeKey = $state<string | null>(null);
  let resolving = $state<string | null>(null);
  let groups = $state<OnlinePlayGroup[]>([]);
  let activeGroup = $state(0);
  let resolvedTitle = $state('');

  // 播放层
  let playing = $state<{ title: string; url: string; direct: boolean } | null>(null);
  let videoEl = $state<HTMLVideoElement | null>(null);
  let hlsRef: { destroy: () => void } | null = null;
  let importing = $state(false);
  let importLibraryId = $state('');

  const enabledCount = $derived(configs.filter((s) => s.enabled).length);
  const currentGroup = $derived(groups[activeGroup] ?? null);

  onMount(() => {
    untrack(() => {
      // 深链：/online?q=沙丘 直接带结果进来（也便于分享）
      const q = liveQueryParam('q');
      if (q) keyword = q;
      void loadConfigs();
      void librariesStore.ensureLoaded?.();
      if (q) void doSearch();
    });
  });

  async function loadConfigs(): Promise<void> {
    try {
      configs = await onlineSourcesApi.list();
      const first = configs.find((s) => s.enabled);
      importLibraryId ||= String(librariesStore.libraries[0]?.id ?? '');
      if (!first && configs.length === 0) showManage = true;
    } catch (e) {
      toasts.push(errorMessage(e, '读取源配置失败'), 'err');
    }
  }

  async function doSearch(): Promise<void> {
    const q = keyword.trim();
    if (!q || searching) return;
    searching = true;
    activeKey = null;
    groups = [];
    try {
      const res = await onlineSourcesApi.search(q);
      results = res.items;
      sources = res.sources;
      skipped = res.skipped_sources;
      searched = true;
      if (res.total === 0) toasts.push('没有搜到结果，试试更短的关键词或补充源');
    } catch (e) {
      toasts.push(errorMessage(e, '搜索失败'), 'err');
    } finally {
      searching = false;
    }
  }

  function toggleResult(item: AggregatedResult): void {
    if (activeKey === item.key) {
      activeKey = null;
      groups = [];
      return;
    }
    activeKey = item.key;
    groups = [];
    resolvedTitle = item.title;
    const first = item.offers[0];
    if (first) void resolve(first.source_id, first.vod_id);
  }

  async function resolve(sourceId: string, vodId: string): Promise<void> {
    resolving = `${sourceId}:${vodId}`;
    groups = [];
    activeGroup = 0;
    try {
      const res = await onlineSourcesApi.resolve(sourceId, vodId);
      groups = res.groups;
      resolvedTitle = res.title;
      if (res.groups.length === 0) toasts.push('该源没有返回可播放的地址', 'err');
    } catch (e) {
      toasts.push(errorMessage(e, '解析失败'), 'err');
    } finally {
      resolving = null;
    }
  }

  async function play(ep: { name: string; url: string; direct: boolean }): Promise<void> {
    if (!ep.direct) {
      // 非直链：交给系统浏览器打开原站页面，避免把解析逻辑硬编码进来
      window.open(ep.url, '_blank', 'noopener');
      return;
    }
    playing = { title: `${resolvedTitle} · ${ep.name}`, url: ep.url, direct: true };
    await Promise.resolve();
    void attachStream();
  }

  /** 挂载 hls.js（npm 依赖，不走 CDN，离线可用）。 */
  async function attachStream(): Promise<void> {
    const el = videoEl;
    if (!el || !playing) return;
    hlsRef?.destroy();
    hlsRef = null;
    el.src = '';
    const url = playing.url;
    const isHls = /\.m3u8(\?|$)/i.test(url);
    if (!isHls) {
      el.src = url;
      return;
    }
    const { default: Hls } = await import('hls.js');
    if (Hls.isSupported()) {
      const hls = new Hls({ maxBufferLength: 30 });
      hls.loadSource(url);
      hls.attachMedia(el);
      hls.on(Hls.Events.ERROR, (_evt, data) => {
        if (data.fatal) toasts.push(`播放中断：${data.details}`, 'err');
      });
      hlsRef = hls;
    } else if (el.canPlayType('application/vnd.apple.mpegurl')) {
      el.src = url;
    } else {
      toasts.push('当前环境不支持 HLS 播放', 'err');
    }
  }

  function closePlayer(): void {
    hlsRef?.destroy();
    hlsRef = null;
    playing = null;
  }

  async function importToLibrary(): Promise<void> {
    if (!playing || importing) return;
    const libId = Number(importLibraryId);
    if (!libId) {
      toasts.push('请先选择要入库的资源库', 'err');
      return;
    }
    importing = true;
    try {
      await client.post('/media/import-network', {
        library_id: libId,
        url: playing.url,
        title: playing.title
      });
      toasts.push('已入库为网络媒体');
      librariesStore.notifyChanged?.();
    } catch (e) {
      toasts.push(errorMessage(e, '入库失败'), 'err');
    } finally {
      importing = false;
    }
  }

  async function saveDraft(): Promise<void> {
    if (saving) return;
    if (!draft.name.trim() || !draft.base_url.trim()) {
      toasts.push('名称和接口地址都要填', 'err');
      return;
    }
    saving = true;
    try {
      const next: OnlineSourceInput[] = [
        ...configs.map((s) => ({
          id: s.id,
          name: s.name,
          base_url: s.base_url,
          kind: s.kind,
          api_path: s.api_path,
          enabled: s.enabled,
          timeout: s.timeout,
          headers: s.headers
        })),
        draft
      ];
      await onlineSourcesApi.save(next);
      draft = { name: '', base_url: '' };
      await loadConfigs();
      toasts.push('已保存');
    } catch (e) {
      toasts.push(errorMessage(e, '保存失败'), 'err');
    } finally {
      saving = false;
    }
  }

  async function probe(source: OnlineSource): Promise<void> {
    testing = true;
    try {
      const res = await onlineSourcesApi.test({ id: source.id });
      toasts.push(
        res.ok ? `「${source.name}」可用 · ${res.latency_ms}ms` : `「${source.name}」不可用：${res.message}`,
        res.ok ? 'ok' : 'err'
      );
      await loadConfigs();
    } catch (e) {
      toasts.push(errorMessage(e, '探活失败'), 'err');
    } finally {
      testing = false;
    }
  }

  async function toggleEnabled(source: OnlineSource): Promise<void> {
    try {
      await onlineSourcesApi.save(
        configs.map((s) => ({
          id: s.id,
          name: s.name,
          base_url: s.base_url,
          kind: s.kind,
          api_path: s.api_path,
          enabled: s.id === source.id ? !s.enabled : s.enabled,
          timeout: s.timeout,
          headers: s.headers
        }))
      );
      await loadConfigs();
    } catch (e) {
      toasts.push(errorMessage(e, '切换失败'), 'err');
    }
  }

  async function removeSource(id: string): Promise<void> {
    try {
      await onlineSourcesApi.save(
        configs
          .filter((s) => s.id !== id)
          .map((s) => ({
            id: s.id,
            name: s.name,
            base_url: s.base_url,
            kind: s.kind,
            api_path: s.api_path,
            enabled: s.enabled,
            timeout: s.timeout,
            headers: s.headers
          }))
      );
      await loadConfigs();
      toasts.push('已删除');
    } catch (e) {
      toasts.push(errorMessage(e, '删除失败'), 'err');
    }
  }

  function healthTone(available: boolean, failStreak: number): string {
    if (!available) return 'bad';
    if (failStreak > 0) return 'warn';
    return 'ok';
  }
</script>

<div class="online">
  <header class="head">
    <div>
      <div class="eyebrow">在线</div>
      <h1>在线片库</h1>
      <p>聚合你配置的采集站接口，一个关键词搜全部源；同名结果合并，可直接播放或入库。</p>
    </div>
    <div class="head-actions">
      <button type="button" class="btn" onclick={() => (showManage = !showManage)}>
        源管理 · {enabledCount}/{configs.length}
      </button>
      <button type="button" class="btn" onclick={() => goto('/manage')}>回管理页</button>
    </div>
  </header>

  <form
    class="searchbar"
    onsubmit={(e) => {
      e.preventDefault();
      void doSearch();
    }}
  >
    <input
      type="search"
      bind:value={keyword}
      placeholder="片名 / 番号 / 剧名…"
      aria-label="搜索在线片库"
      autocomplete="off"
    />
    <button type="submit" disabled={searching || !keyword.trim()}>
      {searching ? '搜索中…' : '搜索'}
    </button>
  </form>

  {#if sources.length > 0 || skipped.length > 0}
    <div class="source-strip">
      {#each sources as s (s.source_id)}
        <span class="chip" class:bad={!s.available} class:ok={s.available && s.fail_streak === 0} class:warn={s.available && s.fail_streak > 0}>
          {s.source_id}
          {#if s.available && s.latency_ms != null}<em>{s.latency_ms}ms</em>{/if}
          {#if !s.available}<em>已熔断</em>{/if}
        </span>
      {/each}
      {#each skipped as id (id)}
        <span class="chip bad">{id} <em>跳过</em></span>
      {/each}
    </div>
  {/if}

  {#if showManage}
    <section class="manage">
      <h2>源管理</h2>
      <p class="hint">
        支持苹果 CMS v10 点播接口（<code>base_url</code> + <code>api.php/provide/vod</code>）。
        连续失败的源会自动熔断（30 分钟 → 24 小时 → 7 天），探活成功即恢复。
      </p>

      <div class="add-row">
        <input bind:value={draft.name} placeholder="源名称（如 高清采集）" aria-label="源名称" />
        <input
          bind:value={draft.base_url}
          placeholder="https://example.com"
          aria-label="源接口地址"
        />
        <button type="button" class="btn primary" disabled={saving} onclick={() => void saveDraft()}>
          {saving ? '保存中…' : '添加'}
        </button>
      </div>

      <div class="src-list">
        {#each configs as src (src.id)}
          <div class="src-row">
            <span class="dot" class:bad={src.health && !src.health.available} class:ok={!src.health || src.health.available}></span>
            <div class="src-main">
              <strong>{src.name}</strong>
              <span class="src-url" title={`${src.base_url}/${src.api_path}`}>{src.base_url}</span>
            </div>
            <span class="chip" class:bad={src.health ? !src.health.available : false} class:warn={src.health ? src.health.available && src.health.fail_streak > 0 : false}>
              {#if !src.health}
                未测试
              {:else if !src.health.available}
                熔断中
              {:else}
                {src.health.latency_ms ?? 0}ms
              {/if}
            </span>
            <button type="button" class="mini" disabled={testing} onclick={() => void probe(src)}>探活</button>
            <button type="button" class="mini" onclick={() => void toggleEnabled(src)}>
              {src.enabled ? '停用' : '启用'}
            </button>
            <button
              type="button"
              class="mini danger"
              onclick={() => {
                removeId = src.id;
                removeOpen = true;
              }}
            >
              删除
            </button>
          </div>
        {/each}
        {#if configs.length === 0}
          <p class="empty">还没有源。添加一个采集站接口就能开始搜索。</p>
        {/if}
      </div>
    </section>
  {/if}

  {#if searched && results.length === 0 && !searching}
    <div class="state">没有匹配的结果。可以换个关键词，或在源管理里补充更多源。</div>
  {/if}

  <div class="results">
    {#each results as item (item.key)}
      <article class="card" class:active={activeKey === item.key}>
        <button type="button" class="card-main" onclick={() => toggleResult(item)}>
          <div class="poster">
            {#if item.poster}
              <img src={item.poster} alt="" loading="lazy" />
            {:else}
              <span class="poster-empty">无封面</span>
            {/if}
          </div>
          <div class="meta">
            <div class="title" title={item.title}>{item.title}</div>
            <div class="sub">
              {#if item.year}<span>{item.year}</span>{/if}
              <span>{item.source_count} 个源 · {item.offers.length} 条线路</span>
            </div>
          </div>
        </button>

        {#if activeKey === item.key}
          <div class="offers">
            <div class="offer-row">
              {#each item.offers as offer (offer.source_id + offer.vod_id)}
                <button
                  type="button"
                  class="offer"
                  disabled={resolving !== null}
                  onclick={() => void resolve(offer.source_id, offer.vod_id)}
                >
                  {offer.source_id}
                  {#if offer.remarks}<em>{offer.remarks}</em>{/if}
                  {#if resolving === `${offer.source_id}:${offer.vod_id}`}<em>解析中…</em>{/if}
                </button>
              {/each}
            </div>

            {#if groups.length > 1}
              <div class="line-tabs">
                {#each groups as g, i (g.flag)}
                  <button type="button" class="line" class:on={activeGroup === i} onclick={() => (activeGroup = i)}>
                    {g.flag}（{g.episodes.length}）
                  </button>
                {/each}
              </div>
            {/if}

            {#if currentGroup}
              <div class="episodes">
                {#each currentGroup.episodes as ep, i (i)}
                  <button type="button" class="ep" class:page={!ep.direct} onclick={() => void play(ep)}>
                    {ep.name}
                    {#if !ep.direct}<em>开原站</em>{/if}
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </article>
    {/each}
  </div>

  {#if playing}
    <div class="player-layer" role="presentation" onclick={(e) => { if (e.target === e.currentTarget) closePlayer(); }}>
      <div class="player-box" role="dialog" aria-modal="true" aria-label="在线播放" tabindex="-1">
        <div class="player-head">
          <span class="player-title" title={playing.title}>{playing.title}</span>
          <div class="player-tools">
            <input
              class="lib-input"
              list="lib-options"
              bind:value={importLibraryId}
              placeholder="入库到…"
              aria-label="入库目标资源库"
            />
            <datalist id="lib-options">
              {#each librariesStore.libraries as lib (lib.id)}
                <option value={String(lib.id)}>{lib.name}</option>
              {/each}
            </datalist>
            <button type="button" class="mini" disabled={importing} onclick={() => void importToLibrary()}>
              {importing ? '入库中…' : '入库'}
            </button>
            <button type="button" class="mini" onclick={closePlayer}>关闭</button>
          </div>
        </div>
        <video
          class="video"
          bind:this={videoEl}
          controls
          playsinline
          onloadedmetadata={() => videoEl?.play().catch(() => undefined)}
        ></video>
        <div class="player-foot">
          <span title={playing.url}>{playing.url}</span>
        </div>
      </div>
    </div>
  {/if}

  <ConfirmDialog
    bind:open={removeOpen}
    title="删除源"
    description="只删除本机保存的配置，不影响该站点本身。"
    confirmText="删除"
    danger
    onconfirm={() => {
      const id = removeId;
      removeOpen = false;
      removeId = null;
      if (id) void removeSource(id);
    }}
  />

  <ToastHost />
</div>

<style>
  .online {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 22px 26px 40px;
    color: var(--ink);
  }
  .head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 16px;
  }
  .eyebrow {
    font-size: 11.5px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-faint);
    margin-bottom: 4px;
  }
  h1 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 650;
  }
  .head p {
    margin: 0;
    max-width: 720px;
    font-size: 13px;
    color: var(--ink-tertiary);
    line-height: 1.6;
  }
  .head-actions {
    display: flex;
    gap: 8px;
    flex-shrink: 0;
  }
  .btn {
    font: inherit;
    font-size: 12.5px;
    padding: 7px 13px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    cursor: pointer;
    white-space: nowrap;
  }
  .btn:hover {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .btn.primary {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-soft);
  }
  .searchbar {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
  }
  .searchbar input {
    flex: 1;
    font: inherit;
    font-size: 14px;
    padding: 9px 13px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--rule);
    background: var(--bg-elevated);
    color: var(--ink);
  }
  .searchbar input:focus {
    outline: none;
    border-color: var(--accent);
  }
  .searchbar button {
    font: inherit;
    font-size: 13px;
    padding: 0 18px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--accent);
    background: var(--accent);
    color: #04120d;
    font-weight: 600;
    cursor: pointer;
  }
  .searchbar button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .source-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 14px;
  }
  .chip {
    font-size: 11.5px;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    border: 1px solid var(--rule);
    color: var(--ink-tertiary);
  }
  .chip em {
    font-style: normal;
    color: var(--ink-faint);
    margin-left: 4px;
  }
  .chip.ok {
    border-color: color-mix(in srgb, var(--accent) 40%, transparent);
    color: var(--accent);
  }
  .chip.warn {
    border-color: color-mix(in srgb, var(--warn) 55%, transparent);
    color: var(--warn);
  }
  .chip.bad {
    border-color: color-mix(in srgb, var(--danger) 55%, transparent);
    color: var(--danger);
  }
  .manage {
    border: 1px solid var(--rule);
    border-radius: var(--radius-md);
    padding: 14px 16px;
    margin-bottom: 16px;
    background: var(--bg-elevated);
  }
  .manage h2 {
    margin: 0 0 4px;
    font-size: 14px;
  }
  .manage .hint {
    margin: 0 0 10px;
    font-size: 12.5px;
    color: var(--ink-tertiary);
    line-height: 1.6;
  }
  .manage code {
    font-size: 12px;
    color: var(--ink-secondary);
  }
  .add-row {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .add-row input {
    font: inherit;
    font-size: 12.5px;
    padding: 6px 10px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: var(--bg);
    color: var(--ink);
    min-width: 180px;
  }
  .src-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .src-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 2px;
    border-top: 1px solid var(--rule-light);
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--ink-faint);
    flex-shrink: 0;
  }
  .dot.ok {
    background: var(--accent);
  }
  .dot.bad {
    background: var(--danger);
  }
  .src-main {
    display: flex;
    flex-direction: column;
    min-width: 0;
    flex: 1;
  }
  .src-main strong {
    font-size: 13px;
    font-weight: 600;
  }
  .src-url {
    font-size: 11.5px;
    color: var(--ink-faint);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mini {
    font: inherit;
    font-size: 11.5px;
    padding: 3px 9px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--ink-tertiary);
    cursor: pointer;
    white-space: nowrap;
  }
  .mini:hover {
    color: var(--ink);
    border-color: var(--ink-faint);
  }
  .mini.danger {
    color: var(--danger);
    border-color: color-mix(in srgb, var(--danger) 40%, transparent);
  }
  .empty,
  .state {
    font-size: 13px;
    color: var(--ink-tertiary);
    padding: 18px 2px;
  }
  .results {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .card {
    border: 1px solid var(--rule);
    border-radius: var(--radius-md);
    overflow: hidden;
    background: var(--bg-elevated);
  }
  .card.active {
    border-color: var(--accent);
  }
  .card-main {
    display: flex;
    gap: 12px;
    width: 100%;
    padding: 10px 12px;
    border: none;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .poster {
    width: 54px;
    height: 76px;
    border-radius: var(--radius-xs);
    overflow: hidden;
    background: var(--bg);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .poster img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .poster-empty {
    font-size: 10.5px;
    color: var(--ink-faint);
  }
  .meta {
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 5px;
  }
  .title {
    font-size: 14px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sub {
    display: flex;
    gap: 10px;
    font-size: 12px;
    color: var(--ink-tertiary);
  }
  .offers {
    border-top: 1px solid var(--rule-light);
    padding: 10px 12px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .offer-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .offer {
    font: inherit;
    font-size: 12px;
    padding: 4px 10px;
    border-radius: var(--radius-full);
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--ink-secondary);
    cursor: pointer;
  }
  .offer:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }
  .offer em {
    font-style: normal;
    color: var(--ink-faint);
    margin-left: 5px;
  }
  .line-tabs {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .line {
    font: inherit;
    font-size: 11.5px;
    padding: 3px 9px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--ink-tertiary);
    cursor: pointer;
  }
  .line.on {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-soft);
  }
  .episodes {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    max-height: 190px;
    overflow: auto;
  }
  .ep {
    font: inherit;
    font-size: 12px;
    padding: 4px 10px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: var(--bg);
    color: var(--ink-secondary);
    cursor: pointer;
    white-space: nowrap;
  }
  .ep:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
  .ep.page {
    color: var(--ink-faint);
  }
  .ep em {
    font-style: normal;
    margin-left: 4px;
    font-size: 10.5px;
    color: var(--ink-faint);
  }
  .player-layer {
    position: fixed;
    inset: 0;
    z-index: 80;
    background: rgba(0, 0, 0, 0.72);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 28px;
  }
  .player-box {
    width: min(1080px, 100%);
    background: var(--bg-elevated);
    border-radius: var(--radius-lg);
    border: 1px solid var(--rule);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .player-head {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--rule-light);
  }
  .player-title {
    flex: 1;
    min-width: 0;
    font-size: 13px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .player-tools {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .lib-input {
    font: inherit;
    font-size: 11.5px;
    width: 96px;
    padding: 3px 8px;
    border-radius: var(--radius-xs);
    border: 1px solid var(--rule);
    background: var(--bg);
    color: var(--ink);
  }
  .video {
    width: 100%;
    max-height: 68vh;
    background: #000;
    display: block;
  }
  .player-foot {
    padding: 7px 14px;
    font-size: 11px;
    color: var(--ink-faint);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    border-top: 1px solid var(--rule-light);
  }
</style>
