<script lang="ts">
  // /tags 路由已合并到 /manage?tab=tags
  // 保留此文件用于重定向，避免书签 404
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  onMount(() => {
    goto('/manage?tab=tags', { replaceState: true });
  });
</script>

<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--ink-tertiary)">
  正在跳转到标签管理…
</div>
