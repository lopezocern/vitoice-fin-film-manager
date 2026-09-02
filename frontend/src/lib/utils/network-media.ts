/** Network media utility functions for vitoice player */

export type NetworkUrlType = 'direct' | 'hls' | 'platform';

/** Classify a network URL into playback category. */
export function classifyNetworkUrl(url: string): NetworkUrlType {
  if (!url) return 'platform';
  const lower = url.toLowerCase();

  if (lower.includes('.m3u8')) return 'hls';

  const platformPatterns = [
    /youtube\.com\/watch/, /youtu\.be\//, /bilibili\.com\/video/,
    /b23\.tv\//, /vimeo\.com\//, /twitch\.tv\//, /nicovideo\.jp\/watch/,
  ];
  if (platformPatterns.some((p) => p.test(lower))) return 'platform';

  const directExts = /\.(mp4|webm|ogg|mov|m4v|mkv)(\?|$)/;
  if (directExts.test(lower)) return 'direct';

  if (!lower.includes('watch') && !lower.includes('/embed/')) return 'direct';
  return 'platform';
}

/** Load hls.js dynamically from CDN. */
export async function loadHlsJs(): Promise<any> {
  if ((window as any).Hls) return (window as any).Hls;
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js';
    script.onload = () => {
      if ((window as any).Hls) resolve((window as any).Hls);
      else reject(new Error('hls.js loaded but Hls not found'));
    };
    script.onerror = () => reject(new Error('Failed to load hls.js from CDN'));
    document.head.appendChild(script);
  });
}

/** Detect if running inside Tauri desktop app. */
export function isTauriEnv(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/** Open an external URL in the system default browser (Tauri) or new tab (browser). */
export async function openExternalUrl(url: string): Promise<void> {
  if (isTauriEnv()) {
    try {
      const { openUrl } = await import('@tauri-apps/plugin-opener');
      await openUrl(url);
    } catch {
      // Fallback to window.open if Tauri opener plugin fails
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  } else {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}

// ---- Adult aggregator (javgg-style) media detection --------------------------

/** Platform names produced by the adult aggregator resolver. */
export const ADULT_SERVERS = ['vidhide', 'turboplay', 'streamwish'] as const;

/** True when a URL points at an adult aggregator site (e.g. javgg article page). */
export function isAdultAggregatorUrl(url: string): boolean {
  const lower = url.toLowerCase();
  return lower.includes('javgg') || lower.includes('/jav/') || lower.includes('javbus');
}

/** True when the media carries adult aggregator source URLs (isolation-aware).
 *
 * Matches either the resolver platform names OR an aggregator page URL
 * (users may import the article page link instead of a resolved stream —
 * the "刷新源" button then upgrades it to real stream URLs). */
export function isAdultNetworkMedia(
  media: { media_type?: string; urls?: { url_role: string; url?: string; platform?: string | null }[] },
): boolean {
  if (media.media_type !== 'network') return false;
  return (media.urls ?? []).some(
    (u) =>
      u.url_role === 'source' &&
      ((!!u.platform && (ADULT_SERVERS as readonly string[]).includes(u.platform.toLowerCase())) ||
        isAdultAggregatorUrl(u.url ?? '')),
  );
}

/** Extract a JAV fancode (e.g. ``SNOS-334`` or prefixed ``300MIUM-1334``) from a string, or null. */
export function extractFancode(text: string): string | null {
  const m = text.toUpperCase().match(/\b(\d{1,5})?([A-Z]{2,6})[-_ ]?(\d{2,5})\b/);
  if (!m) return null;
  return `${m[1] ?? ''}${m[2]}-${m[3]}`;
}
