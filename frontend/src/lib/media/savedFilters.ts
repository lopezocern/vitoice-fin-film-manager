/**
 * 保存的自定义筛选（Saved Filter）。
 *
 * 与 7 个内置 Saved View 的区别：内置视图是"服务端口径"的固定语义（有问题 / 缺封面…），
 * 这里的筛选是用户自己拼出来的组合（库 + 目录 + 标签 + 评分区间 + 搜索词…），
 * 存下来当快捷入口用，比如"AZV 里没封面且评分≥4 的"。
 *
 * 存哪些字段是刻意的：**分页与展示形态不属于筛选**。
 * 把 `page` 存进去会导致"点开筛选取到的却是第 7 页"，把 `display` 存进去会让
 * 用户在表格里保存的筛选强行切掉别人的网格视图。
 */

import { DEFAULT_MEDIA_QUERY, type MediaQueryState } from './query';

/** 属于"筛选"的字段：保存与恢复都只碰这些（与 MediaQueryState 的实际字段名一致）。 */
export const FILTER_FIELDS = [
  'view',
  'libraryId',
  'dir',
  'section',
  'genre',
  'country',
  'year',
  'resolution',
  'duration',
  'ratingMin',
  'attribute',
  'tags',
  'tagMatch',
  'tagTypeId',
  'source',
  'q',
  'sort',
  'order'
] as const satisfies readonly (keyof MediaQueryState)[];

export interface SavedFilter {
  id: string;
  name: string;
  /** 只含 FILTER_FIELDS 的字段快照 */
  filter: Partial<MediaQueryState>;
}

/** 从当前查询状态里截出"筛选部分"（深拷贝数组，避免共享引用）。 */
export function toFilterState(query: MediaQueryState): Partial<MediaQueryState> {
  const out: Record<string, unknown> = {};
  for (const key of FILTER_FIELDS) {
    const value = query[key];
    out[key] = Array.isArray(value) ? [...value] : value;
  }
  return out as Partial<MediaQueryState>;
}

/**
 * 把保存的筛选合并回当前状态：分页回到第 1 页，展示形态保持不变。
 * 未出现在快照里的字段回落默认值——否则"取消某个筛选"永远无法通过保存的条目完成。
 */
export function applyFilter(current: MediaQueryState, filter: Partial<MediaQueryState>): MediaQueryState {
  // 先保留展示形态（display/pageSize），再把所有筛选字段重置成默认值，
  // 最后套用快照——这样"快照里没有的筛选"一定会被清掉，
  // 否则保存的条目永远无法表达"不要某个条件"。
  const next: MediaQueryState = { ...current };
  for (const key of FILTER_FIELDS) {
    const fallback = DEFAULT_MEDIA_QUERY[key];
    (next as unknown as Record<string, unknown>)[key] = Array.isArray(fallback) ? [...fallback] : fallback;
  }
  for (const key of FILTER_FIELDS) {
    if (key in filter) {
      const value = filter[key];
      (next as unknown as Record<string, unknown>)[key] = Array.isArray(value) ? [...value] : value;
    }
  }
  next.page = 1;
  next.display = current.display;
  next.pageSize = current.pageSize;
  return next;
}

/** 校验来自 localStorage 的条目；结构不对就丢弃，宁可少一条也不能让页面崩。 */
export function isSavedFilter(value: unknown): value is SavedFilter {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === 'string' &&
    v.id.length > 0 &&
    typeof v.name === 'string' &&
    v.name.trim().length > 0 &&
    typeof v.filter === 'object' &&
    v.filter !== null
  );
}

/** 名称规整：去首尾空白、折叠内部空白、限制长度（防止一行撑爆下拉）。 */
export function normalizeName(raw: string): string {
  return raw.trim().replace(/\s+/g, ' ').slice(0, 24);
}
