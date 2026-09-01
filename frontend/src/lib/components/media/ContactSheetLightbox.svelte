<script lang="ts">
  /** 缩略图集灯箱：全屏展示 4×4 contact sheet（1920×1080）。
   *  点击遮罩 / 关闭按钮 / Esc 关闭。 */
  import { untrack } from 'svelte';
  import { mediaApi } from '$lib/api/media';

  let {
    open = $bindable(false),
    mediaId,
    title,
    version
  }: {
    open?: boolean;
    mediaId: string | null;
    title?: string;
    version?: string;
  } = $props();

  let loaded = $state(false);
  let failed = $state(false);

  function close(): void {
    open = false;
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape' && open) close();
  }

  // 切换目标媒体时重置图片状态
  $effect(() => {
    const _ = mediaId + String(version ?? '');
    if (open) {
      untrack(() => {
        loaded = false;
        failed = false;
      });
    }
  });
</script>

<svelte:window onkeydown={onKeydown} />

{#if open && mediaId}
  <div
    class="cs-lightbox"
    role="dialog"
    aria-modal="true"
    aria-label={title ? `${title} 的缩略图集` : '缩略图集'}
    tabindex="-1"
    onclick={(e) => e.target === e.currentTarget && close()}
  >
    <header class="lb-head">
      <span class="lb-title">{title ?? '缩略图集'}</span>
      <button class="lb-close" aria-label="关闭" onclick={close}>×</button>
    </header>
    <div class="lb-body">
      {#if !loaded && !failed}
        <div class="lb-loading">加载中…</div>
      {/if}
      {#if !failed}
        <img
          src={mediaApi.contactSheetUrl(mediaId, version)}
          alt={title ? `${title} 缩略图集` : '缩略图集'}
          class:hidden={!loaded}
          onload={() => (loaded = true)}
          onerror={() => (failed = true)}
        />
      {:else}
        <div class="lb-error">缩略图集加载失败</div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .cs-lightbox {
    position: fixed;
    z-index: 1600;
    inset: 0;
    display: flex;
    flex-direction: column;
    background: rgba(0, 0, 0, 0.72);
    padding: 24px;
  }
  .lb-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 4px 12px;
  }
  .lb-title {
    color: #fff;
    font-size: 14px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .lb-close {
    border: 0;
    background: transparent;
    color: rgba(255, 255, 255, 0.7);
    font-size: 22px;
    line-height: 1;
    cursor: pointer;
    padding: 2px 6px;
  }
  .lb-close:hover { color: #fff; }
  .lb-body {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
  }
  .lb-body img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: 6px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
  }
  .lb-body img.hidden { display: none; }
  .lb-loading,
  .lb-error {
    color: rgba(255, 255, 255, 0.75);
    font-size: 14px;
  }
  .lb-error { color: #fb7185; }
</style>
