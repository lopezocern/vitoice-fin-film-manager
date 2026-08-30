// 共享资源库状态：Sidebar / 媒体页 / 管理页 / 详情页 共用
// 任何创建/编辑/删除库的操作后调用 reload() 即可全局刷新

import { librariesApi, type Library } from '$lib/api/libraries';
import { tagsApi, type Tag } from '$lib/api/tags';
import { mediaApi } from '$lib/api/media';
import { client } from '$lib/api/client';

interface SmartFolder {
  id: number;
  name: string;
  color?: string | null;
  preview_count?: number;
}

export interface TagType {
  id: number;
  name: string;
  color?: string | null;
  is_builtin?: boolean;
  sort_order?: number;
}

class LibrariesStore {
  libraries = $state<Library[]>([]);
  tags = $state<Tag[]>([]);
  tagTypes = $state<TagType[]>([]);
  smartFolders = $state<SmartFolder[]>([]);
  totalCount = $state(0);
  favoriteCount = $state(0);
  loading = $state(false);
  /** 最近一次 reload 的失败原因（全部请求都失败时非空，供页面展示"后端不可达"提示） */
  lastError = $state('');
  private loaded = false;
  private _reloadGen = 0;

  /**
   * 数据版本号：reload() 成功后自增。
   * 媒体页/管理页在 $effect 中追踪该值——侧边栏内任何修改媒体数据的操作
   * (打标/取消打标/移动库/删除标签等, 均通过 tagOps → reload) 后,
   * 可见页面列表能立即刷新, 无需等用户切页/切筛选。
   */
  revision = $state(0);

  /** Load all sidebar data from the backend. Safe to call multiple times. */
  async reload(): Promise<void> {
    const gen = ++this._reloadGen;
    this.loading = true;
    // libraries/tags 必须 noCache（绕过 client 30s GET 缓存）：受限开关切换、
    // 导航后刷新等场景要拿到最新数据，否则侧边栏显示旧库列表/旧标签。
    const [libs, tgs, types, folders, all, favs] = await Promise.allSettled([
      librariesApi.list(true),
      tagsApi.list({ noCache: true }),
      client.get<TagType[]>('/tag-types'),
      client.get<SmartFolder[]>('/smart-folders'),
      mediaApi.list({ page: 1, page_size: 1 }),
      mediaApi.list({ favorite: true, page: 1, page_size: 1 })
    ]);
    // 丢弃过期（gen 滞后）的 reload 响应，防止竞态
    if (gen !== this._reloadGen) {
      this.loading = false;
      return;
    }
    if (libs.status === 'fulfilled') this.libraries = libs.value ?? [];
    if (tgs.status === 'fulfilled') this.tags = tgs.value ?? [];
    if (types.status === 'fulfilled') this.tagTypes = types.value ?? [];
    if (folders.status === 'fulfilled') this.smartFolders = folders.value ?? [];
    if (all.status === 'fulfilled') this.totalCount = all.value.total ?? 0;
    if (favs.status === 'fulfilled') this.favoriteCount = favs.value.total ?? 0;
    // 全部失败 → 记录错误供页面提示（默认仍保持静默，不打扰主界面）
    if ([libs, tgs, types, folders].every((r) => r.status === 'rejected')) {
      const reason = (libs as PromiseRejectedResult).reason;
      this.lastError = reason instanceof Error ? reason.message : '无法连接后端服务';
      console.warn('[librariesStore] reload 全部失败:', this.lastError);
    } else {
      this.lastError = '';
    }
    this.loading = false;
    this.loaded = true;
    this.revision++;
  }

  /**
   * 数据变更通知（轻量，不请求后端）：仅递增 revision。
   * 媒体页/管理页 $effect 追踪 revision，变化即重新加载列表——
   * 用于删除/回收/恢复等本地操作后立即刷新可见列表，
   * 避免"操作生效但界面未及时刷新"。
   */
  notifyChanged(): void {
    this.revision++;
  }

  /** Ensure data is loaded at least once (idempotent). */
  async ensureLoaded(): Promise<void> {
    if (!this.loaded) {
      await this.reload();
    }
  }
}

export const librariesStore = new LibrariesStore();
