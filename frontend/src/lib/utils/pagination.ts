/**
 * Pagination helpers shared by the media grid and the manage table.
 *
 * Both pages used to inline an identical `pageList` plus a copy of the
 * "how many page buttons fit in this width" formula. The formula is the same;
 * only the pixel budget differs (the manage pager also renders a "共 N 项"
 * counter), so the budget is a parameter rather than a constant.
 */

/** Pixel budget of a pager row, measured once per pager layout. */
export interface PagerMetrics {
  /** One page button plus its gap. */
  btnWidth: number;
  /** Prev + next buttons. */
  navWidth: number;
  /** Both ellipsis slots. */
  ellipsisWidth: number;
  /** Right-hand controls (page-size select, item counter). */
  rightWidth: number;
  /** Container padding + gap + border slack. */
  padding: number;
}

export interface PagerLimits {
  min: number;
  max: number;
  /** Used before the container has been measured. */
  fallback: number;
}

export const DEFAULT_PAGER_LIMITS: PagerLimits = { min: 5, max: 15, fallback: 15 };

/** Media grid pager budget. */
export const MEDIA_PAGER_METRICS: PagerMetrics = {
  btnWidth: 36,
  navWidth: 72, // 上一页+下一页(34*2 + 间距)
  ellipsisWidth: 32, // 两个省略号
  rightWidth: 150, // 右侧每页下拉区
  padding: 78 // padding 32*2 + gap 12 + 边框余量
};

/** Manage table pager budget — wider than the media one (item counter). */
export const MANAGE_PAGER_METRICS: PagerMetrics = {
  btnWidth: 36,
  navWidth: 64, // 上一页+下一页
  ellipsisWidth: 32, // 两个省略号
  rightWidth: 190, // 右侧每页下拉区(管理页含"共 N 项"文本,比 media 页宽)
  padding: 68 // padding + gap
};

/**
 * Build the visible page list: first page, last page, a window around the
 * current page, and `…` markers for the gaps.
 */
export function pageList(current: number, totalPages: number, maxVisible: number): (number | string)[] {
  if (totalPages <= maxVisible) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const pages: (number | string)[] = [1];
  // 当前页左右窗口:总窗口 = 首尾各1 + 当前页1 + 左右 half*2
  const half = Math.max(1, Math.floor((maxVisible - 3) / 2));
  let left = Math.max(2, current - half);
  let right = Math.min(totalPages - 1, current + half);
  // 窗口靠近边缘时向另一侧扩展,保持窗口饱满
  if (right - left + 1 < maxVisible - 2) {
    const slack = maxVisible - 2 - (right - left + 1);
    if (left === 2) right = Math.min(totalPages - 1, right + slack);
    else if (right === totalPages - 1) left = Math.max(2, left - slack);
  }
  if (left > 2) pages.push('…');
  for (let i = left; i <= right; i++) pages.push(i);
  if (right < totalPages - 1) pages.push('…');
  pages.push(totalPages);
  return pages;
}

/**
 * How many page buttons fit in `width`, clamped to `limits`.
 * A width of 0 means "not measured yet" → `limits.fallback`.
 */
export function maxVisiblePages(
  width: number,
  metrics: PagerMetrics,
  limits: PagerLimits = DEFAULT_PAGER_LIMITS
): number {
  if (width <= 0) return limits.fallback;
  const usable = width - metrics.padding - metrics.rightWidth - metrics.navWidth - metrics.ellipsisWidth;
  return Math.max(limits.min, Math.min(limits.max, Math.floor(usable / metrics.btnWidth)));
}
