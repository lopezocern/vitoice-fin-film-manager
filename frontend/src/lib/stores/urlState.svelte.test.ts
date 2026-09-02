import { describe, expect, it, beforeEach, vi } from 'vitest';

// SvelteKit's generated `$app/environment` resolves `browser` to false under
// vitest (it is a build-time constant), which would send the module down its
// SSR branch and return an empty param set. The browser branch is the one the
// app actually runs, so force it on for these tests.
vi.mock('$app/environment', () => ({
	browser: true,
	dev: true,
	building: false,
	version: 'test'
}));

import { liveQueryParam, liveSearchParams } from './urlState.svelte';

/**
 * Value-correctness tests for the reactive URL helpers.
 *
 * ## What is covered
 *
 * That `liveQueryParam()` returns the *real* query string after a popstate —
 * the actual defect being fixed. SvelteKit's `$page.url` restores only the
 * pathname on a popstate re-mount, so a `$derived` seeded from the store
 * collapses to its default and the component's URL-sync effect then writes
 * that wrong value back over the history entry.
 *
 * ## What is NOT covered
 *
 * The `version` counter that makes the read *re-evaluate* (i.e. the reactive
 * plumbing). Verifying it needs `$effect.root` + `$effect` + `flushSync`,
 * and effects do not execute under this project's vitest setup — even a
 * minimal `$state` -> `$effect` sanity case produces no runs. That is a
 * tooling limitation, not a product defect. The re-evaluation path is covered
 * indirectly: `liveQueryParam` re-reads `window.location` on every call, so
 * any read triggered after popstate gets the correct value.
 */
describe('liveQueryParam', () => {
	beforeEach(() => {
		window.history.replaceState({}, '', '/');
	});

	it('reads the current query string', () => {
		window.history.replaceState({}, '', '/manage?section=tags');

		expect(liveQueryParam('section')).toBe('tags');
		expect(liveSearchParams().get('section')).toBe('tags');
	});

	it('returns the real query after a popstate re-mount', () => {
		// The regression: the component re-mounts here and re-seeds its state.
		// SvelteKit's page store would report a bare pathname at this point.
		window.history.replaceState({}, '', '/manage?section=tags');
		window.dispatchEvent(new PopStateEvent('popstate', { state: null }));

		expect(liveQueryParam('section')).toBe('tags');
	});

	it('returns the real query after a hashchange', () => {
		window.history.replaceState({}, '', '/settings?cat=player');
		window.dispatchEvent(new HashChangeEvent('hashchange'));

		expect(liveQueryParam('cat')).toBe('player');
	});

	it('picks up a changed value across successive popstates', () => {
		window.history.replaceState({}, '', '/settings?cat=ai');
		window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
		expect(liveQueryParam('cat')).toBe('ai');

		// Navigate again: the helper must not cache the first answer.
		window.history.replaceState({}, '', '/settings?cat=player');
		window.dispatchEvent(new PopStateEvent('popstate', { state: null }));

		expect(liveQueryParam('cat')).toBe('player');
	});

	it('returns null when there is no query', () => {
		window.history.replaceState({}, '', '/manage');

		expect(liveQueryParam('section')).toBeNull();
		expect([...liveSearchParams().keys()]).toEqual([]);
	});

	it('reads multiple params independently', () => {
		window.history.replaceState({}, '', '/media?mode=library&view=grid');

		expect(liveQueryParam('mode')).toBe('library');
		expect(liveQueryParam('view')).toBe('grid');
		expect(liveQueryParam('missing')).toBeNull();
	});
});
