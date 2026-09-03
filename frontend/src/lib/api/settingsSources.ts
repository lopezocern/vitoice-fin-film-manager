// Scrape source chains API — unified movie/tv/av scraping source management.
import { client } from './client';

export interface ScrapeSourceItem {
  name: string;
  kind: 'tmdb' | 'html';
  base_url: string;
  image_base?: string;
  api_key?: string;
  language?: string;
  timeout?: number;
  enabled?: boolean;
  parser?: '' | 'javbus' | 'javdb' | 'javlibrary' | '3xplanet';
}

export type ScrapeSources = {
  movie: ScrapeSourceItem[];
  tv: ScrapeSourceItem[];
  av: ScrapeSourceItem[];
};

export interface SourceTestResult {
  ok: boolean;
  message: string;
}

export const sourcesApi = {
  /** Load configured chains. api_key values arrive masked (****). */
  get: () => client.get<ScrapeSources>('/settings/scrape-sources'),

  /** Built-in AV source chain (the scraper's fallback when av group is empty). */
  getAvDefaults: () =>
    client.get<{ av: ScrapeSourceItem[] }>('/settings/scrape-sources/defaults'),

  /** Validate + persist chains. Masked api_key placeholders are kept. */
  put: (sources: ScrapeSources) =>
    client.put<ScrapeSources>('/settings/scrape-sources', { sources }),

  /** Test a single source's connectivity. */
  test: (kind: 'movie' | 'tv' | 'av', source: ScrapeSourceItem) =>
    client.post<SourceTestResult>('/settings/test-source', { kind, source }),
};
