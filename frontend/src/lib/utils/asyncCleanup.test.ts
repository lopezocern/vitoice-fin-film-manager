import { describe, expect, it, vi } from 'vitest';
import { createAsyncCleanup } from './asyncCleanup';

/**
 * These tests pin the unmount-during-await race in Tauri listener
 * registration: `unlisten = await win.onX(...)` leaves `unlisten === null` if
 * the component unmounts first, so the listener is never removed and every
 * re-entry into the page stacks another live callback on the webview.
 */
describe('createAsyncCleanup', () => {
	it('runs the registered disposer on dispose', () => {
		const ac = createAsyncCleanup();
		const dispose = vi.fn();

		ac.set(dispose);
		expect(dispose).not.toHaveBeenCalled();

		ac.dispose();

		expect(dispose).toHaveBeenCalledTimes(1);
		expect(ac.disposed).toBe(true);
	});

	it('invokes a late registration immediately (the race it exists for)', () => {
		const ac = createAsyncCleanup();
		const dispose = vi.fn();

		ac.dispose(); // unmount wins the race
		ac.set(dispose); // await resolves afterwards

		expect(dispose).toHaveBeenCalledTimes(1);
	});

	it('does not re-run the disposer when dispose is called twice', () => {
		const ac = createAsyncCleanup();
		const dispose = vi.fn();

		ac.set(dispose);
		ac.dispose();
		ac.dispose();

		expect(dispose).toHaveBeenCalledTimes(1);
	});

	it('is idempotent for repeated late registrations after dispose', () => {
		const ac = createAsyncCleanup();
		const first = vi.fn();
		const second = vi.fn();

		ac.dispose();
		ac.set(first);
		ac.set(second);

		expect(first).toHaveBeenCalledTimes(1);
		expect(second).toHaveBeenCalledTimes(1);
	});

	it('ignores null / undefined registrations', () => {
		const ac = createAsyncCleanup();

		expect(() => {
			ac.set(null);
			ac.set(undefined);
			ac.dispose();
		}).not.toThrow();
		expect(ac.disposed).toBe(true);
	});

	it('swallows a throwing disposer so teardown cannot break unmount', () => {
		const ac = createAsyncCleanup();
		ac.set(() => {
			throw new Error('listener already gone');
		});

		expect(() => ac.dispose()).not.toThrow();
	});

	it('swallows a throwing late registration after dispose', () => {
		const ac = createAsyncCleanup();
		ac.dispose();

		expect(() =>
			ac.set(() => {
				throw new Error('listener already gone');
			})
		).not.toThrow();
	});

	it('reports not-disposed before dispose is called', () => {
		const ac = createAsyncCleanup();

		expect(ac.disposed).toBe(false);

		ac.dispose();

		expect(ac.disposed).toBe(true);
	});
});
