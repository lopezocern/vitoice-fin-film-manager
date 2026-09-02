<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { sidebar } from '$lib/stores/sidebar.svelte';
  import { liveQueryParam } from '$lib/stores/urlState.svelte';

  const collapsed = $derived(sidebar.collapsed);
  const pathname = $derived($page.url.pathname);
  // 不能用 $page.url.searchParams：popstate 重挂载时 page store 只恢复 pathname、
  // 丢失 query，侧栏高亮会跳回默认项。liveQueryParam 读 window.location（真值）。
  const catParam = $derived(liveQueryParam('cat'));

  type SettingsEntry = { id: string; label: string; href: string; icon: string };

  const entries: SettingsEntry[] = [
    { id: 'libraries', label: '资源库', href: '/libraries', icon: 'folder' },
    { id: 'appearance', label: '外观', href: '/settings?cat=appearance', icon: 'sun' },
    { id: 'content', label: '内容管理', href: '/settings?cat=content', icon: 'shield' },
    { id: 'tools', label: '外部工具', href: '/settings?cat=tools', icon: 'wrench' },
    { id: 'thumbnail', label: '缩略图', href: '/settings?cat=thumbnail', icon: 'image' },
    { id: 'ai', label: 'AI 配置', href: '/settings?cat=ai', icon: 'spark' },
    { id: 'scrape', label: '刮削', href: '/settings?cat=scrape', icon: 'clapper' },
    { id: 'player', label: '播放器', href: '/settings?cat=player', icon: 'play' },
    { id: 'subtitle', label: '字幕', href: '/settings?cat=subtitle', icon: 'subtitle' },
    { id: 'database', label: '数据库', href: '/settings?cat=database', icon: 'database' },
    { id: 'about', label: '关于', href: '/settings?cat=about', icon: 'info' }
  ];

  const activeId = $derived(
    pathname.startsWith('/libraries')
      ? 'libraries'
      : catParam || 'appearance'
  );

  function goTo(href: string): void {
    goto(href);
  }

</script>

<div class="sidebar-scroll">
  <section class="section">
    <div class="section-head" data-tip="设置">
      <svg class="sec-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="8" cy="8" r="2.2"></circle>
        <path d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1M12.6 12.6l-1.1-1.1M4.5 4.5L3.4 3.4"></path>
      </svg>
      {#if !collapsed}<span class="sec-title">设置</span>{/if}
    </div>

    {#snippet entryIcon(icon: string)}
      {#if icon === 'folder'}
        <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5z"/>
      {:else if icon === 'sun'}
        <circle cx="8" cy="8" r="2.7"/>
        <path d="M8 1.5v1.4M8 13.1v1.4M1.5 8h1.4M13.1 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1" stroke-linecap="round"/>
      {:else if icon === 'shield'}
        <path d="M8 2l5 1.7v3.2c0 3-1.7 5.3-5 7.1-3.3-1.8-5-4.1-5-7.1V3.7z"/>
      {:else if icon === 'wrench'}
        <path d="M7.3 6.3a1 1 0 0 0 0 1.4l.8.8a1 1 0 0 0 1.4 0l3.8-3.8a4 4 0 0 1-5.6 5.6L4 13.6a1.5 1.5 0 0 1-2.1-2.1l3.3-3.3a4 4 0 0 1 2.1-1.9z"/>
      {:else if icon === 'image'}
        <rect x="2" y="2.5" width="12" height="11" rx="1.5"/>
        <circle cx="6" cy="6.5" r="1.2"/>
        <path d="M2 11.5l4-3 3 2.5 3-2 2 1.5" stroke-linecap="round"/>
      {:else if icon === 'spark'}
        <path d="M8 1.8l1.6 4.6 4.6 1.6-4.6 1.6L8 14.2l-1.6-4.6L1.8 8l4.6-1.6z" stroke-linejoin="round"/>
      {:else if icon === 'clapper'}
        <path d="M13.8 3.5H2.2a.7.7 0 0 0-.7.7v7.6a.7.7 0 0 0 .7.7h11.6a.7.7 0 0 0 .7-.7V4.2a.7.7 0 0 0-.7-.7z"/>
        <path d="M2 7h12M6 3.5v8.5M10 3.5v8.5" stroke-opacity=".5"/>
      {:else if icon === 'play'}
        <circle cx="8" cy="8" r="6"/>
        <path d="M6.5 5.5l4 2.5-4 2.5z" fill="currentColor" stroke="none"/>
      {:else if icon === 'subtitle'}
        <rect x="2" y="3" width="12" height="10" rx="1.5"/>
        <path d="M4.5 10h3M8 10h3.5" stroke-linecap="round"/>
      {:else if icon === 'database'}
        <ellipse cx="8" cy="3.5" rx="5.5" ry="2"/>
        <path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9"/>
        <path d="M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" stroke-opacity=".5"/>
      {:else if icon === 'info'}
        <circle cx="8" cy="8" r="6"/>
        <path d="M8 7.2V11M8 5.2v.2" stroke-linecap="round"/>
      {/if}
    {/snippet}

    {#each entries as entry (entry.id)}
      <button
        class="item"
        class:active={activeId === entry.id}
        data-tip={entry.label}
        onclick={() => goTo(entry.href)}
      >
        <svg class="item-icon" viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          {@render entryIcon(entry.icon)}
        </svg>
        {#if !collapsed}<span class="item-label">{entry.label}</span>{/if}
      </button>
    {/each}
  </section>

  {#if !collapsed}
    <section class="section">
      <div class="empty-hint">设置修改会自动保存。</div>
    </section>
  {/if}
</div>
