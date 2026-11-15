/**
 * Media status vocabulary — the single definition of "what state is this item in".
 *
 * Before this module there were three copies of the same taxonomy:
 *   - `lib/manage/filters.ts`  `StatusFilter` (8 values)          ← PR6 删除
 *   - `manage/MediaManageView.svelte` `statusOptions` (同一套 8 值) ← PR6 删除
 *   - `manage/OverviewView.svelte`  `assetFilter` (4 值，命名不同)  ← PR5 已删除
 * They had already started to disagree. Everything status-related lives here now.
 *
 * Two kinds of status exist and they compose:
 *
 *   issue view  — *why* the item needs attention (missing file, no poster, …)
 *                 → a Saved View; mutually exclusive, drives the list scope.
 *   attribute   — *what the user did with it* (rated / unrated / favorite)
 *                 → orthogonal; can be combined with any issue view
 *                 ("untagged AND rated" is a legitimate query).
 */
import type { Media } from '$lib/api/media';

/** Why an item needs attention. One at a time; see `lib/media/views.ts`. */
export type SavedViewId =
  | 'all'
  | 'problem'
  | 'missing'
  | 'no_poster'
  | 'metadata'
  | 'ignored'
  | 'untagged';

/**
 * User-data attribute filters.
 *
 * Deliberately kept OUT of `SavedViewId`: unlike an issue view these stack
 * with one another and with any issue view.
 */
export type AttributeStatus = '' | 'rated' | 'unrated' | 'favorite';

/** Tone hints for badges/chips, so colour choices live in one place too. */
export type StatusTone = 'neutral' | 'ok' | 'warn' | 'danger';

export const ATTRIBUTE_LABELS: Record<AttributeStatus, string> = {
  '': '全部状态',
  rated: '已评分',
  unrated: '未评分',
  favorite: '收藏'
};

export const TONE_CLASS: Record<StatusTone, string> = {
  neutral: '',
  ok: 'ok',
  warn: 'warn',
  danger: 'danger'
};

/**
 * Human-readable state of one media row, for table cells and chips.
 *
 * Mirrors the backend predicates in `app/services/media_query.py` so a cell
 * never claims something the filter disagrees with.
 */
export interface MediaStateChips {
  file: { label: string; tone: StatusTone };
  metadata: { label: string; tone: StatusTone };
}

export function mediaStateChips(media: Media): MediaStateChips {
  const isEpisode = Boolean(media.series_id);
  const ignored = Boolean(media.metadata_ignored);

  const file = media.file_missing
    ? { label: '文件缺失', tone: 'danger' as StatusTone }
    : {
        label: media.source_type === 'network' ? '网络源' : '本地正常',
        tone: 'ok' as StatusTone
      };

  // Episodes inherit artwork/metadata from their parent series — reporting them
  // as incomplete individually would flood the table with false alarms.
  if (isEpisode) {
    return { file, metadata: { label: '随系列', tone: 'neutral' } };
  }
  if (ignored) {
    return { file, metadata: { label: '已忽略', tone: 'neutral' } };
  }
  if (!media.poster && !media.scrape_data) {
    return { file, metadata: { label: '待补全', tone: 'danger' } };
  }
  if (!media.poster) {
    return { file, metadata: { label: '缺封面', tone: 'warn' } };
  }
  if (!media.scrape_data) {
    return { file, metadata: { label: '缺元数据', tone: 'warn' } };
  }
  return { file, metadata: { label: '完整', tone: 'ok' } };
}
