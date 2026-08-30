<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import AppShell from '$lib/components/layout/AppShell.svelte';

  let { children } = $props();

  // ---- 全局快捷键（Alt + 字母导航，? 显示帮助）----
  // 排除输入元素聚焦时触发，避免干扰打字。
  let helpToast = $state<string | null>(null);
  let helpTimer: ReturnType<typeof setTimeout> | null = null;

  const NAV_SHORTCUTS: { key: string; label: string; path: string }[] = [
    { key: 'g', label: '媒体页', path: '/media' },
    { key: 'm', label: '管理页', path: '/manage' },
    { key: 's', label: '设置', path: '/settings' },
    { key: 'i', label: '导入', path: '/import' },
  ];

  function showHelp(): void {
    helpToast = '全局快捷键：' + NAV_SHORTCUTS.map((s) => `Alt+${s.key.toUpperCase()} ${s.label}`).join(' · ') + ' · ? 帮助';
    if (helpTimer) clearTimeout(helpTimer);
    helpTimer = setTimeout(() => (helpToast = null), 5000);
  }

  onMount(() => {
    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) {
        return;
      }
      // Alt + 字母：页面导航
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        const hit = NAV_SHORTCUTS.find((s) => s.key === e.key.toLowerCase());
        if (hit) {
          e.preventDefault();
          goto(hit.path);
          return;
        }
      }
      // ? 显示快捷键帮助
      if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        showHelp();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });
</script>

<AppShell>
  {@render children()}
</AppShell>

{#if helpToast}
  <div class="global-shortcut-toast" role="status">{helpToast}</div>
{/if}

<style>
  .global-shortcut-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 9999;
    max-width: 90vw;
    padding: 10px 18px;
    border-radius: 10px;
    background: var(--bg-elevated, rgba(30, 30, 46, 0.95));
    border: 1px solid var(--rule, rgba(255, 255, 255, 0.12));
    color: var(--ink, #eee);
    font-size: 13px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
    text-align: center;
    animation: sc-fade 200ms ease;
  }

  @keyframes sc-fade {
    from { opacity: 0; transform: translateX(-50%) translateY(8px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
</style>
