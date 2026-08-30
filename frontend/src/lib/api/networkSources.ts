// Adult aggregator network source resolution API (javgg-style).
// ISOLATION: this API is gated by the network_allow_adult backend switch
// (403 when off); the UI entry additionally requires show_restricted.
import { client } from './client';

export interface AdultResolveResult {
  server: string;
  nume: string;
  embed_url: string;
  m3u8_url?: string;
  fallback_url?: string;
  expires_in?: number;
  error?: string;
}

export interface AdultResolveResponse {
  status: 'ok' | 'no_match' | 'error';
  message: string;
  fancode: string;
  results: AdultResolveResult[];
}

export const adultNetworkApi = {
  resolve: (fancode: string, baseUrl?: string) =>
    client.post<AdultResolveResponse>('/network/adult-resolve', {
      fancode,
      base_url: baseUrl || undefined,
    }),
  /** Re-resolve and sync the media's adult sources (update matching + add missing). */
  refresh: (mediaId: string, fancode: string, baseUrl?: string) =>
    client.post<{ updated: number; added: number; removed: number; demoted_pages: number; refresh: AdultResolveResponse }>(
      '/network/adult-refresh',
      { media_id: Number(mediaId), fancode, base_url: baseUrl || undefined },
    ),
};
