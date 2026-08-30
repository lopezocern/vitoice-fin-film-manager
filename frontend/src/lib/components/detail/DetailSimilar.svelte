<script lang="ts">
  // 详情页相似内容区：基于标签匹配的推荐媒体网格
  //
  // 相似内容逻辑（实现在 detail/[id]/+page.svelte 的 loadMedia 函数中）：
  //   1. 取当前媒体的所有标签 ID 作为过滤条件
  //   2. 调用 GET /media?tag_ids=1,2,3（OR 语义：匹配任意一个标签即可）
  //   3. 排除当前媒体自身
  //   4. 取前 6 条结果作为推荐
  //   5. 当媒体没有标签时不显示相似内容（similar 为空数组）
  //
  // 注意：当前实现是简单的标签 OR 匹配，不计算标签重叠数量排序。
  // 若需更精确的推荐（如按共享标签数量排序），可在后端新增 /media/{id}/similar 端点。
  import { mediaApi, isAvMedia, type Media } from '$lib/api/media';

  let {
    similar,
    onnavigate
  }: {
    similar: Media[];
    onnavigate?: (id: string) => void;
  } = $props();
</script>

<section class="section">
  <div class="section-head">
    <h2 class="section-title">相似内容</h2>
    {#if similar.length > 0}
      <span class="section-count">{similar.length}</span>
    {/if}
  </div>
  {#if similar.length > 0}
    <div class="similar-grid">
      {#each similar as s (s.id)}
        <button class="similar-card" onclick={() => onnavigate?.(s.id)}>
          <div class="similar-thumb" class:av-poster={isAvMedia(s)}>
            {#if s.poster}
              <img src={mediaApi.posterUrl(s.id, s.updated_at)} alt={s.title ?? s.filename} loading="lazy" />
            {:else if s.thumbnail}
              <img src={mediaApi.thumbnailUrl(s.id, s.updated_at)} alt={s.filename} loading="lazy" />
            {:else}
              <span class="similar-fallback">{s.type === 'video' ? '▶' : s.type === 'audio' ? '♪' : '▣'}</span>
            {/if}
          </div>
          <div class="similar-title" title={s.title ?? s.filename}>{s.title ?? s.filename}</div>
        </button>
      {/each}
    </div>
  {:else}
    <div class="section-empty">暂无相似内容</div>
  {/if}
</section>

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

  .section-count {
    font-size: 11px;
    color: var(--muted);
    background: var(--bg-soft);
    padding: 1px 8px;
    border-radius: var(--radius-full);
  }

  .section-empty {
    padding: 16px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    background: var(--bg-soft);
    border-radius: var(--radius);
  }

  /* ---- 相似内容 ---- */
  .similar-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 12px;
  }

  @media (max-width: 1250px) {
    .similar-grid {
      grid-template-columns: repeat(4, 1fr);
    }
  }

  @media (max-width: 900px) {
    .similar-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  .similar-card {
    background: var(--bg2);
    border: 1px solid var(--rule);
    border-radius: var(--radius-card);
    overflow: hidden;
    cursor: pointer;
    padding: 0;
    text-align: left;
    transition: transform 200ms ease, box-shadow 200ms ease, border-color 200ms;
  }

  .similar-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.1);
    border-color: var(--accent);
  }

  .similar-thumb {
    aspect-ratio: 2 / 3;
    background: var(--bg-soft);
    overflow: hidden;
  }

  .similar-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .similar-thumb.av-poster {
    aspect-ratio: 3 / 2;
  }

  .similar-thumb.av-poster img {
    object-fit: contain;
  }

  .similar-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 24px;
    background: linear-gradient(135deg, var(--bg-soft), var(--bg2));
  }

  .similar-title {
    padding: 6px 8px 8px;
    font-size: 12px;
    color: var(--ink);
    font-weight: 500;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
</style>
