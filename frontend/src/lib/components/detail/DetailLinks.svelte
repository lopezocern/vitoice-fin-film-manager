<script lang="ts">
  // 详情页资源链接区：源链接/参考链接展示、链接编辑弹窗、删除确认
  import type { MediaUrl, UrlRole } from '$lib/api/media';
  import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

  let {
    sourceLinks,
    referenceLinks,
    // 链接编辑器状态（由父组件管理）
    linkEditorOpen = $bindable(false),
    linkEditing = $bindable<MediaUrl | null>(null),
    linkForm = $bindable({
      url: '',
      title: '',
      url_role: 'source' as UrlRole,
      platform: ''
    }),
    platformManual = $bindable(false),
    linkSaving = false,
    // 链接删除状态（由父组件管理）
    linkDeleteOpen = $bindable(false),
    linkDeleteTarget = $bindable<MediaUrl | null>(null),
    // 回调
    onadd,
    onedit,
    oncancel,
    onSave,
    onconfirmDelete,
    onDelete,
    oncancelDelete,
    onplay,
    showAggregateResolve = false,
    aggregateResolving = false,
    onaggregateResolve
  }: {
    sourceLinks: MediaUrl[];
    referenceLinks: MediaUrl[];
    linkEditorOpen?: boolean;
    linkEditing?: MediaUrl | null;
    linkForm?: { url: string; title: string; url_role: UrlRole; platform: string };
    platformManual?: boolean;
    linkSaving?: boolean;
    linkDeleteOpen?: boolean;
    linkDeleteTarget?: MediaUrl | null;
    onadd?: () => void;
    onedit?: (link: MediaUrl) => void;
    oncancel?: () => void;
    onSave?: () => void;
    onconfirmDelete?: (link: MediaUrl) => void;
    onDelete?: () => void;
    oncancelDelete?: () => void;
    onplay?: () => void;
    showAggregateResolve?: boolean;
    aggregateResolving?: boolean;
    onaggregateResolve?: () => void;
  } = $props();

  // 平台自动识别：根据 URL 域名推断平台名称
  function detectPlatform(url: string): string {
    try {
      const host = new URL(url).hostname.toLowerCase();
      if (host.includes('youtube') || host.includes('youtu.be')) return 'YouTube';
      if (host.includes('bilibili') || host.includes('b23.tv')) return 'Bilibili';
      if (host.includes('vimeo')) return 'Vimeo';
      if (host.includes('dailymotion')) return 'Dailymotion';
      if (host.includes('twitch')) return 'Twitch';
      if (host.includes('youku')) return 'Youku';
      if (host.includes('iqiyi')) return 'iQiyi';
      if (host.includes('v.qq.com')) return 'Tencent Video';
      if (host.includes('baidu')) return 'Baidu';
      if (host.includes('weibo')) return 'Weibo';
      if (host.includes('twitter') || host.includes('x.com')) return 'Twitter/X';
      if (host.includes('instagram')) return 'Instagram';
      if (host.includes('tiktok') || host.includes('douyin')) return 'TikTok/Douyin';
      if (host.includes('javbus')) return 'JavBus';
      if (host.includes('javlibrary')) return 'JavLibrary';
      if (host.includes('tmdb') || host.includes('themoviedb')) return 'TMDB';
      if (host.includes('imdb')) return 'IMDB';
      return host;
    } catch {
      return '';
    }
  }

  // URL 输入时自动填充平台（用户手动修改后不再覆盖）
  function onLinkUrlInput(): void {
    if (!platformManual && linkForm.url) {
      const detected = detectPlatform(linkForm.url);
      if (detected) {
        linkForm.platform = detected;
      }
    }
  }

  function linkHost(url: string): string {
    try {
      return new URL(url).hostname;
    } catch {
      return url;
    }
  }

  function cancelLinkEditor(): void {
    oncancel?.();
  }

  function handleCancelDelete(): void {
    oncancelDelete?.();
  }
</script>

<section class="section">
  <div class="section-head">
    <h2 class="section-title">资源版本</h2>
    {#if showAggregateResolve}
      <button class="section-add aggregate-btn" onclick={() => onaggregateResolve?.()} disabled={linkSaving || aggregateResolving} title="从聚合站（javgg）解析番号并添加网络源（已存在的服务器源自动刷新，不重复添加）">
        {aggregateResolving ? '解析中…' : '从聚合站解析'}
      </button>
    {/if}
    <button class="section-add" onclick={() => onadd?.()} disabled={linkSaving}>
      <svg viewBox="0 0 24 24" width="12" height="12"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" fill="currentColor"/></svg>
      添加链接
    </button>
  </div>
  {#if sourceLinks.length === 0 && referenceLinks.length === 0}
    <div class="section-empty">
      暂无资源链接
      <button class="link-btn" onclick={() => onadd?.()}>添加链接</button>
    </div>
  {:else}
    {#if sourceLinks.length > 0}
      <div class="link-group">
        <div class="link-group-head">源链接 (Source)</div>
        {#each sourceLinks as link (link.id)}
          <div class="link-item" class:expired={link.is_expired}>
            <a
              class="link-label"
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              title={link.url}
            >
              <svg viewBox="0 0 24 24" width="12" height="12"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
              {link.title || linkHost(link.url)}
              {#if link.platform}
                <span class="link-platform">{link.platform}</span>
              {/if}
              {#if link.is_expired}
                <span class="link-expired-badge">已失效</span>
              {/if}
            </a>
            <div class="link-actions">
              <button class="link-btn-icon" onclick={() => onplay?.()} title="播放">
                <svg viewBox="0 0 24 24" width="12" height="12"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>
              </button>
              <button class="link-btn-icon" onclick={() => onedit?.(link)} title="编辑">
                <svg viewBox="0 0 24 24" width="12" height="12"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/></svg>
              </button>
              <button class="link-btn-icon danger" onclick={() => onconfirmDelete?.(link)} title="删除">
                <svg viewBox="0 0 24 24" width="12" height="12"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/></svg>
              </button>
              <a class="link-btn-icon" href={link.url} target="_blank" rel="noopener noreferrer" title="打开链接">
                <svg viewBox="0 0 24 24" width="12" height="12"><path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z" fill="currentColor"/></svg>
              </a>
            </div>
          </div>
        {/each}
      </div>
    {/if}
    {#if referenceLinks.length > 0}
      <div class="link-group">
        <div class="link-group-head">参考链接 (Reference)</div>
        {#each referenceLinks as link (link.id)}
          <div class="link-item" class:expired={link.is_expired}>
            <a
              class="link-label"
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              title={link.url}
            >
              <svg viewBox="0 0 24 24" width="12" height="12"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z" fill="currentColor"/></svg>
              {link.title || linkHost(link.url)}
              {#if link.platform}
                <span class="link-platform">{link.platform}</span>
              {/if}
              {#if link.is_expired}
                <span class="link-expired-badge">已失效</span>
              {/if}
            </a>
            <div class="link-actions">
              <button class="link-btn-icon" onclick={() => onedit?.(link)} title="编辑">
                <svg viewBox="0 0 24 24" width="12" height="12"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/></svg>
              </button>
              <button class="link-btn-icon danger" onclick={() => onconfirmDelete?.(link)} title="删除">
                <svg viewBox="0 0 24 24" width="12" height="12"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/></svg>
              </button>
              <a class="link-btn-icon" href={link.url} target="_blank" rel="noopener noreferrer" title="打开链接">
                <svg viewBox="0 0 24 24" width="12" height="12"><path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z" fill="currentColor"/></svg>
              </a>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</section>

<!-- 资源链接编辑器弹窗 -->
{#if linkEditorOpen}
  <div
    class="modal-overlay"
    onclick={cancelLinkEditor}
    role="button"
    tabindex="0"
    onkeydown={(e) => { if (e.key === 'Escape') { e.preventDefault(); cancelLinkEditor(); } }}
  >
    <div
      class="modal-card"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="modal-head">
        <h3 class="modal-title">{linkEditing ? '编辑链接' : '添加链接'}</h3>
        <button class="modal-close" onclick={cancelLinkEditor} aria-label="关闭" tabindex="-1">✕</button>
      </div>
      <div class="modal-body">
        <div class="form-field">
          <label class="form-label" for="link-url">链接地址 <span class="req">*</span></label>
          <input
            id="link-url"
            class="form-input"
            type="url"
            bind:value={linkForm.url}
            oninput={onLinkUrlInput}
            placeholder="https://..."
          />
        </div>
        <div class="form-field">
          <label class="form-label" for="link-title">标签 / 标题</label>
          <input
            id="link-title"
            class="form-input"
            type="text"
            bind:value={linkForm.title}
            placeholder="可选，用于显示链接名称"
          />
        </div>
        <div class="form-row">
          <div class="form-field">
            <label class="form-label" for="link-role">类型</label>
            <select id="link-role" class="form-input" bind:value={linkForm.url_role}>
              <option value="source">源链接 (Source)</option>
              <option value="reference">参考链接 (Reference)</option>
            </select>
          </div>
          <div class="form-field">
            <label class="form-label" for="link-platform">平台</label>
            <input
              id="link-platform"
              class="form-input"
              type="text"
              bind:value={linkForm.platform}
              oninput={() => { platformManual = true; }}
              placeholder="自动识别，可手动修改"
            />
          </div>
        </div>
      </div>
      <div class="modal-foot">
        <button class="modal-btn" onclick={cancelLinkEditor} disabled={linkSaving}>取消</button>
        <button class="modal-btn primary" onclick={() => onSave?.()} disabled={linkSaving || !linkForm.url.trim()}>
          {#if linkSaving}保存中…{:else}保存{/if}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- 链接删除确认对话框 -->
<ConfirmDialog
  bind:open={linkDeleteOpen}
  title="删除链接"
  description={linkDeleteTarget ? `确定要删除链接"${linkDeleteTarget.title || linkHost(linkDeleteTarget.url)}"吗？` : '确定要删除此链接吗？'}
  confirmText="删除"
  danger={true}
  onconfirm={() => onDelete?.()}
  oncancel={handleCancelDelete}
/>

<style>
  /* ---- 共享 section 样式 ---- */
  .section {
    margin-bottom: 28px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--rule);
  }

  .section:last-child {
    border-bottom: none;
    margin-bottom: 0;
  }

  .section-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }

  .section-title {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
  }

  .section-add {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: none;
    background: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: var(--radius);
    transition: background 200ms;
  }

  .section-add:hover {
    background: var(--accent-soft);
  }
  .section-add.aggregate-btn {
    color: #3b82f6;
  }
  .section-add.aggregate-btn:hover {
    background: rgba(59, 130, 246, 0.12);
  }

  .section-add:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .section-empty {
    padding: 16px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    background: var(--bg-soft);
    border-radius: var(--radius);
  }

  .link-btn {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
    margin-left: 8px;
    text-decoration: underline;
  }

  /* ---- 资源链接 ---- */
  .link-group {
    margin-bottom: 12px;
  }

  .link-group:last-child {
    margin-bottom: 0;
  }

  .link-group-head {
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 6px;
  }

  .link-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg-soft);
    border-radius: var(--radius);
    transition: background 200ms;
  }

  .link-item:hover {
    background: var(--accent-soft);
  }

  .link-label {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--ink);
    font-size: 13px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .link-label:hover {
    color: var(--accent);
  }

  .link-actions {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
  }

  .link-btn-icon {
    width: 26px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--muted);
    transition: all 200ms ease;
    cursor: pointer;
  }

  .link-btn-icon:hover {
    color: var(--accent);
    border-color: var(--accent);
  }

  .link-btn-icon.danger:hover {
    color: #ff3b30;
    border-color: #ff3b30;
  }

  .link-platform {
    font-size: 10px;
    color: var(--muted);
    background: var(--bg2);
    padding: 1px 6px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .link-expired-badge {
    font-size: 10px;
    color: #ff3b30;
    background: rgba(255, 59, 48, 0.1);
    padding: 1px 6px;
    border-radius: var(--radius-full);
    flex-shrink: 0;
  }

  .link-item.expired {
    opacity: 0.6;
  }

  .link-item.expired .link-label {
    text-decoration: line-through;
  }

  /* ---- 链接编辑器弹窗 ---- */
  .modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 2500;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fade-in 200ms ease;
  }

  .modal-card {
    width: 90%;
    max-width: 460px;
    background: var(--bg);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    overflow: hidden;
    animation: pop 200ms ease;
  }

  @keyframes pop {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes fade-in {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .modal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--rule);
  }

  .modal-title {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
  }

  .modal-close {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: var(--radius);
    background: none;
    color: var(--muted);
    font-size: 15px;
    cursor: pointer;
    transition: all 200ms;
  }

  .modal-close:hover {
    background: var(--bg-soft);
    color: var(--ink);
  }

  .modal-body {
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .form-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
  }

  .form-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--muted);
  }

  .req {
    color: #ff3b30;
  }

  .form-input {
    width: 100%;
    height: 36px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-family: inherit;
    transition: border-color 200ms;
    box-sizing: border-box;
  }

  .form-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .form-row {
    display: flex;
    gap: 12px;
  }

  .modal-foot {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 12px 20px;
    border-top: 1px solid var(--rule);
  }

  .modal-btn {
    height: 34px;
    padding: 0 18px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 200ms ease;
  }

  .modal-btn:hover:not(:disabled) {
    border-color: var(--muted);
  }

  .modal-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .modal-btn.primary {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }

  .modal-btn.primary:hover:not(:disabled) {
    filter: brightness(1.08);
  }
</style>
