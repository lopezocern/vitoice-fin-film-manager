
// this file is generated — do not edit it


declare module "svelte/elements" {
	export interface HTMLAttributes<T> {
		'data-sveltekit-keepfocus'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-noscroll'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-preload-code'?:
			| true
			| ''
			| 'eager'
			| 'viewport'
			| 'hover'
			| 'tap'
			| 'off'
			| undefined
			| null;
		'data-sveltekit-preload-data'?: true | '' | 'hover' | 'tap' | 'off' | undefined | null;
		'data-sveltekit-reload'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-replacestate'?: true | '' | 'off' | undefined | null;
	}
}

export {};


declare module "$app/types" {
	type MatcherParam<M> = M extends (param : string) => param is (infer U extends string) ? U : string;

	export interface AppTypes {
		RouteId(): "/" | "/detail" | "/detail/[id]" | "/import" | "/libraries" | "/manage" | "/media" | "/player" | "/series" | "/series/[id]" | "/settings" | "/smart-folders" | "/tags";
		RouteParams(): {
			"/detail/[id]": { id: string };
			"/series/[id]": { id: string }
		};
		LayoutParams(): {
			"/": { id?: string | undefined };
			"/detail": { id?: string | undefined };
			"/detail/[id]": { id: string };
			"/import": Record<string, never>;
			"/libraries": Record<string, never>;
			"/manage": Record<string, never>;
			"/media": Record<string, never>;
			"/player": Record<string, never>;
			"/series": { id?: string | undefined };
			"/series/[id]": { id: string };
			"/settings": Record<string, never>;
			"/smart-folders": Record<string, never>;
			"/tags": Record<string, never>
		};
		Pathname(): "/" | `/detail/${string}` & {} | "/import" | "/libraries" | "/manage" | "/media" | "/player" | `/series/${string}` & {} | "/settings" | "/smart-folders" | "/tags";
		ResolvedPathname(): `${"" | `/${string}`}${ReturnType<AppTypes['Pathname']>}`;
		Asset(): "/favicon.png" | "/vitoice-logo.svg" | string & {};
	}
}