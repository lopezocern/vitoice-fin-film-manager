/**
 * URL query access that is safe under popstate.
 *
 * ## Why not `$page.url`
 *
 * SvelteKit's `page` store restores only the pathname when a route component
 * is re-mounted via popstate (browser Back/Forward) — the query string is
 * lost, so `$page.url` reports e.g. `/media` while `location` is
 * `/media?mode=library`. A component that seeds its state from the store then
 * writes that wrong state back through its URL-sync effect (`replaceState`),
 * corrupting the very history entry the user just returned to.
 *
 * `goto()`/push navigations are unaffected; the store is reliable there. The
 * problem is specific to popstate re-mounts, which is exactly when the
 * initialization code runs.
 *
 * `window.location` is ground truth: the browser updates it *before*
 * dispatching popstate.
 *
 * Usage: read query params **once at component init**, never inside `$effect`.
 */

/** True when running in the browser (guards SSR, where `window` is absent). */
export const isBrowser: boolean = typeof window !== 'undefined';

/**
 * Snapshot of the real URL's query string.
 *
 * Returns an empty set during SSR so callers fall back to a default without
 * branching.
 */
export function realSearchParams(): URLSearchParams {
	if (!isBrowser) return new URLSearchParams();
	return new URLSearchParams(window.location.search);
}

/** Read a single query param from the real URL. */
export function realQueryParam(key: string): string | null {
	return realSearchParams().get(key);
}

/**
 * Build a URL for `goto()` from the real location, preserving other params.
 *
 * `new URL($page.url)` has the same popstate defect as `$page.url` — under
 * popstate it would drop the query and silently discard filters/mode.
 */
export function urlWithParam(key: string, value: string | null): string {
	if (!isBrowser) return '';
	const url = new URL(window.location.href);
	if (value === null) {
		url.searchParams.delete(key);
	} else {
		url.searchParams.set(key, value);
	}
	return url.pathname + url.search + url.hash;
}
