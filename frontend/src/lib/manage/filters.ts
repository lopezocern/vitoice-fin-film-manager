/**
 * Pure filter helpers for the manage table.
 *
 * Extracted from MediaManageView so the rules can be unit-tested without a
 * component host. The media grid has its own, *different* client-side filter
 * (resolution / duration buckets) — do not merge the two.
 */
import type { Media, MediaSortField } from '$lib/api/media';
import type { Tag } from '$lib/api/tags';

export type StatusFilter =
  | ''
  | 'rated'
  | 'unrated'
  | 'favorite'
  | 'untagged'
  | 'problem'
  | 'missing'
  | 'unmatched';

/** Everything the list request needs, in one plain object. */
export interface ManageQueryState {
  sortField: MediaSortField;
  sortOrder: 'asc' | 'desc';
  page: number;
  pageSize: number;
  libraryId: string;
  dir: string;
  type: string;
  tags: string[];
  status: StatusFilter;
  source: string;
}

/**
 * Build the query params for the media list endpoint.
 *
 * `missing` is expressible server-side (`file_missing`); `untagged` /
 * `problem` / `unmatched` are not, so they are handled by
 * {@link applyClientFilters} after the response arrives.
 */
export function buildManageParams(s: ManageQueryState): Record<string, unknown> {
  const p: Record<string, unknown> = {
    sort: s.sortField,
    order: s.sortOrder,
    page: s.page,
    page_size: s.pageSize
  };
  if (s.libraryId) p.library_id = s.libraryId;
  if (s.dir) p.dir = s.dir;
  if (s.type) p.type = s.type;
  if (s.tags.length) p.tags = s.tags;
  if (s.status === 'favorite') p.favorite = true;
  if (s.status === 'rated') p.rating_min = 1;
  if (s.status === 'unrated') p.rating_max = 0;
  if (s.status === 'missing') p.file_missing = true;
  if (s.source === 'local') p.source = 'local';
  if (s.source === 'network') p.source = 'network';
  if (s.source === 'missing') p.file_missing = true;
  return p;
}

/** Second-pass filter for statuses the backend cannot express. */
export function applyClientFilters(list: Media[], status: StatusFilter): Media[] {
  if (status === 'untagged') {
    return list.filter((m) => !m.tags || m.tags.length === 0);
  }
  if (status === 'problem') {
    return list.filter((m) => m.file_missing || !m.poster || !m.scrape_data);
  }
  if (status === 'unmatched') {
    return list.filter((m) => !m.poster && !m.scrape_data);
  }
  return list;
}

/**
 * Keep only the sub-trees matching `typeId`. A node that matches keeps its
 * whole sub-tree; a node that does not match is dropped and any matching
 * descendants are promoted to its place.
 */
export function filterTreeByType(nodes: Tag[], typeId: number): Tag[] {
  const out: Tag[] = [];
  for (const n of nodes) {
    if (n.tag_type_id === typeId) {
      out.push(n);
    } else if (n.children?.length) {
      const kids = filterTreeByType(n.children, typeId);
      if (kids.length) out.push(...kids);
    }
  }
  return out;
}
