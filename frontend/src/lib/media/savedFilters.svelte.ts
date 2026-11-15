/**
 * 自定义筛选的持久化 store（localStorage）。
 *
 * 为什么放 localStorage 而不是后端：这是"这台机器上的个人快捷方式"，
 * 不是库配置；放后端要么加表要么塞设置项，都会让一次私人调整牵连全局状态。
 * 代价是换机器不跟随——如果以后要多端共享，再把这里换成 API 即可，
 * 上层只依赖 `savedFilters.items / save / remove`。
 */
import type { MediaQueryState } from './query';
import { isSavedFilter, normalizeName, toFilterState, type SavedFilter } from './savedFilters';

const STORAGE_KEY = 'vitoice.assets.savedfilters';
/** 上限：下拉里太多就失去"快捷"的意义，也避免把 localStorage 写爆。 */
const MAX_FILTERS = 30;

function read(): SavedFilter[] {
  if (typeof localStorage === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isSavedFilter).slice(0, MAX_FILTERS);
  } catch {
    return [];
  }
}

function write(items: SavedFilter[]): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // 配额/隐私模式：失败不影响本次会话内使用
  }
}

let items = $state<SavedFilter[]>(read());

export const savedFilters = {
  get items(): SavedFilter[] {
    return items;
  },
  /** 保存当前筛选；同名会覆盖（避免"我的筛选 1/2/3"堆积）。 */
  save(name: string, query: MediaQueryState): SavedFilter | null {
    const normalized = normalizeName(name);
    if (!normalized) return null;
    const existing = items.find((f) => f.name === normalized);
    const entry: SavedFilter = {
      id: existing?.id ?? `sf_${Date.now().toString(36)}`,
      name: normalized,
      filter: toFilterState(query)
    };
    const next = existing ? items.map((f) => (f.id === entry.id ? entry : f)) : [...items, entry];
    items = next.slice(0, MAX_FILTERS);
    write(items);
    return entry;
  },
  remove(id: string): void {
    items = items.filter((f) => f.id !== id);
    write(items);
  },
  /** 仅测试/重置用。 */
  clear(): void {
    items = [];
    write(items);
  }
};
