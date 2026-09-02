import { describe, expect, it, beforeEach } from 'vitest';
import { isBrowser, realQueryParam, realSearchParams, urlWithParam } from './urlState';

/**
 * These tests pin the *reason* this module exists: SvelteKit's `page` store
 * restores only the pathname when a route is re-mounted by popstate, so
 * `$page.url.searchParams` silently returns nothing. `window.location` is the
 * ground truth. If someone "simplifies" these helpers back to the store, the
 * popstate regressions in the player / settings / manage pages come back.
 */
describe('urlState', () => {
	beforeEach(() => {
		// jsdom starts at about:blank; give it a real http origin so that
		// `new URL(...)` and relative paths behave like the browser.
		window.history.replaceState({}, '', '/');
	});

	it('reports running in a browser', () => {
		expect(isBrowser).toBe(true);
	});

	it('reads the query string from the real location', () => {
		window.history.replaceState({}, '', '/media?mode=library&view=grid');

		const params = realSearchParams();

		expect(params.get('mode')).toBe('library');
		expect(params.get('view')).toBe('grid');
		expect(params.get('missing')).toBeNull();
	});

	it('returns a single param by key', () => {
		window.history.replaceState({}, '', '/player?id=42&from=detail');

		expect(realQueryParam('id')).toBe('42');
		expect(realQueryParam('from')).toBe('detail');
		expect(realQueryParam('nope')).toBeNull();
	});

	it('returns an empty param set when the URL has no query', () => {
		window.history.replaceState({}, '', '/media');

		expect(realQueryParam('mode')).toBeNull();
		expect([...realSearchParams().keys()]).toEqual([]);
	});

	it('survives a popstate re-mount, which is the whole point', () => {
		// This is the regression: after popstate the component re-mounts and
		// re-initialises. SvelteKit's store would report a bare pathname here.
		window.history.replaceState({}, '', '/media?mode=library');
		window.dispatchEvent(new PopStateEvent('popstate', { state: null }));

		expect(realQueryParam('mode')).toBe('library');
	});

	describe('urlWithParam', () => {
		it('sets a param while preserving the others', () => {
			window.history.replaceState({}, '', '/media?mode=library&view=grid');

			expect(urlWithParam('mode', 'recent')).toBe('/media?mode=recent&view=grid');
		});

		it('adds a param when the URL has no query yet', () => {
			window.history.replaceState({}, '', '/media');

			expect(urlWithParam('mode', 'library')).toBe('/media?mode=library');
		});

		it('removes a param when the value is null', () => {
			window.history.replaceState({}, '', '/media?mode=library&view=grid');

			expect(urlWithParam('mode', null)).toBe('/media?view=grid');
		});

		it('preserves the pathname and hash', () => {
			window.history.replaceState({}, '', '/detail/7?tab=cast#credits');

			expect(urlWithParam('tab', 'crew')).toBe('/detail/7?tab=crew#credits');
		});

		it('does not corrupt a popstate-restored URL', () => {
			// The failure mode this prevents: building the next URL from
			// `$page.url` would drop the query the user just navigated back to.
			window.history.replaceState({}, '', '/manage?section=tags');
			window.dispatchEvent(new PopStateEvent('popstate', { state: null }));

			expect(urlWithParam('section', 'tasks')).toBe('/manage?section=tasks');
		});
	});
});
