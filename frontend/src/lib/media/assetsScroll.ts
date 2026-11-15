/**
 * 记住资产工作台的滚动位置。
 *
 * 背景：旧管理页用 `manageFilterStore.scrollTop` 做同一件事，但那个 store 同时
 * 塞了筛选/排序/分页，导致职责混杂。这里只存"滚动偏移"，按 section+view 分区，
 * 并在 localStorage 里持久化（刷新后也能回到原处）。
 *
 * 刻意不放进 `MediaQueryState`：滚动位置不是查询条件，不该进 URL，也不该触发
 * 重新取数。
 */
const KEY = 'vitoice.assets.scroll';

type ScrollMap = Record<string, number>;

function read(): ScrollMap {
  if (typeof localStorage === 'undefined') return {};
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as ScrollMap) : {};
  } catch {
    return {};
  }
}

function write(map: ScrollMap): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(KEY, JSON.stringify(map));
  } catch {
    // 配额满/隐私模式：滚动位置丢了不影响功能
  }
}

/** 分区键：同一视图的不同筛选各自记住位置没有意义，按 section+view 分即可。 */
export function scrollKey(section: string, view: string): string {
  return `${section}:${view}`;
}

export function saveScroll(key: string, top: number): void {
  const map = read();
  map[key] = Math.max(0, Math.round(top));
  write(map);
}

export function loadScroll(key: string): number {
  return read()[key] ?? 0;
}
