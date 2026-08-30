// 图片加载失败回退工具。
// 海报图失败 → 回退到缩略图；缩略图也失败 → 隐藏图片（露出占位背景/图标）。
import { mediaApi } from '$lib/api/media';

/**
 * 海报/缩略图 img onerror 回退。
 * 第一次失败：若媒体有缩略图则切到缩略图 URL；第二次失败（或原图就是缩略图）→ 隐藏。
 */
export function imageFallback(e: Event, media: { id: string; thumbnail?: string | null; updated_at?: string | null }): void {
  const img = e.currentTarget as HTMLImageElement | null;
  if (!img) return;
  if (img.dataset.fb !== 'thumb') {
    img.dataset.fb = 'thumb';
    if (media.thumbnail) {
      img.src = mediaApi.thumbnailUrl(media.id, media.updated_at ?? undefined);
      return;
    }
  }
  // 已是缩略图或没有缩略图 → 隐藏（露出占位）
  img.style.display = 'none';
}

/** Fall back from a Series poster to the episode's own poster and thumbnail. */
export function seriesCoverFallback(
  e: Event,
  media: { id: string; poster?: string | null; thumbnail?: string | null; updated_at?: string | null }
): void {
  const img = e.currentTarget as HTMLImageElement | null;
  if (!img) return;
  if (img.dataset.fb !== 'poster' && media.poster) {
    img.dataset.fb = 'poster';
    img.src = mediaApi.posterUrl(media.id, media.updated_at ?? undefined);
    return;
  }
  if (img.dataset.fb !== 'thumb' && media.thumbnail) {
    img.dataset.fb = 'thumb';
    img.src = mediaApi.thumbnailUrl(media.id, media.updated_at ?? undefined);
    return;
  }
  img.style.display = 'none';
}
