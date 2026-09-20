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
	// popstate: Back/Forward. hashchange: fragment changes.
	window.addEventListener('popstate', bump);
	window.addEventListener('hashchange', bump);
	// NOTE: do NOT patch history.pushState/replaceState here. SvelteKit
	// installs its own override of those methods; wrapping them on top makes
	// SvelteKit's internal navigate() route back through this wrapper and
	// re-trigger the counter on every navigation, forming an infinite
	// `effect_update_depth_exceeded` loop that freezes the UI on its loading
	// skeleton. React to navigations via afterNavigate() (see notifyUrlChanged).
}

/**
 * Bump the reactive URL version after a SvelteKit navigation.
 * The root layout calls this from afterNavigate; goto()/links/pushState/
 * replaceState don't fire popstate, so without it liveQueryParam() consumers
 * (manage sidebar sections, settings tabs) never re-evaluate after navigation
 * until a full reload (F5).
 */
export function notifyUrlChanged(): void {
	if (browser) version += 1;
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
