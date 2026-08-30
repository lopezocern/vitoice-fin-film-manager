import "clsx";
import { c as client } from "./client2.js";
class SettingsStore {
  /** Raw key→value map from the backend. */
  _values = {};
  _loaded = false;
  get loaded() {
    return this._loaded;
  }
  /**
   * Fetch all settings from the backend and cache in memory.
   * Falls back to localStorage cache if the API is unreachable,
   * then to hardcoded defaults.
   */
  async load() {
    if (!this._loaded) {
      try {
        const cached = localStorage.getItem("vitoice_settings_cache");
        if (cached) {
          this._values = JSON.parse(cached);
        }
      } catch {
      }
    }
    try {
      const list = await client.get("/settings", void 0, void 0, true);
      const map = {};
      for (const s of list) {
        map[s.key] = s.value ?? "";
      }
      this._values = map;
      this._loaded = true;
      localStorage.setItem("vitoice_settings_cache", JSON.stringify(map));
    } catch {
      this._loaded = true;
    }
  }
  /**
   * Update a single setting on the backend and in the store.
   * For sensitive keys the backend may ignore the update (masked placeholder).
   */
  async update(key, value) {
    this._values[key] = value;
    try {
      await client.put(`/settings/${key}`, { value });
      const resp = await client.get(`/settings/${key}`, void 0, void 0, true);
      this._values[key] = resp.value ?? "";
    } catch {
    }
  }
  /**
   * Bulk update settings on the backend.
   * The backend skips sensitive keys whose value is a masked placeholder.
   */
  async bulkUpdate(items) {
    for (const item of items) {
      this._values[item.key] = item.value;
    }
    try {
      await client.put("/settings", { settings: items });
      await this.load();
    } catch {
    }
  }
  /**
   * 仅更新内存值（不请求后端）。
   * 用于设置页已成功 PUT 后同步 store——避免再走 bulkUpdate 的二次 PUT + 全量 load，
   * 让依赖 settingsStore 的页面（媒体页/侧边栏）立即响应，减少"保存后刷新慢"的体感。
   */
  setLocal(key, value) {
    this._values[key] = value;
  }
  // --- Typed accessors with sensible defaults ---
  _getNum(key, fallback) {
    const v = this._values[key];
    const n = v ? parseInt(v, 10) : NaN;
    return Number.isNaN(n) ? fallback : n;
  }
  _getFloat(key, fallback) {
    const v = this._values[key];
    const n = v ? parseFloat(v) : NaN;
    return Number.isNaN(n) ? fallback : n;
  }
  _getStr(key, fallback) {
    return this._values[key] || fallback;
  }
  // Subtitle settings
  get subtitleFontSize() {
    return this._getNum("subtitle_font_size", 16);
  }
  get subtitleColor() {
    return this._getStr("subtitle_color", "#FFFFFF");
  }
  get subtitleStroke() {
    return this._getNum("subtitle_stroke", 2);
  }
  get subtitleBgOpacity() {
    return this._getFloat("subtitle_bg_opacity", 0.5);
  }
  get subtitlePosition() {
    return this._getStr("subtitle_position", "bottom");
  }
  // Player settings
  get stepSize() {
    return this._getFloat("step_size", 5);
  }
  get stepUnit() {
    return this._getStr("step_unit", "seconds");
  }
  // Content restriction
  get showRestricted() {
    return (this._values["show_restricted"] || "false").toLowerCase() === "true";
  }
  get maskRestricted() {
    return (this._values["mask_restricted"] || "false").toLowerCase() === "true";
  }
  // Adult aggregator network source resolution master switch
  get allowAdultNetwork() {
    return (this._values["network_allow_adult"] || "false").toLowerCase() === "true";
  }
}
const settingsStore = new SettingsStore();
export {
  settingsStore as s
};
