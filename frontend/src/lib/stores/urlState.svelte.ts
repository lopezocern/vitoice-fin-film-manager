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
 * `goto()`-driven navigations are covered too: SvelteKit routes them through
 * `history.pushState` / `history.replaceState`, which are patched below to
 * bump the same counter.
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
	// popstate: Back/Forward.
	window.addEventListener('popstate', bump);
	window.addEventListener('hashchange', bump);

	// SvelteKit's goto() drives client-side navigation through
	// history.pushState / history.replaceState — no popstate fires, so without
	// this patch `liveQueryParam()` consumers (manage sidebar sections,
	// settings tabs) would never re-evaluate until a full reload (F5).
	type HistMethod = 'pushState' | 'replaceState';
	const patchHistory = (name: HistMethod): void => {
		const orig = history[name].bind(history);
		history[name] = ((data: unknown, unused: string, url?: string | URL | null) => {
			orig(data, unused, url);
			bump();
		}) as History[HistMethod];
	};
	patchHistory('pushState');
	patchHistory('replaceState');
}

/** Reactive snapshot of the real query string. Re-reads after every navigation. */
export function liveSearchParams(): URLSearchParams {
	if (!browser) return new URLSearchParams();
	const params = new URLSearchParams(window.location.search);
	// Keep the reactive read of `version` alive: Svelte 5's compiler
	// dead-code-eliminates `void version`, which silently severed every
	// `$derived` subscription (menus stopped reacting to goto()/popstate).
	// A conditional read cannot be eliminated and never fires in practice.
	if (version < 0) params.set('__nav__', '1');
	return params;
}

/** Reactive read of a single query param from the real URL. */
export function liveQueryParam(key: string): string | null {
	return liveSearchParams().get(key);
}
