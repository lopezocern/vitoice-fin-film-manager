/**
 * 自定义在线源（苹果 CMS 采集站）客户端。
 *
 * 与 `networkSources.ts` 的区别：
 * - `networkSources` 是内置站点解析（fancode → 播放地址），服务已入库的媒体；
 * - 这里是用户自填的通用源，用于「搜索 → 在线播放 / 入库」。
 */
import { client } from './client';

export interface SourceHealth {
  fail_streak: number;
  disabled_until: number;
  last_ok_at: number;
  last_error: string | null;
  latency_ms: number | null;
  available: boolean;
}

export interface OnlineSource {
  id: string;
  name: string;
  kind: string;
  base_url: string;
  api_path: string;
  enabled: boolean;
  timeout: number;
  headers: Record<string, string>;
  health: SourceHealth | null;
}

/** 可保存的源（id 缺省时由后端按名称派生，改名请保留 id）。 */
export interface OnlineSourceInput {
  id?: string;
  name: string;
  base_url: string;
  kind?: string;
  api_path?: string;
  enabled?: boolean;
  timeout?: number;
  headers?: Record<string, string>;
}

export interface SourceOffer {
  source_id: string;
  vod_id: string;
  remarks: string | null;
}

/** 跨源合并后的搜索结果。 */
export interface AggregatedResult {
  key: string;
  title: string;
  year: number | null;
  poster: string | null;
  source_count: number;
  offers: SourceOffer[];
}

export interface SourceSearchReport {
  source_id: string;
  latency_ms: number | null;
  fail_streak: number;
  available: boolean;
  last_error: string | null;
}

export interface SourceSearchResponse {
  keyword: string;
  total: number;
  skipped_sources: string[];
  items: AggregatedResult[];
  sources: SourceSearchReport[];
}

export interface OnlineEpisode {
  name: string;
  url: string;
  /** 直链（m3u8/mp4/flv）可直接播放；否则是需要打开的原站页面 */
  direct: boolean;
}

export interface OnlinePlayGroup {
  flag: string;
  episodes: OnlineEpisode[];
}

export interface SourceResolveResponse {
  source_id: string;
  vod_id: string;
  title: string;
  year: number | null;
  poster: string | null;
  groups: OnlinePlayGroup[];
}

export interface ProbeResult {
  ok: boolean;
  message: string;
  latency_ms: number;
  health: SourceHealth;
}

export const onlineSourcesApi = {
  list: async (): Promise<OnlineSource[]> => {
    const raw = await client.get<{ sources?: OnlineSource[] }>('/sources');
    return raw?.sources ?? [];
  },

  save: (sources: OnlineSourceInput[]): Promise<{ status: string; count: number }> =>
    client.put<{ status: string; count: number }>('/sources', { sources }),

  /** 探活：传 id 测已保存源，传 base_url 测表单里尚未保存的地址。 */
  test: (payload: { id?: string; base_url?: string; api_path?: string; timeout?: number }) =>
    client.post<ProbeResult>('/sources/test', payload),

  search: (q: string, page = 1): Promise<SourceSearchResponse> =>
    client.get<SourceSearchResponse>('/sources/search', { q, page }),

  resolve: (sourceId: string, vodId: string): Promise<SourceResolveResponse> =>
    client.post<SourceResolveResponse>('/sources/resolve', {
      source_id: sourceId,
      vod_id: vodId
    })
};
