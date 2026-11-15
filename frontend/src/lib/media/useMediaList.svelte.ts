/**
 * Data layer for one media list.
 *
 * Both the manage table and (later) the media grid read media the same way:
 * build params from a `MediaQueryState`, fetch one page, keep the server's
 * `total`. There is deliberately **no client-side filtering** — before PR1 the
 * manage view fetched 200 rows and filtered in the browser, which made paging
 * and the badge counts lie.
 *
 * Concurrency: requests are numbered; a newer request invalidates older ones
 * (the previous implementation used the same `reqId` pattern for the same
 * reason — fast filter changes otherwise render stale rows).
 */
import { mediaApi, type Media } from '$lib/api/media';
import { buildMediaQuery, type MediaQueryState } from './query';
import { delay, shouldRetry, timeoutError, withTimeout } from './listRequest';

export interface MediaListOptions {
  /** Read the current query state. A function (not a value) so the caller's
   *  `$state` is read at request time instead of captured at construction. */
  getState: () => MediaQueryState;
  /** Called after a successful load (selection pruning, scroll restore, …). */
  onLoaded?: (items: Media[], total: number) => void;
}

export interface MediaList {
  readonly items: Media[];
  readonly total: number;
  readonly loading: boolean;
  readonly error: string | null;
  /** True once a request has completed (so empty states do not flash). */
  readonly loaded: boolean;
  reload: () => Promise<void>;
}

export function createMediaList(options: MediaListOptions): MediaList {
  let items = $state<Media[]>([]);
  let total = $state(0);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let loaded = $state(false);
  let reqId = 0;

  async function reload(): Promise<void> {
    const id = ++reqId;
    loading = true;
    error = null;
    const params = buildMediaQuery(options.getState());

    // 超时保护 + 只重试一次：后端卡住时不让界面无限转圈，也不把"慢"变成"失败连击"
    for (let attempt = 0; ; attempt++) {
      const guard = withTimeout(undefined, undefined);
      try {
        const res = await mediaApi.list(params, guard.signal);
        guard.cleanup();
        if (id !== reqId) return; // a newer request already started
        items = res.items;
        total = res.total;
        loaded = true;
        options.onLoaded?.(items, total);
        return;
      } catch (e) {
        guard.cleanup();
        if (id !== reqId) return;
        const err = guard.timedOut() ? timeoutError() : e;
        if (shouldRetry(err, attempt)) {
          await delay();
          if (id !== reqId) return;
          continue;
        }
        items = [];
        total = 0;
        loaded = true;
        error = err instanceof Error ? err.message : '加载媒体失败';
        return;
      } finally {
        if (id === reqId) loading = false;
      }
    }
  }

  return {
    get items() {
      return items;
    },
    get total() {
      return total;
    },
    get loading() {
      return loading;
    },
    get error() {
      return error;
    },
    get loaded() {
      return loaded;
    },
    reload
  };
}
