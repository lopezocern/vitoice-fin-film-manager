<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  onMount(() => {
    goto('/media', { replaceState: true });
  });
</script>

<div class="flex h-screen items-center justify-center text-muted">
  正在跳转到媒体库...
</div>
