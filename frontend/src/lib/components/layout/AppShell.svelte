<script lang="ts">
  import { onMount } from 'svelte';
  import TopNav from './TopNav.svelte';
  import Sidebar from './Sidebar.svelte';
  import TaskDrawer from './TaskDrawer.svelte';
  import SearchModal from './SearchModal.svelte';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { sidebar } from '$lib/stores/sidebar.svelte';

  // Tauri v2 declares ResizeDirection inside @tauri-apps/api/window but does
  // not export it, so mirror the union locally. The values are the strings
  // startResizeDragging expects on the Rust side.
  type ResizeDirection =
    | 'East'
    | 'North'
    | 'NorthEast'
    | 'NorthWest'
    | 'South'
    | 'SouthEast'
    | 'SouthWest'
    | 'West';

  let { children } = $props();

  let searchOpen = $state(false);

  // ---- Tauri 窗口 resize 手柄（decorations:false 时需要自定义） ----
  let isTauri = $state(false);
  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    isTauri = true;
  }

  async function startResize(direction: ResizeDirection): Promise<void> {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      const win = getCurrentWindow();
      await win.startResizeDragging(direction);
    } catch {
      // 浏览器环境或 API 不可用时静默忽略
    }
  }

  onMount(() => {
    // Load global settings from backend (with localStorage fallback)
    void settingsStore.load();
  });

  function openSearch(): void {
    searchOpen = true;
  }
  function closeSearch(): void {
    searchOpen = false;
  }

  function handleKeydown(e: KeyboardEvent): void {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      searchOpen = !searchOpen;
      return;
    }
    if (e.key === 'Escape' && searchOpen) {
      searchOpen = false;
    }
  }

  onMount(() => {
    window.addEventListener('keydown', handleKeydown);
    // 侧边栏默认常驻展开（sidebar store 的 collapsed 默认为 false）
    // 窄屏（<960px）自动折叠侧边栏，回到宽屏自动展开——仅在跨阈值时切换，
    // 不覆盖用户手动折叠/展开的状态。
    let lastW = window.innerWidth;
    const onResize = () => {
      const w = window.innerWidth;
      if (w < 960 && lastW >= 960) sidebar.collapse();
      else if (w >= 960 && lastW < 960) sidebar.expand();
      lastW = w;
    };
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('keydown', handleKeydown);
      window.removeEventListener('resize', onResize);
    };
  });
</script>

<div class="app-shell">
  <TopNav onOpenSearch={openSearch} />
  <div class="app-body">
    <Sidebar />
    <main class="app-main">
      {@render children()}
    </main>
  </div>
  <TaskDrawer />
  <SearchModal bind:open={searchOpen} onClose={closeSearch} />
</div>

<!-- 窗口 resize 手柄（仅 Tauri 桌面端，decorations:false 时提供窗口边缘调整） -->
{#if isTauri}
  <div class="resize-handles" aria-hidden="true">
    <div class="rh rh-n" onmousedown={() => startResize('North')}></div>
    <div class="rh rh-s" onmousedown={() => startResize('South')}></div>
    <div class="rh rh-w" onmousedown={() => startResize('West')}></div>
    <div class="rh rh-e" onmousedown={() => startResize('East')}></div>
    <div class="rh rh-nw" onmousedown={() => startResize('NorthWest')}></div>
    <div class="rh rh-ne" onmousedown={() => startResize('NorthEast')}></div>
    <div class="rh rh-sw" onmousedown={() => startResize('SouthWest')}></div>
    <div class="rh rh-se" onmousedown={() => startResize('SouthEast')}></div>
  </div>
{/if}

<style>
  .app-shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
    background: var(--bg);
  }

  .app-body {
    display: flex;
    flex: 1;
    min-height: 0;
  }

  .app-main {
    flex: 1;
    min-width: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    background: var(--bg);
  }

  /* ---- 窗口 resize 手柄 ---- */
  .resize-handles {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 9999;
  }

  .rh {
    position: absolute;
    pointer-events: auto;
  }

  /* 边缘手柄：4px 宽，可拖拽调整窗口大小 */
  .rh-n { top: 0; left: 6px; right: 6px; height: 4px; cursor: ns-resize; }
  .rh-s { bottom: 0; left: 6px; right: 6px; height: 4px; cursor: ns-resize; }
  .rh-w { left: 0; top: 6px; bottom: 6px; width: 4px; cursor: ew-resize; }
  .rh-e { right: 0; top: 6px; bottom: 6px; width: 4px; cursor: ew-resize; }

  /* 角落手柄：8x8px，双向调整 */
  .rh-nw { top: 0; left: 0; width: 8px; height: 8px; cursor: nwse-resize; }
  .rh-ne { top: 0; right: 0; width: 8px; height: 8px; cursor: nesw-resize; }
  .rh-sw { bottom: 0; left: 0; width: 8px; height: 8px; cursor: nesw-resize; }
  .rh-se { bottom: 0; right: 0; width: 8px; height: 8px; cursor: nwse-resize; }
</style>
