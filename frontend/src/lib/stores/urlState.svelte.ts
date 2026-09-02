/**
 * Reactive access to the *real* URL query string.
 *
 * ## Problem
 *
 * `$page.url` (SvelteKit's page store) restores only the pathname when a route
 * is re-mounted by popstate — the query string is missing. A `$derived` seeded
 * from the store therefore collapses to its default, and the URL-sync `$effect`
 * that mirrors state back into the URL then `replaceState`s that wrong value
 * over the history entry the user just navigated to. Net effect: going Back
 * silently loses the active filter / tab / section.
 *
 * ## Solution
 *
 * Read `window.location` (ground truth — the browser updates it before
 * dispatching popstate) and make the read *reactive* by depending on a counter
 * that `popstate` increments. That keeps the URL -> state direction alive while
 * fixing its value.
 *
 * `goto()`-driven navigations keep working through the components' own state
 * updates, as before.
 *
 * Prefer the non-reactive `realQueryParam()` from `$lib/utils/urlState` for
 * one-shot initialization; use `liveQueryParam()` inside `$derived`.
 */
import { browser } from '$app/environment';

let version = $state(0);

if (browser) {
	const bump = (): void => {
		version += 1;
	};
	// popstate: Back/Forward. SvelteKit's own navigations don't fire this, but
	// components update their own state on `goto` anyway.
	window.addEventListener('popstate', bump);
	window.addEventListener('hashchange', bump);
}

/** Reactive snapshot of the real query string. Re-reads after popstate. */
export function liveSearchParams(): URLSearchParams {
	// Subscribe to the popstate counter so `$derived` re-evaluates.
	void version;
	if (!browser) return new URLSearchParams();
	return new URLSearchParams(window.location.search);
}

/** Reactive read of a single query param from the real URL. */
export function liveQueryParam(key: string): string | null {
	return liveSearchParams().get(key);
}
