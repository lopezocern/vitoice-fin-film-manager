// 媒体页共享类型定义

export type ResolutionFilter = '4k' | '1080p' | '720p' | '480p' | 'other' | '';
export type DurationFilter = 'short' | 'medium' | 'long' | '';

export interface FilterState {
  type?: string;
  genre?: string;
  country?: string;
  year?: number;
  resolution?: ResolutionFilter;
  ratingMin?: number;
  duration?: DurationFilter;
  tags?: string[];
}

export type SortField = 'created_at' | 'filename' | 'rating' | 'duration' | 'progress';

export interface SortState {
  field: SortField;
  order: 'asc' | 'desc';
}

export type ContentSection = 'all' | 'movie' | 'tv' | 'image' | 'audio';
export type ViewMode = 'mixed' | 'poster' | 'list' | 'timeline';

// 从媒体 metadata 中读取播放进度（0-100）
// M11 fix: MediaResponse 的 playback_position 以「秒」为单位（normalizeMedia
// 会写入 metadata.progress/playback_position）。当 duration 可用时按秒换算为
// 百分比；无 duration 的旧数据（progress 已是 0-100）则原样 clamp，保持兼容。
export function getProgress(meta?: Record<string, unknown>): number {
  if (!meta) return 0;
  const pos =
    meta.playback_position ?? meta.progress ?? meta.playback_progress ?? meta.position;
  if (typeof pos !== 'number' || !Number.isFinite(pos) || pos <= 0) return 0;
  const dur = typeof meta.duration === 'number' ? meta.duration : 0;
  if (Number.isFinite(dur) && dur > 0) {
    return Math.max(0, Math.min(100, (pos / dur) * 100));
  }
  return Math.max(0, Math.min(100, pos));
}

// 分辨率档位判定
export function resolutionBucket(width?: number, height?: number): ResolutionFilter {
  const h = height ?? 0;
  if (h >= 2160) return '4k';
  if (h >= 1080) return '1080p';
  if (h >= 720) return '720p';
  if (h >= 480) return '480p';
  if (h > 0) return 'other';
  return '';
}

// 过滤选项（从后端 /media/filters 获取）
export interface FilterOptions {
  genres: string[];
  countries: string[];
  years: number[];
}
