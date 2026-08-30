import { client } from './client';

export type ThemeMode = 'light' | 'dark' | 'system';
export type ThumbnailFormat = 'jpg' | 'png' | 'webp';

export interface AISettings {
  provider: string;
  api_key?: string;
  model?: string;
  endpoint?: string;
}

export interface AppSettings {
  theme: ThemeMode;
  language: string;
  scan_on_start: boolean;
  auto_tag: boolean;
  default_rating: number;
  thumbnail_format: ThumbnailFormat;
  player_volume: number;
  player_speed: number;
  shortcuts: Record<string, string>;
  ai: AISettings;
  libraries: string[];
}

export const defaultSettings: AppSettings = {
  theme: 'system',
  language: 'zh-CN',
  scan_on_start: false,
  auto_tag: false,
  default_rating: 0,
  thumbnail_format: 'webp',
  player_volume: 1,
  player_speed: 1,
  shortcuts: {},
  ai: {
    provider: '',
    model: ''
  },
  libraries: []
};

export const settingsApi = {
  get: () => client.get<AppSettings>('/settings'),
  update: (input: Partial<AppSettings>) => client.put<AppSettings>('/settings', input),
  reset: () => client.post<AppSettings>('/settings/reset')
};
