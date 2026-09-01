<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { browser } from '$app/environment';
  import { onMount, onDestroy } from 'svelte';
  import { tasks } from '$lib/stores/tasks.svelte';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { toggleWorkAreaMaximize, isWorkAreaMaximized, sizeLooksMaximized } from '$lib/utils/tauri-window';

  let { onOpenSearch }: { onOpenSearch?: () => void } = $props();

  const path = $derived($page.url.pathname);
  const searchShortcut = browser && /Mac|iPhone|iPad/.test(navigator.userAgent) ? '⌘K' : 'Ctrl K';
  let theme = $state<'light' | 'dark'>('dark');

  function currentTheme(): 'light' | 'dark' {
    if (typeof document === 'undefined') return 'dark';
    const attr = document.documentElement.getAttribute('data-theme');
    if (attr === 'light' || attr === 'dark') return attr;
    return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }

  onMount(() => {
    theme = currentTheme();
  });

  function toggleTheme(): void {
    const next: 'light' | 'dark' = theme === 'dark' ? 'light' : 'dark';
    theme = next;
    const root = document.documentElement;
    root.setAttribute('data-theme', next);
    root.style.colorScheme = next;
    void settingsStore.update('theme', next);
  }

  function tabActive(prefix: string): boolean {
    return path === prefix || path.startsWith(prefix + '/');
  }

  // ---- Tauri 窗口控制（仅桌面端可用，浏览器中静默失败） ----
  let isMaximized = $state(false);
  let unlistenResize: (() => void) | null = null;

  type TauriWindow = {
    minimize(): Promise<void>;
    close(): Promise<void>;
    isMaximized(): Promise<boolean>;
    onResized(cb: () => void): Promise<() => void>;
    setSize(s: { width: number; height: number }): Promise<void>;
    setPosition(p: { x: number; y: number }): Promise<void>;
    outerSize(): Promise<{ width: number; height: number }>;
    outerPosition(): Promise<{ x: number; y: number }>;
  };

  async function getCurrentWindow(): Promise<TauriWindow | null> {
    try {
      const { getCurrentWindow } = await import('@tauri-apps/api/window');
      return getCurrentWindow() as unknown as TauriWindow;
    } catch {
      return null;
    }
  }

  async function initWindow() {
    const win = await getCurrentWindow();
    if (!win) return;
    try {
      isMaximized = await win.isMaximized() || isWorkAreaMaximized();
    } catch {
      // 权限不足时静默忽略
    }
    unlistenResize = await win.onResized(async () => {
      try {
        // 手动工作区最大化不会让系统 isMaximized() 返回 true，
        // 用尺寸是否铺满工作区来判断（兼容系统最大化与手动最大化）。
        const s = await win.outerSize();
        isMaximized = s ? sizeLooksMaximized(s) : await win.isMaximized();
      } catch {
        // ignore
      }
    });
  }

  onDestroy(() => {
    unlistenResize?.();
  });

  async function minimize() {
    const win = await getCurrentWindow();
    win?.minimize();
  }

  async function toggleMaximize() {
    const win = await getCurrentWindow();
    if (!win) return;
    try {
      // 手动"最大化到工作区"：任务栏保持可见（系统 maximize 在无边框窗口下会覆盖任务栏）
      isMaximized = await toggleWorkAreaMaximize(win);
    } catch {
      // ignore
    }
  }

  async function closeWindow() {
    const win = await getCurrentWindow();
    win?.close();
  }

  // 检测是否在 Tauri 环境
  let isTauri = $state(false);
  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    isTauri = true;
    initWindow().catch(() => {});
  }
</script>

<header class="topnav" data-tauri-drag-region>
  <div class="left" data-tauri-drag-region>
    <button class="logo" data-tauri-drag-region="false" onclick={() => goto('/media?mode=center')} aria-label="vitoice 首页"
        title="回到观看中心">
      <img class="logo-mark" src="/logo-mark.png" width="24" height="24" alt="" aria-hidden="true" />
      <span class="logo-text">vitoice</span>
    </button>
    <nav class="tabs" data-tauri-drag-region>
      <button class="tab" class:active={tabActive('/media')} aria-current={tabActive('/media') ? 'page' : undefined} data-tauri-drag-region="false" onclick={() => goto('/media')}>
        <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="2" y="3" width="12" height="10" rx="1.5"></rect>
          <path d="M2 6h12M5 3v10M11 3v10" stroke-opacity="0.5"></path>
        </svg>
        <span>媒体</span>
      </button>
      <button class="tab" class:active={tabActive('/manage')} aria-current={tabActive('/manage') ? 'page' : undefined} data-tauri-drag-region="false" onclick={() => goto('/manage')}>
        <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M2 4h6M2 8h9M2 12h5" stroke-linecap="round"></path>
          <circle cx="12" cy="4" r="1.8"></circle>
          <circle cx="11" cy="8" r="1.8"></circle>
          <circle cx="10" cy="12" r="1.8"></circle>
        </svg>
        <span>管理</span>
      </button>
      <button class="tab" class:active={tabActive('/settings') || path === '/libraries'} aria-current={tabActive('/settings') || path === '/libraries' ? 'page' : undefined} data-tauri-drag-region="false" onclick={() => goto('/settings')}>
        <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="8" cy="8" r="2.2"></circle>
          <path d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1M12.6 12.6l-1.1-1.1M4.5 4.5L3.4 3.4"></path>
        </svg>
        <span>设置</span>
        <span class="changed">含资源库</span>
      </button>
    </nav>
  </div>

  <div class="center" data-tauri-drag-region>
    <button class="search" data-tauri-drag-region="false" onclick={() => onOpenSearch?.()} type="button">
      <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
        <circle cx="7" cy="7" r="5"></circle>
        <line x1="10.5" y1="10.5" x2="14" y2="14" stroke-linecap="round"></line>
      </svg>
      <span class="search-placeholder">搜索媒体</span>
      <kbd class="search-kbd">{searchShortcut}</kbd>
    </button>
  </div>

  <div class="right" data-tauri-drag-region>
    <button class="theme-switch" data-tauri-drag-region="false" role="switch" aria-checked={theme === 'light'} aria-label="切换深浅色" title="切换深浅色" onclick={toggleTheme}>
      <svg class="sun" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><circle cx="8" cy="8" r="2.7"></circle><path d="M8 1.5v1.4M8 13.1v1.4M1.5 8h1.4M13.1 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1" stroke-linecap="round"></path></svg>
      <svg class="moon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7z" stroke-linejoin="round"></path></svg>
      <span class="theme-switch-thumb"></span>
    </button>
    <button class="icon-btn task-btn" title="任务中心" data-tauri-drag-region="false" aria-label="任务中心" onclick={() => tasks.toggle()}>
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4">
        <circle cx="8" cy="8" r="6"></circle>
        <path d="M8 4.5V8l2.2 1.4" stroke-linecap="round" stroke-linejoin="round"></path>
      </svg>
      {#if tasks.count > 0}
        <span class="badge">{tasks.count}</span>
      {/if}
    </button>
  </div>

  <!-- 窗口控制按钮（仅 Tauri 桌面端显示，样式对齐右侧 icon-btn） -->
  {#if isTauri}
    <div class="window-controls" data-tauri-drag-region="false">
      <button class="win-btn" data-tauri-drag-region="false" onclick={minimize} aria-label="最小化" title="最小化">
        <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4">
          <line x1="3" y1="6" x2="9" y2="6" stroke-linecap="round"></line>
        </svg>
      </button>
      <button class="win-btn" data-tauri-drag-region="false" onclick={toggleMaximize} aria-label="最大化/还原" title="最大化/还原">
        {#if isMaximized}
          <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4">
            <rect x="3.5" y="4.5" width="5" height="5" rx="0.8"></rect>
            <path d="M4.5 4.5V3.5h5v5h-1" stroke-opacity="0.55" stroke-linejoin="round"></path>
          </svg>
        {:else}
          <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4">
            <rect x="3" y="3" width="6" height="6" rx="1"></rect>
          </svg>
        {/if}
      </button>
      <button class="win-btn close" data-tauri-drag-region="false" onclick={closeWindow} aria-label="关闭" title="关闭">
        <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.4">
          <line x1="3.5" y1="3.5" x2="8.5" y2="8.5" stroke-linecap="round"></line>
          <line x1="8.5" y1="3.5" x2="3.5" y2="8.5" stroke-linecap="round"></line>
        </svg>
      </button>
    </div>
  {/if}
</header>

<style>
  .topnav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--topnav-h);
    padding: 0 12px 0 14px;
    background: color-mix(in srgb, var(--bg-elevated) 80%, transparent);
    backdrop-filter: blur(16px) saturate(180%);
    -webkit-backdrop-filter: blur(16px) saturate(180%);
    border-bottom: 1px solid var(--rule);
    flex-shrink: 0;
    gap: 16px;
    z-index: 10;
  }

  .left {
    display: flex;
    align-items: center;
    gap: 20px;
    min-width: 0;
  }

  .logo {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: none;
    border: none;
    padding: 0;
    transition: transform var(--dur) var(--ease-spring);
  }

  .logo:hover {
    transform: scale(1.02);
  }

  .logo-mark {
    flex-shrink: 0;
    filter: drop-shadow(0 2px 8px var(--accent-glow));
  }

  .logo-text {
    font-family: var(--font-display);
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 0;
    background: linear-gradient(135deg, var(--ink) 0%, var(--accent) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .tabs {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  .tab {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: none;
    border: none;
    padding: 6px 13px;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 500;
    color: var(--ink-tertiary);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
  }

  .tab:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }

  .tab.active {
    color: var(--accent);
    background: var(--accent-soft);
  }

  .tab .changed {
    margin-left: 3px;
    padding: 1px 6px;
    height: 16px;
    line-height: 14px;
    border-radius: var(--radius-full);
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 10px;
    font-weight: 600;
  }

  .center {
    flex: 1;
    display: flex;
    justify-content: center;
    min-width: 0;
  }

  .search {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    max-width: 420px;
    height: 34px;
    padding: 0 10px;
    background: var(--bg-surface);
    border: 1px solid transparent;
    border-radius: var(--radius-full);
    color: var(--ink-tertiary);
    transition: background var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out), box-shadow var(--dur) var(--ease-out);
  }

  .search:hover {
    background: var(--bg-hover);
    border-color: var(--rule);
  }

  .search:focus-visible {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .search-placeholder {
    flex: 1;
    text-align: left;
    font-size: 13px;
    color: var(--ink-tertiary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .search-kbd {
    font-family: var(--font-mono);
    font-size: 10.5px;
    color: var(--ink-tertiary);
    background: var(--bg-elevated);
    border: 1px solid var(--rule);
    border-radius: var(--radius-xs);
    padding: 1px 5px;
    line-height: 1.4;
  }

  .right {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .icon-btn {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: none;
    border: none;
    border-radius: var(--radius);
    color: var(--ink-tertiary);
    transition: background var(--dur) var(--ease-out), color var(--dur) var(--ease-out);
  }

  .icon-btn:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }

  .theme-switch {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: space-between;
    width: 48px;
    height: 26px;
    padding: 0 7px;
    border: 1px solid var(--rule);
    border-radius: var(--radius-full);
    background: var(--bg-hover);
    color: var(--ink-tertiary);
    cursor: pointer;
    transition: border-color var(--dur) var(--ease-out), background var(--dur) var(--ease-out);
  }
  .theme-switch:hover { border-color: var(--ink-tertiary); }
  .theme-switch svg { position: relative; z-index: 1; width: 13px; height: 13px; }
  .theme-switch .sun { color: var(--accent2); }
  .theme-switch .moon { color: var(--ink3, var(--ink-tertiary)); }
  .theme-switch-thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 2px 8px var(--accent-glow);
    transition: transform 180ms ease, background 180ms ease;
  }
  :global([data-theme='light']) .theme-switch-thumb {
    transform: translateX(22px);
  }
  :global([data-theme='light']) .theme-switch .sun {
    color: var(--ink-tertiary);
  }
  :global([data-theme='light']) .theme-switch .moon {
    color: var(--accent);
  }

  .badge {
    position: absolute;
    top: -2px;
    right: -2px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    background: var(--accent);
    color: #fff;
    font-size: 10px;
    font-weight: 600;
    line-height: 16px;
    border-radius: var(--radius-full);
    text-align: center;
    box-shadow: 0 0 0 2px var(--bg-elevated);
  }

  /* ---- 窗口控制按钮（Tauri 桌面端，与右侧 icon-btn 同款风格） ---- */
  .window-controls {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: 8px;
    padding-left: 10px;
    border-left: 1px solid var(--rule);
    -webkit-app-region: no-drag;
  }

  .win-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: none;
    border: none;
    border-radius: var(--radius);
    color: var(--ink-tertiary);
    cursor: default;
    transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
  }

  .win-btn:hover {
    background: var(--bg-hover);
    color: var(--ink);
  }

  .win-btn:active {
    transform: scale(0.92);
  }

  .win-btn.close:hover {
    background: var(--danger);
    color: #fff;
  }

  /* 所有交互元素排除拖拽 */
  .topnav button {
    -webkit-app-region: no-drag;
    app-region: no-drag;
  }
</style>
