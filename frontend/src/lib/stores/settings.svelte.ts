import { client } from '$lib/api/client';

export interface SettingResponse {
  id: number;
  key: string;
  value: string | null;
  type: string;
  category: string;
  description: string | null;
  updated_at: string;
}

class SettingsStore {
  /** Raw key→value map from the backend. */
  private _values = $state<Record<string, string>>({});
  private _loaded = $state(false);

  get loaded(): boolean {
    return this._loaded;
  }

  /**
   * Fetch all settings from the backend and cache in memory.
   * Falls back to localStorage cache if the API is unreachable,
   * then to hardcoded defaults.
   */
  async load(): Promise<void> {
    // 1. 首次加载用 localStorage 缓存即时渲染（避免白屏）；
    //    后续 load 不再用旧缓存覆盖——否则刚 setLocal 的新值（如刚保存的开关）
    //    会被旧缓存短暂覆盖，后端失败时甚至停留在旧值。
    if (!this._loaded) {
      try {
        const cached = localStorage.getItem('vitoice_settings_cache');
        if (cached) {
          this._values = JSON.parse(cached);
        }
      } catch {
        /* ignore parse errors */
      }
    }

    // 2. Fetch authoritative values from backend
    try {
      const list = await client.get<SettingResponse[]>('/settings', undefined, undefined, true);
      const map: Record<string, string> = {};
      for (const s of list) {
        map[s.key] = s.value ?? '';
      }
      this._values = map;
      this._loaded = true;
      // 3. Write back to localStorage cache
      localStorage.setItem('vitoice_settings_cache', JSON.stringify(map));
    } catch {
      // Backend unreachable — keep cache or defaults
      this._loaded = true;
    }
  }

  /**
   * Update a single setting on the backend and in the store.
   * For sensitive keys the backend may ignore the update (masked placeholder).
   */
  async update(key: string, value: string): Promise<void> {
    // Optimistic local update
    this._values[key] = value;
    try {
      await client.put(`/settings/${key}`, { value });
      // Refresh from backend to get the authoritative (possibly masked) value
      const resp = await client.get<SettingResponse>(`/settings/${key}`, undefined, undefined, true);
      this._values[key] = resp.value ?? '';
    } catch {
      // Revert on failure
      // (the optimistic value stays — better to have something than nothing)
    }
  }

  /**
   * Bulk update settings on the backend.
   * The backend skips sensitive keys whose value is a masked placeholder.
   */
  async bulkUpdate(items: { key: string; value: string }[]): Promise<void> {
    for (const item of items) {
      this._values[item.key] = item.value;
    }
    try {
      await client.put('/settings', { settings: items });
      // Reload to get authoritative values
      await this.load();
    } catch {
      // Keep optimistic values
    }
  }

  /**
   * 仅更新内存值（不请求后端）。
   * 用于设置页已成功 PUT 后同步 store——避免再走 bulkUpdate 的二次 PUT + 全量 load，
   * 让依赖 settingsStore 的页面（媒体页/侧边栏）立即响应，减少"保存后刷新慢"的体感。
   */
  setLocal(key: string, value: string): void {
    this._values[key] = value;
  }

  // --- Typed accessors with sensible defaults ---

  private _getNum(key: string, fallback: number): number {
    const v = this._values[key];
    const n = v ? parseInt(v, 10) : NaN;
    return Number.isNaN(n) ? fallback : n;
  }

  private _getFloat(key: string, fallback: number): number {
    const v = this._values[key];
    const n = v ? parseFloat(v) : NaN;
    return Number.isNaN(n) ? fallback : n;
  }

  private _getStr(key: string, fallback: string): string {
    return this._values[key] || fallback;
  }

  // Subtitle settings
  get subtitleFontSize(): number {
    return this._getNum('subtitle_font_size', 16);
  }
  get subtitleColor(): string {
    return this._getStr('subtitle_color', '#FFFFFF');
  }
  get subtitleStroke(): number {
    return this._getNum('subtitle_stroke', 2);
  }
  get subtitleBgOpacity(): number {
    return this._getFloat('subtitle_bg_opacity', 0.5);
  }
  get subtitlePosition(): string {
    return this._getStr('subtitle_position', 'bottom');
  }

  // Player settings
  get stepSize(): number {
    return this._getFloat('step_size', 5);
  }
  get stepUnit(): string {
    return this._getStr('step_unit', 'seconds');
  }

  // Content restriction
  get showRestricted(): boolean {
    return (this._values['show_restricted'] || 'false').toLowerCase() === 'true';
  }
  get maskRestricted(): boolean {
    return (this._values['mask_restricted'] || 'false').toLowerCase() === 'true';
  }
  // Adult aggregator network source resolution master switch
  get allowAdultNetwork(): boolean {
    return (this._values['network_allow_adult'] || 'false').toLowerCase() === 'true';
  }

  // Player end-of-playback behavior
  /** 播放结束后自动连播下一集（仅同系列存在下一集时生效）。 */
  get playerAutoplay(): boolean {
    return (this._values['player_autoplay'] || 'false').toLowerCase() === 'true';
  }
  /** 播放结束显示推荐网格（无连播或连播关闭时展示）。 */
  get playerRecGrid(): boolean {
    return (this._values['player_rec_grid'] || 'true').toLowerCase() === 'true';
  }
}

export const settingsStore = new SettingsStore();
