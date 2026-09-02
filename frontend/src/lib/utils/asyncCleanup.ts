/**
 * Cleanup registration that survives unmount-during-await.
 *
 * ## The race it fixes
 *
 * Tauri listeners are registered asynchronously:
 *
 * ```ts
 * $effect(() => {
 *   let unlisten: (() => void) | null = null;
 *   (async () => {
 *     unlisten = await win.onResized(handler);   // <- await
 *   })();
 *   return () => { unlisten?.(); };              // <- may run first
 * });
 * ```
 *
 * If the component unmounts while the `await` is in flight, the cleanup runs
 * with `unlisten === null` and is a no-op. The promise then resolves and
 * assigns the real unlisten function, which nobody will ever call — the
 * listener stays attached to the webview for the lifetime of the window, and
 * re-entering the page stacks up another copy. Each leaked callback keeps
 * writing to `$state` of a dead component.
 *
 * ## Usage
 *
 * ```ts
 * $effect(() => {
 *   const ac = createAsyncCleanup();
 *   (async () => {
 *     ac.set(await win.onResized(handler));
 *   })();
 *   return () => ac.dispose();
 * });
 * ```
 */
export interface AsyncCleanup {
	/** Register the disposer; if already disposed, it is invoked immediately. */
	set(fn: (() => void) | null | undefined): void;
	/** Run the registered disposer (if any) and prevent later registration. */
	dispose(): void;
	/** True once `dispose()` has been called. */
	readonly disposed: boolean;
}

export function createAsyncCleanup(): AsyncCleanup {
	let disposed = false;
	let cleanup: (() => void) | null = null;

	return {
		set(fn) {
			if (!fn) return;
			if (disposed) {
				// Unmounted before the async registration resolved — undo it now.
				try {
					fn();
				} catch {
					/* listener already gone; nothing to undo */
				}
				return;
			}
			cleanup = fn;
		},
		dispose() {
			if (disposed) return;
			disposed = true;
			const fn = cleanup;
			cleanup = null;
			try {
				fn?.();
			} catch {
				/* ignore teardown errors */
			}
		},
		get disposed() {
			return disposed;
		},
	};
}
