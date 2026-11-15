/**
 * Saved Views — the eight "why am I looking at this list" presets.
 *
 * A view is *only* a set of query parameters plus the stats field that badges
 * it. Everything else (sorting, paging, bulk actions, extra filters) is shared,
 * which is what lets the manage page keep one list implementation instead of
 * one per problem type.
 *
 * Invariant enforced by `views.test.ts` and by the backend guard-rail
 * (`tests/test_media_issue_filters.py`): for every view, the number shown on
 * the badge (the `countKey` field of `/stats/summary`) must equal the `total`
 * of the list this view requests.
 */
import type { SavedViewId, StatusTone } from './status';

/** Field of `GET /api/stats/summary` that counts this view. */
export type StatsCountKey =
  | 'media_count'
  | 'problem_count'
  | 'missing_count'
  | 'no_poster_count'
  | 'no_metadata_count'
  | 'ignored_count'
  | 'untagged_count';

export interface SavedView {
  id: SavedViewId;
  label: string;
  /** Shown in the empty state / tooltip. */
  hint: string;
  /** `null` when the backend has no matching count (yet). */
  countKey: StatsCountKey | null;
  tone: StatusTone;
}

export const SAVED_VIEWS: readonly SavedView[] = [
  {
    id: 'all',
    label: '全部资产',
    hint: '媒体库里的全部条目',
    countKey: 'media_count',
    tone: 'neutral'
  },
  {
    id: 'problem',
    label: '存在问题',
    hint: '文件缺失、缺封面、元数据不全的并集（同一项只算一次）',
    countKey: 'problem_count',
    tone: 'danger'
  },
  {
    id: 'missing',
    label: '文件缺失',
    hint: '本地文件已不在，但记录仍保留',
    countKey: 'missing_count',
    tone: 'danger'
  },
  {
    id: 'no_poster',
    label: '缺封面',
    hint: '既没有海报也没有缩略图',
    countKey: 'no_poster_count',
    tone: 'warn'
  },
  {
    id: 'metadata',
    label: '元数据待处理',
    hint: '还缺刮削数据或封面，等待补全',
    countKey: 'no_metadata_count',
    tone: 'warn'
  },
  {
    id: 'ignored',
    label: '已忽略刮削',
    hint: '你显式放弃刮削的条目，可批量恢复',
    countKey: 'ignored_count',
    tone: 'neutral'
  },
  {
    id: 'untagged',
    label: '无标签',
    hint: '一个标签都没有的条目',
    countKey: 'untagged_count',
    tone: 'neutral'
  }
] as const;

/** Every view id, in display order. */
export const VIEW_IDS: readonly SavedViewId[] = SAVED_VIEWS.map((v) => v.id);

const BY_ID = new Map<SavedViewId, SavedView>(SAVED_VIEWS.map((v) => [v.id, v]));

export function isSavedViewId(value: unknown): value is SavedViewId {
  return typeof value === 'string' && BY_ID.has(value as SavedViewId);
}

/** Lookup that never returns undefined — unknown ids fall back to `all`. */
export function savedView(id: string | null | undefined): SavedView {
  if (id && BY_ID.has(id as SavedViewId)) return BY_ID.get(id as SavedViewId)!;
  return BY_ID.get('all')!;
}

/** Views that represent an actionable problem (used for badge emphasis). */
export const PROBLEM_VIEW_IDS: readonly SavedViewId[] = ['problem', 'missing', 'no_poster', 'metadata'];
