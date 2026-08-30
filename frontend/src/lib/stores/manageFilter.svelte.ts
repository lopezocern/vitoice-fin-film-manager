// 管理页筛选状态持久化（会话级）
//
// 背景：在管理页设置筛选 → 进入详情 → 返回时 MediaManageView 组件重建，
// 筛选状态（类型/标签/状态/来源/排序/分页）仅存于组件 $state，全部丢失。
// 此 store 与媒体页 mediaScroll 类似，在组件重建时恢复；
// URL 显式参数（lib/dir/source/status，侧边栏/仪表盘外部入口）优先于 store。
//
// 注意：module 级 $state 必须通过对象引用导出（裸 rune 只读）。
import type { MediaSortField } from '$lib/api/media';

export type ManageStatusFilter = '' | 'rated' | 'unrated' | 'favorite' | 'untagged' | 'problem' | 'missing' | 'unmatched';

export interface ManageFilterState {
  filterLib: string;
  filterDir: string;
  filterType: string;
  filterTags: string[];
  filterTagType: number | '';
  filterStatus: ManageStatusFilter;
  filterSource: string;
  sortField: MediaSortField;
  sortOrder: 'asc' | 'desc';
  view: 'list' | 'grid';
  page: number;
  pageSize: number;
  scrollTop: number;
  /** 是否保存过有效状态（false = 从未设置，保持默认值） */
  hasState: boolean;
}

const defaultState: ManageFilterState = {
  filterLib: '',
  filterDir: '',
  filterType: '',
  filterTags: [],
  filterTagType: '',
  filterStatus: '',
  filterSource: '',
  sortField: 'created_at',
  sortOrder: 'desc',
  view: 'list',
  page: 1,
  pageSize: 50,
  scrollTop: 0,
  hasState: false,
};

const state = $state<ManageFilterState>({ ...defaultState });

export const manageFilterStore = {
  get state(): ManageFilterState {
    return state;
  },
  save(next: Partial<ManageFilterState>): void {
    Object.assign(state, next);
    state.hasState = true;
  },
  clear(): void {
    Object.assign(state, { ...defaultState, hasState: false });
  },
};
