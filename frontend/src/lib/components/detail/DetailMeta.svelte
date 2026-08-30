<script lang="ts">
  // 详情页右栏元数据区：原始文件名/重命名、描述、字幕
  import type { Media } from '$lib/api/media';
  import type { Subtitle } from './types';

  let {
    media,
    description,
    subtitles,
    // 重命名状态（由父组件管理）
    renameEditing = $bindable(false),
    renameDraft = $bindable(''),
    renameReScrape = $bindable(false),
    renaming = false,
    // 描述编辑状态（由父组件管理）
    descEditing = $bindable(false),
    descDraft = $bindable(''),
    // 回调
    onstartRename,
    onsaveRename,
    oncancelRename,
    onstartDescEdit,
    onsaveDesc,
    oncancelDesc,
    ondescKeydown,
    onloadSubtitleFile
  }: {
    media: Media;
    description: string;
    subtitles: Subtitle[];
    renameEditing?: boolean;
    renameDraft?: string;
    renameReScrape?: boolean;
    renaming?: boolean;
    descEditing?: boolean;
    descDraft?: string;
    onstartRename?: () => void;
    onsaveRename?: () => void;
    oncancelRename?: () => void;
    onstartDescEdit?: () => void;
    onsaveDesc?: () => void;
    oncancelDesc?: () => void;
    ondescKeydown?: (e: KeyboardEvent) => void;
    onloadSubtitleFile?: (fileName: string) => void;
  } = $props();

  let renameInput: HTMLInputElement | null = $state(null);
  let descTextarea: HTMLTextAreaElement | null = $state(null);
  let subtitleInput: HTMLInputElement | null = $state(null);

  function subtitleTypeLabel(t: Subtitle['type']): string {
    if (t === 'external') return '外部';
    if (t === 'embedded') return '内嵌';
    if (t === 'network') return '网络';
    return t;
  }

  function handleSubtitleFile(e: Event): void {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    onloadSubtitleFile?.(file.name);
    input.value = '';
  }

  // 聚焦输入框
  $effect(() => {
    if (renameEditing) {
      queueMicrotask(() => {
        renameInput?.focus();
        renameInput?.select();
      });
    }
  });

  $effect(() => {
    if (descEditing) {
      queueMicrotask(() => {
        descTextarea?.focus();
      });
    }
  });
</script>

<!-- 0. 原始文件名 + 重命名 -->
<section class="section file-section">
  <div class="section-head">
    <h2 class="section-title">原始文件</h2>
    {#if !renameEditing}
      <button class="section-edit" onclick={() => onstartRename?.()} title="重命名文件">重命名</button>
    {/if}
  </div>
  {#if renameEditing}
    <div class="rename-inline">
      <input
        bind:this={renameInput}
        class="rename-input"
        bind:value={renameDraft}
        onkeydown={(e) => {
          if (e.key === 'Enter') onsaveRename?.();
          if (e.key === 'Escape') oncancelRename?.();
        }}
        placeholder="输入新文件名"
        disabled={renaming}
      />
      <label class="rename-rescrape">
        <input type="checkbox" bind:checked={renameReScrape} disabled={renaming} />
        <span>重新刮削</span>
      </label>
      <button class="rename-btn ok" onclick={() => onsaveRename?.()} disabled={renaming || !renameDraft.trim()}>
        {renaming ? '…' : '保存'}
      </button>
      <button class="rename-btn cancel" onclick={() => oncancelRename?.()} disabled={renaming}>取消</button>
    </div>
  {:else}
    <div class="file-display" title={media.filename}>
      <svg class="file-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M3 2h7l3 3v9H3V2z" stroke-linejoin="round"></path>
        <path d="M10 2v3h3" stroke-linejoin="round"></path>
      </svg>
      <span class="file-name-text">{media.filename}</span>
    </div>
  {/if}
</section>

<!-- 1. 描述 -->
<section class="section">
  <div class="section-head">
    <h2 class="section-title">描述</h2>
    {#if !descEditing && description}
      <button class="section-edit" onclick={() => onstartDescEdit?.()}>编辑</button>
    {/if}
  </div>
  {#if descEditing}
    <div class="desc-edit">
      <textarea
        bind:this={descTextarea}
        bind:value={descDraft}
        class="desc-textarea"
        rows="5"
        onblur={() => onsaveDesc?.()}
        onkeydown={(e) => ondescKeydown?.(e)}
        placeholder="输入描述..."
      ></textarea>
      <div class="desc-hint">失焦保存 · Ctrl+Enter 保存 · Esc 取消</div>
    </div>
  {:else}
    <div class="desc-body" onclick={() => onstartDescEdit?.()} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onstartDescEdit?.(); } }} role="button" tabindex="0">
      {#if description}
        {description}
      {:else}
        <span class="placeholder">点击添加描述...</span>
      {/if}
    </div>
  {/if}
</section>

<!-- 字幕 -->
<section class="section">
  <div class="section-head">
    <h2 class="section-title">字幕</h2>
    <button class="section-add" onclick={() => subtitleInput?.click()}>
      <svg viewBox="0 0 24 24" width="12" height="12"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" fill="currentColor"/></svg>
      加载字幕
    </button>
    <input bind:this={subtitleInput} type="file" class="subtitle-hidden-input" accept=".srt,.vtt,.ass,.ssa,.sub" onchange={handleSubtitleFile} />
  </div>
  {#if subtitles.length > 0}
    <div class="subtitle-list">
      {#each subtitles as sub (sub.id)}
        <div class="subtitle-item" class:default={sub.default}>
          <div class="sub-info">
            <span class="sub-lang">{sub.language}</span>
            <span class="sub-type">{subtitleTypeLabel(sub.type)}</span>
            {#if sub.default}<span class="sub-default-badge">默认</span>{/if}
          </div>
          {#if sub.url}
            <a class="link-btn-icon" href={sub.url} target="_blank" rel="noopener noreferrer" title="下载字幕">
              <svg viewBox="0 0 24 24" width="12" height="12"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" fill="currentColor"/></svg>
            </a>
          {/if}
        </div>
      {/each}
    </div>
  {:else}
    <div class="section-empty">暂无字幕，点击"加载字幕"添加外部字幕文件</div>
  {/if}
</section>

<style>
  /* ---- 共享 section 样式 ---- */
  .section {
    max-width: 1280px;
    margin: 0 auto 28px;
    padding: 24px 28px;
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
    font-size: 16px;
    font-weight: 600;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 9px;
  }

  .section-title::before {
    content: '';
    width: 4px;
    height: 16px;
    border-radius: 2px;
    background: var(--accent);
    display: inline-block;
  }

  .section-edit,
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

  .section-edit:hover,
  .section-add:hover {
    background: var(--accent-soft);
  }

  .section-empty {
    padding: 16px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    background: var(--bg-soft);
    border-radius: var(--radius);
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

  /* ---- 文件名 section ---- */
  .file-section {
    padding-bottom: 16px;
  }
  .file-display {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: var(--radius);
    background: var(--bg2);
    border: 1px solid var(--rule);
    transition: border-color 0.2s;
  }
  .file-display:hover {
    border-color: var(--muted);
  }
  .file-icon {
    flex-shrink: 0;
    color: var(--muted);
  }
  .file-name-text {
    font-size: 12.5px;
    font-family: monospace;
    color: var(--ink);
    word-break: break-all;
    line-height: 1.5;
  }

  /* ---- 文件重命名 ---- */
  .rename-inline {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .rename-input {
    flex: 1;
    min-width: 200px;
    padding: 6px 10px;
    border: 1px solid var(--border, rgba(255,255,255,0.15));
    border-radius: var(--radius);
    background: var(--bg, rgba(0,0,0,0.2));
    color: var(--ink);
    font-size: 12.5px;
    font-family: monospace;
    outline: none;
    transition: border-color 0.2s;
  }
  .rename-input:focus {
    border-color: var(--accent, #635bff);
  }
  .rename-rescrape {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: var(--muted);
    cursor: pointer;
    white-space: nowrap;
  }
  .rename-rescrape input {
    cursor: pointer;
  }
  .rename-btn {
    padding: 5px 14px;
    border: none;
    border-radius: var(--radius);
    font-size: 12px;
    cursor: pointer;
    transition: background 0.2s, opacity 0.2s;
    white-space: nowrap;
  }
  .rename-btn.ok {
    background: var(--accent, #635bff);
    color: #fff;
  }
  .rename-btn.ok:hover {
    opacity: 0.9;
  }
  .rename-btn.cancel {
    background: var(--bg-hover);
    color: var(--muted);
  }
  .rename-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* ---- 描述 ---- */
  .desc-body {
    padding: 12px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    font-size: 13px;
    line-height: 1.7;
    color: var(--ink);
    cursor: text;
    white-space: pre-wrap;
    min-height: 48px;
    transition: background 200ms;
  }

  .desc-body:hover {
    background: var(--bg2);
    box-shadow: inset 0 0 0 1px var(--rule);
  }

  .placeholder {
    color: var(--muted);
    font-style: italic;
  }

  .desc-edit {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .desc-textarea {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    line-height: 1.7;
    font-family: inherit;
    resize: vertical;
    min-height: 100px;
  }

  .desc-textarea:focus {
    outline: none;
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .desc-hint {
    font-size: 11.5px;
    color: var(--muted);
  }

  /* ---- 字幕 ---- */
  .subtitle-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .subtitle-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
  }

  .subtitle-item.default {
    background: var(--accent-soft);
  }

  .sub-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .sub-lang {
    font-size: 13px;
    color: var(--ink);
    font-weight: 500;
  }

  .sub-type {
    font-size: 11px;
    color: var(--muted);
    background: var(--bg2);
    padding: 1px 8px;
    border-radius: var(--radius-full);
  }

  .subtitle-item.default .sub-type {
    background: var(--bg2);
  }

  .sub-default-badge {
    font-size: 10px;
    color: var(--accent);
    background: var(--bg2);
    padding: 1px 6px;
    border-radius: var(--radius-full);
    font-weight: 500;
  }

  .subtitle-hidden-input {
    display: none;
  }
</style>
