/**
 * Column definitions for the asset table.
 *
 * Kept as data (not markup) so the table, the grid's meta line and any future
 * export can agree on what "a column" is. `sortField` is the backend sort key;
 * columns without one are not sortable.
 */
import type { MediaSortField } from '$lib/api/media';

export type AssetColumnId =
  | 'asset'
  | 'state'
  | 'library'
  | 'tags'
  | 'duration'
  | 'size'
  | 'rating'
  | 'actions';

export interface AssetColumn {
  id: AssetColumnId;
  label: string;
  /** CSS grid track size. The table renders itself as a grid, not a <table>,
   *  so rows can be virtualised later without changing the markup model. */
  track: string;
  sortField?: MediaSortField;
  align?: 'left' | 'right' | 'center';
  /** Hidden below this container width (managed by CSS, declared here for docs). */
  collapseAt?: 'sm' | 'md';
  /** 允许用户在「列」里关掉。`asset`（标题/封面）与 `actions` 常驻，
   *  否则关掉后整行就剩不下可点的东西了。 */
  hideable?: boolean;
}

export const ASSET_COLUMNS: readonly AssetColumn[] = [
  { id: 'asset', label: '资产', track: 'minmax(220px, 1.6fr)' },
  { id: 'state', label: '状态', track: 'minmax(150px, 0.9fr)', hideable: true },
  { id: 'library', label: '资源库', track: 'minmax(110px, 0.7fr)', collapseAt: 'md', hideable: true },
  { id: 'tags', label: '标签', track: 'minmax(150px, 1fr)', collapseAt: 'md', hideable: true },
  {
    id: 'duration',
    label: '时长',
    track: '76px',
    sortField: 'duration',
    align: 'right',
    collapseAt: 'sm',
    hideable: true
  },
  {
    id: 'size',
    label: '大小',
    track: '86px',
    sortField: 'size',
    align: 'right',
    collapseAt: 'sm',
    hideable: true
  },
  { id: 'rating', label: '评分', track: '78px', sortField: 'rating', align: 'center', hideable: true },
  { id: 'actions', label: '', track: '158px', align: 'right' }
] as const;

/** 可被用户隐藏的列（供「列」菜单渲染勾选项）。 */
export const HIDEABLE_COLUMNS = ASSET_COLUMNS.filter((c) => c.hideable);

/**
 * 过滤出真正要渲染的列。
 *
 * 纯函数，`hidden` 里的未知 id 会被忽略（旧版本存下的列名不匹配新代码时
 * 不应该把整个表搞崩）；不可隐藏的列即使出现在 `hidden` 里也强制显示。
 */
export function visibleColumns(
  all: readonly AssetColumn[] = ASSET_COLUMNS,
  hidden: Iterable<string> = []
): AssetColumn[] {
  const hiddenSet = new Set(hidden);
  return all.filter((c) => !c.hideable || !hiddenSet.has(c.id));
}

/** 给定列集合的 `grid-template-columns`。 */
export function gridTemplate(columns: readonly AssetColumn[]): string {
  return columns.map((c) => c.track).join(' ');
}

/** `grid-template-columns` for the default（全可见）header and every row. */
export const ASSET_GRID_TEMPLATE = gridTemplate(ASSET_COLUMNS);

export const SORTABLE_COLUMNS = ASSET_COLUMNS.filter((c) => c.sortField);
