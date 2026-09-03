<script lang="ts">
  // 设置页：键值对存储，8 个分区
  // 后端 GET /settings 返回 [{id, key, value, type, category, description, updated_at}]
  // PUT /settings {settings:[{key,value}]} 批量更新
  import { onMount, onDestroy } from 'svelte';
  import { client, ApiError } from '$lib/api/client';
  import { settingsStore } from '$lib/stores/settings.svelte';
  import { liveQueryParam } from '$lib/stores/urlState.svelte';
  import SourceManager from '$lib/components/settings/SourceManager.svelte';
  import { openExternalUrl, isTauriEnv } from '$lib/utils/network-media';

  // 字节数 → 人类可读 (B/KB/MB/GB)
  function formatBytes(n: number): string {
    if (!n || n <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let v = n;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  // ---- 设置项类型 ----
  type SettingType =
    | 'text'
    | 'password'
    | 'number'
    | 'range'
    | 'select'
    | 'toggle'
    | 'color'
    | 'readonly';

  interface SettingItem {
    key: string;
    category: string;
    label: string;
    type: SettingType;
    default: string;
    options?: { value: string; label: string }[];
    min?: number;
    max?: number;
    step?: number;
    unit?: string;
    testable?: boolean;
    pickable?: boolean;
    description?: string;
  }

  interface SettingResponse {
    id: number;
    key: string;
    value: string | null;
    type: string;
    category: string;
    description: string | null;
    updated_at: string;
  }

  // ---- 分区定义（icon 通过 SVG snippet 渲染） ----
  const categories: { id: string; label: string }[] = [
    { id: 'appearance', label: '外观' },
    { id: 'content', label: '内容管理' },
    { id: 'tools', label: '外部工具' },
    { id: 'thumbnail', label: '缩略图' },
    { id: 'ai', label: 'AI 配置' },
    { id: 'scrape', label: '刮削' },
    { id: 'player', label: '播放器' },
    { id: 'subtitle', label: '字幕' },
    { id: 'database', label: '数据库' },
    { id: 'about', label: '关于' }
  ];

  // ---- 设置项 schema（全部分区的已知键，带默认值） ----
  const schema: SettingItem[] = [
    // 外观
    {
      key: 'theme',
      category: 'appearance',
      label: '主题',
      type: 'select',
      default: 'system',
      options: [
        { value: 'light', label: '浅色' },
        { value: 'dark', label: '深色' },
        { value: 'system', label: '跟随系统' }
      ],
      description: '应用界面主题'
    },
    {
      key: 'language',
      category: 'appearance',
      label: '语言',
      type: 'select',
      default: 'zh-CN',
      options: [
        { value: 'zh-CN', label: '中文' },
        { value: 'en', label: '英文' }
      ],
      description: '界面显示语言'
    },
    // 内容管理
    {
      key: 'show_restricted',
      category: 'content',
      label: '显示限制内容',
      type: 'toggle',
      default: 'false',
      description: '打开后显示标记为限制的媒体库（如成人内容）。关闭时这些库及其媒体、标签在所有页面隐藏。'
    },
    {
      key: 'mask_restricted',
      category: 'content',
      label: '遮罩限制内容',
      type: 'toggle',
      default: 'false',
      description: '仅在"显示限制内容"开启时生效。对限制内容的海报和播放画面应用模糊遮罩，避免预览时直接展示。'
    },
    {
      key: 'network_allow_adult',
      category: 'content',
      label: '允许成人网络源解析',
      type: 'toggle',
      default: 'false',
      description: '开启后可在网络媒体导入中解析成人聚合站（javgg）的播放源。javgg 存在间歇性访问限制（403 频率限制），遇到时等 1-2 分钟重试即可；3 小时缓存内同一番号不会再请求聚合站。仅在"显示限制内容"开启时显示。'
    },
    {
      key: 'network_adult_base_url',
      category: 'content',
      label: '成人聚合站地址',
      type: 'text',
      default: 'https://javgg.net',
      description: '成人网络源的聚合站根地址（此类域名更换频繁，可在此修改）。仅在"显示限制内容"开启时显示。'
    },
    // 外部工具
    {
      key: 'ffmpeg_path',
      category: 'tools',
      label: 'FFmpeg 路径',
      type: 'text',
      default: '',
      testable: true,
      pickable: true,
      description: '视频转码与缩略图生成依赖'
    },
    {
      key: 'ffprobe_path',
      category: 'tools',
      label: 'FFprobe 路径',
      type: 'text',
      default: '',
      testable: true,
      pickable: true,
      description: '媒体元数据探测依赖'
    },
    {
      key: 'ytdlp_path',
      category: 'tools',
      label: 'yt-dlp 路径',
      type: 'text',
      default: '',
      testable: true,
      pickable: true,
      description: '网络资源下载依赖'
    },
    {
      key: 'proxy_enabled',
      category: 'tools',
      label: '启用 HTTP 代理',
      type: 'toggle',
      default: 'false',
      description: '所有外部请求（TMDB 刮削、限制内容源、聚合站解析、AI 打标、网络流代理）通过代理访问。关闭为直连。'
    },
    {
      key: 'proxy_host',
      category: 'tools',
      label: '代理地址',
      type: 'text',
      default: '',
      testable: true,
      description: '代理主机 IP 或域名（如 127.0.0.1）'
    },
    {
      key: 'proxy_port',
      category: 'tools',
      label: '代理端口',
      type: 'text',
      default: '7890',
      description: '代理端口（如 7890）'
    },
    // 缩略图
    {
      key: 'thumbnail_size',
      category: 'thumbnail',
      label: '缩略图尺寸',
      type: 'range',
      default: '320',
      min: 160,
      max: 640,
      step: 20,
      unit: 'px',
      description: '缩略图宽度（像素）'
    },
    {
      key: 'thumbnail_quality',
      category: 'thumbnail',
      label: '缩略图质量',
      type: 'range',
      default: '85',
      min: 50,
      max: 100,
      step: 1,
      unit: '%',
      description: 'JPEG 压缩质量'
    },
    {
      key: 'thumbnail_offset',
      category: 'thumbnail',
      label: '时间偏移',
      type: 'number',
      default: '10',
      min: 0,
      max: 600,
      step: 1,
      unit: '秒',
      description: '从视频第几秒截取缩略图'
    },
    {
      key: 'thumbnail_smart_frame',
      category: 'thumbnail',
      label: '智能选帧',
      type: 'toggle',
      default: 'true',
      description: '自动跳过黑屏/纯色帧，从多个时间点选择有效画面作为封面'
    },
    // AI 配置
    {
      key: 'ai_base_url',
      category: 'ai',
      label: 'API 地址',
      type: 'text',
      default: 'https://api.openai.com/v1',
      description: 'OpenAI 兼容接口地址，需以 /v1 结尾'
    },
    {
      key: 'ai_api_key',
      category: 'ai',
      label: 'API Token',
      type: 'password',
      default: '',
      description: 'API 访问令牌，本地存储不上传'
    },
    {
      key: 'ai_model',
      category: 'ai',
      label: '模型名称',
      type: 'text',
      default: 'gpt-4o-mini',
      description: '如 gpt-4o-mini、deepseek-chat、moonshot-v1-8k'
    },
    {
      key: 'ai_auto_tag',
      category: 'ai',
      label: '导入时自动打标',
      type: 'toggle',
      default: 'false',
      description: '扫描完成后自动调用 AI 生成标签'
    },
    // 刮削（TMDB 元数据：标题 / 年份 / 简介 / 海报）
    {
      key: 'tmdb_api_key',
      category: 'scrape',
      label: 'TMDB API Key',
      type: 'password',
      default: '',
      description: 'The Movie Database 密钥，支持 v3 Key 或 v4 读取令牌（eyJ 开头），本地存储不上传'
    },
    {
      key: 'tmdb_language',
      category: 'scrape',
      label: '刮削语言',
      type: 'select',
      default: 'zh-CN',
      options: [
        { value: 'zh-CN', label: '简体中文' },
        { value: 'zh-TW', label: '繁体中文' },
        { value: 'en-US', label: 'English' },
        { value: 'ja-JP', label: '日本語' }
      ],
      description: '标题与简介的返回语言'
    },
    {
      key: 'tmdb_base_url',
      category: 'scrape',
      label: 'API Base URL',
      type: 'text',
      default: 'https://api.themoviedb.org/3',
      description: '默认官方地址，可填反代地址以改善连通性；改回默认即可还原'
    },
    // 播放器
    {
      key: 'step_size',
      category: 'player',
      label: '步长',
      type: 'number',
      default: '5',
      min: 1,
      max: 60,
      step: 1,
      unit: '',
      description: '快进/快退的步长数值'
    },
    {
      key: 'step_unit',
      category: 'player',
      label: '步长单位',
      type: 'select',
      default: 'seconds',
      options: [
        { value: 'seconds', label: '秒' },
        { value: 'frames', label: '帧' }
      ],
      description: '步长按时间或帧数计算'
    },
    {
      key: 'player_autoplay',
      category: 'player',
      label: '自动连播',
      type: 'toggle',
      default: 'false',
      description: '播放结束后 5 秒倒计时自动播放同系列下一集'
    },
    {
      key: 'player_rec_grid',
      category: 'player',
      label: '结束推荐网格',
      type: 'toggle',
      default: 'true',
      description: '播放结束后（或未连播时）展示同系列/同标签/同库的推荐网格'
    },
    // 字幕
    {
      key: 'subtitle_font_size',
      category: 'subtitle',
      label: '字体大小',
      type: 'number',
      default: '16',
      min: 12,
      max: 48,
      step: 1,
      unit: 'px',
      description: '字幕字体大小'
    },
    {
      key: 'subtitle_color',
      category: 'subtitle',
      label: '颜色',
      type: 'color',
      default: '#FFFFFF',
      description: '字幕文字颜色'
    },
    {
      key: 'subtitle_stroke',
      category: 'subtitle',
      label: '描边宽度',
      type: 'number',
      default: '2',
      min: 0,
      max: 6,
      step: 0.5,
      unit: 'px',
      description: '字幕描边宽度'
    },
    {
      key: 'subtitle_bg_opacity',
      category: 'subtitle',
      label: '背景透明度',
      type: 'range',
      default: '0.5',
      min: 0,
      max: 1,
      step: 0.05,
      unit: '',
      description: '字幕背景不透明度（0=透明，1=完全不透明）'
    },
    {
      key: 'subtitle_position',
      category: 'subtitle',
      label: '位置',
      type: 'select',
      default: 'bottom',
      options: [
        { value: 'top', label: '顶部' },
        { value: 'center', label: '居中' },
        { value: 'bottom', label: '底部' }
      ],
      description: '字幕显示位置'
    },
    // 数据库
    {
      key: 'db_path',
      category: 'database',
      label: '数据库路径',
      type: 'readonly',
      default: '',
      description: 'SQLite 数据库文件位置'
    }
  ];

  // ---- 状态 ----
  let activeCategory = $state('appearance');
  $effect(() => {
    // 用 liveQueryParam 而非 $page.url：popstate 重挂载时 page store 只恢复 pathname、
    // 丢掉 query，cat 会退回默认值并被这里写回 URL，覆盖刚返回的历史条目。
    const cat = liveQueryParam('cat');
    if (cat && categories.some((c) => c.id === cat)) {
      activeCategory = cat;
    }
  });
  let values = $state<Record<string, string>>({});
  let loaded = $state(false);
  let loading = $state(false);
  let error = $state<string | null>(null);

  // 保存状态：'idle' | 'saving' | 'saved' | 'error'
  let saveState = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
  let pendingKeys = $state<Set<string>>(new Set());
  let saveTimer: ReturnType<typeof setTimeout> | null = null;

  // 显示密码
  let showKeys = $state<Record<string, boolean>>({});

  // 工具测试状态
  let testingKey = $state<string | null>(null);
  let testResult = $state<Record<string, { ok: boolean; msg: string }>>({});

  // toast
  let toast = $state<string | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  function showToast(msg: string): void {
    toast = msg;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2600);
  }

  const APP_VERSION = '3.0.0';

  // ---- 派生：当前分区设置项 ----
  // mask_restricted 仅在 show_restricted 开启时显示
  // 成人网络源配置（network_allow_adult / network_adult_base_url）同样受 show_restricted 门控——
  // 显示限制内容关闭时，成人相关配置完全不可见（数据隔离）
  const categoryItems = $derived(
    schema.filter((s) => {
      if (s.category !== activeCategory) return false;
      if (s.key === 'mask_restricted' && (values['show_restricted'] ?? 'false') !== 'true') return false;
      if (
        (s.key === 'network_allow_adult' || s.key === 'network_adult_base_url') &&
        (values['show_restricted'] ?? 'false') !== 'true'
      ) return false;
      return true;
    })
  );

  // ---- 初始化默认值 ----
  function initDefaults(): Record<string, string> {
    const map: Record<string, string> = {};
    for (const item of schema) {
      map[item.key] = item.default;
    }
    // 数据库路径默认
    if (!map['db_path']) {
      map['db_path'] = '~/.vitoice/vitoice.db';
    }
    return map;
  }

  // ---- 加载 ----
  async function loadSettings(): Promise<void> {
    loading = true;
    error = null;
    try {
      // noCache=true：绕过 client 层 30s GET 缓存——否则刚保存的开关（如"显示限制内容"）
      // 在 30 秒内返回设置页会读到旧缓存值，表现为"开关又自己弹回去了"。
      const list = await client.get<SettingResponse[]>('/settings', undefined, undefined, true);
      const map = initDefaults();
      for (const s of list ?? []) {
        if (s.value !== null && s.value !== undefined) {
          map[s.key] = s.value;
        }
      }
      // tmdb_base_url 空值在后端语义上等同官方默认（scraper 留空回退），
      // 输入框直接显示默认地址，避免"看起来没配置"
      if (!(map['tmdb_base_url'] ?? '').trim()) {
        map['tmdb_base_url'] = 'https://api.themoviedb.org/3';
      }
      values = map;
      loaded = true;
    } catch (e) {
      error =
        e instanceof ApiError
          ? `加载设置失败：${e.status}`
          : '加载设置失败，请检查后端服务';
      values = initDefaults();
      loaded = true;
    } finally {
      loading = false;
    }
  }

  // ---- 修改值并触发自动保存 ----
  function setValue(key: string, value: string): void {
    values = { ...values, [key]: value };
    pendingKeys = new Set(pendingKeys).add(key);
    scheduleSave();
  }

  function scheduleSave(): void {
    saveState = 'saving';
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      void flushSave();
    }, 500);
  }

  async function flushSave(): Promise<void> {
    if (pendingKeys.size === 0) {
      saveState = 'idle';
      return;
    }
    const keys = Array.from(pendingKeys);
    pendingKeys = new Set();
    try {
      const settings = keys.map((k) => ({ key: k, value: values[k] ?? '' }));
      await client.put('/settings', { settings });
      saveState = 'saved';
      // 直接同步全局 store 内存（不二次 PUT）：媒体页/侧边栏立即响应开关变化，
      // 避免 bulkUpdate 的第二次 PUT + 全量 load 造成的"保存后刷新慢"。
      settings.forEach((s) => settingsStore.setLocal(s.key, s.value));
      setTimeout(() => {
        if (saveState === 'saved') saveState = 'idle';
      }, 1500);
    } catch {
      saveState = 'error';
      // 重新加入待保存
      pendingKeys = new Set([...pendingKeys, ...keys]);
    }
  }

  async function saveAll(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    pendingKeys = new Set(schema.map((s) => s.key));
    await flushSave();
    showToast(saveState === 'error' ? '保存失败' : '已保存全部设置');
  }

  // ---- 工具测试 ----
  async function testTool(item: SettingItem): Promise<void> {
    testingKey = item.key;
    const path = values[item.key] ?? '';
    if (!path) {
      testResult = {
        ...testResult,
        [item.key]: { ok: false, msg: '请先填写路径' }
      };
      testingKey = null;
      return;
    }
    try {
      // 尝试调用后端检测接口（若不存在则视为暂不可用）
      await client.get('/tools/check', { tool: item.key, path });
      testResult = { ...testResult, [item.key]: { ok: true, msg: '可用' } };
    } catch (e) {
      // 后端无此接口（404）时，仅做基础非空校验视为已保存；其他错误视为不可用
      if (e instanceof ApiError && e.status === 404) {
        testResult = {
          ...testResult,
          [item.key]: { ok: true, msg: '路径已保存（在线检测暂不可用）' }
        };
      } else {
        const msg = e instanceof ApiError ? `检测失败（${e.status}）` : '检测失败，请检查路径';
        testResult = { ...testResult, [item.key]: { ok: false, msg } };
      }
    } finally {
      testingKey = null;
    }
  }

  // ---- 孤立缩略图/封面清理 ----
  let assetStats = $state<{ thumbnails: { count: number; bytes: number }; posters: { count: number; bytes: number } } | null>(null);
  let assetStatsLoading = $state(false);
  let assetCleaning = $state(false);

  async function loadAssetStats(): Promise<void> {
    assetStatsLoading = true;
    try {
      const res = await client.get<{
        thumbnails: { count: number; bytes: number; sample: string[] };
        posters: { count: number; bytes: number; sample: string[] };
      }>('/settings/asset-stats');
      assetStats = {
        thumbnails: { count: res?.thumbnails?.count ?? 0, bytes: res?.thumbnails?.bytes ?? 0 },
        posters: { count: res?.posters?.count ?? 0, bytes: res?.posters?.bytes ?? 0 }
      };
    } catch {
      assetStats = null;
    } finally {
      assetStatsLoading = false;
    }
  }

  async function cleanAssets(): Promise<void> {
    if (assetCleaning) return;
    assetCleaning = true;
    try {
      const res = await client.post<{ removed_count: number; freed_bytes: number; remaining: Record<string, { count: number }> }>(
        '/settings/clean-assets',
        {}
      );
      showToast(`已清理 ${res?.removed_count ?? 0} 个孤立文件`);
      await loadAssetStats();
    } catch {
      showToast('清理失败');
    } finally {
      assetCleaning = false;
    }
  }
  // ---- 数据存储位置（自定义数据根） ----
  interface DataRootInfo {
    current: string;
    default: string;
    source: 'dev' | 'env' | 'pointer' | 'default';
    env_override: boolean;
    pointer_file: string;
    db_path: string;
    is_dev: boolean;
  }
  interface DataRootChangeResult {
    ok: boolean;
    message: string;
    restart_required?: boolean;
    old_root?: string;
    new_root?: string;
    moved_dirs?: string[];
    note?: string;
  }
  let dataRootInfo = $state<DataRootInfo | null>(null);
  let dataRootError = $state(false);
  let newDataRoot = $state('');
  let dataRootMigrating = $state(false);
  let dataRootResult = $state<DataRootChangeResult | null>(null);

  async function loadDataRoot(): Promise<void> {
    dataRootError = false;
    try {
      const info = await client.get<DataRootInfo>('/settings/data-root', undefined, undefined, true);
      dataRootInfo = info;
      // 数据库路径只读项显示后端真实路径（替代硬编码默认值）
      values = { ...values, db_path: info.db_path };
      newDataRoot = info.current;
    } catch {
      dataRootError = true;
    }
  }

  async function changeDataRoot(): Promise<void> {
    if (dataRootMigrating) return;
    const target = newDataRoot.trim();
    if (!target) {
      showToast('请填写新的数据目录');
      return;
    }
    if (!window.confirm(
      '将把数据库与缩略图/海报等资产迁移到新位置：\n\n' + target +
      '\n\n迁移过程中请勿关闭应用。迁移完成后需要重启应用生效。继续吗？'
    )) return;
    dataRootMigrating = true;
    dataRootResult = null;
    try {
      const res = await client.post<DataRootChangeResult>('/settings/data-root', { path: target });
      dataRootResult = res;
      showToast(res.message || '迁移完成');
      await loadDataRoot();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : '迁移失败';
      showToast(msg);
    } finally {
      dataRootMigrating = false;
    }
  }

  function dataRootSourceLabel(source: DataRootInfo['source']): string {
    switch (source) {
      case 'dev': return '开发环境';
      case 'env': return '环境变量';
      case 'pointer': return '自定义';
      default: return '默认';
    }
  }

  // ---- 数据库备份 ----
  interface BackupItem { name: string; path: string; size: number; mtime: number }
  let backups = $state<BackupItem[]>([]);
  let backupsLoading = $state(false);
  let backingUp = $state(false);

  async function loadBackups(): Promise<void> {
    backupsLoading = true;
    try {
      const res = await client.get<{ backups: BackupItem[] }>('/settings/backups', undefined, undefined, true);
      backups = res?.backups ?? [];
    } catch {
      backups = [];
    } finally {
      backupsLoading = false;
    }
  }

  async function createBackup(): Promise<void> {
    if (backingUp) return;
    backingUp = true;
    try {
      const res = await client.post<{ ok: boolean; path: string }>('/settings/backup', {});
      showToast(`备份完成：${res.path.split(/[\\/]/).pop() ?? ''}`);
      await loadBackups();
    } catch {
      showToast('备份失败');
    } finally {
      backingUp = false;
    }
  }

  // ---- 重置所有数据（恢复全新安装状态） ----
  interface ResetResult {
    ok: boolean;
    message: string;
    backup_path?: string;
    tables_cleared?: number;
    removed_files?: number;
    freed_bytes?: number;
  }
  let resetDialogOpen = $state(false);
  let resetConfirmText = $state('');
  let resetBusy = $state(false);
  let resetResult = $state<ResetResult | null>(null);

  function openResetDialog(): void {
    resetConfirmText = '';
    resetResult = null;
    resetDialogOpen = true;
  }

  function closeResetDialog(): void {
    if (resetBusy) return;
    resetDialogOpen = false;
  }

  function handleResetKeydown(e: KeyboardEvent): void {
    if (!resetDialogOpen) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeResetDialog();
    }
  }

  async function doResetAllData(): Promise<void> {
    if (resetBusy) return;
    // 输入确认词作为前端闸门；后端再次校验同一确认词（双保险）
    if (resetConfirmText.trim() !== '重置') {
      showToast('请输入"重置"以确认');
      return;
    }
    resetBusy = true;
    try {
      const res = await client.post<ResetResult>('/settings/reset-data', {
        confirm: resetConfirmText.trim()
      });
      resetResult = res;
      showToast(res.message || '已重置');
      await Promise.all([loadBackups(), loadDataRoot()]);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : '重置失败';
      showToast(msg);
    } finally {
      resetBusy = false;
    }
  }

  // ---- AI 连接测试 ----
  // 检测值是否为后端返回的掩码值（****xxxx），掩码值不能作为真实 key 发送
  function isMaskedValue(v: string | undefined): boolean {
    return !!v && v.startsWith('****');
  }

  async function testAI(resultKey: string = 'ai_api_key'): Promise<void> {
    testingKey = resultKey;
    const apiKey = values['ai_api_key'] ?? '';
    if (!apiKey) {
      testResult = {
        ...testResult,
        [resultKey]: { ok: false, msg: '请先填写 API Key' }
      };
      testingKey = null;
      return;
    }
    try {
      const payload = {
        base_url: values['ai_base_url'] ?? 'https://api.openai.com/v1',
        // 掩码值发送 null，让后端回退到数据库中的真实 key
        api_key: isMaskedValue(apiKey) ? null : apiKey,
        model: values['ai_model'] ?? 'gpt-4o-mini'
      };
      const res = await client.post<{ ok: boolean; message?: string; detail?: string }>(
        '/settings/test-ai',
        payload
      );
      const ok = res?.ok ?? true;
      const msg = res?.message || res?.detail || (ok ? '连接成功' : '连接失败');
      testResult = { ...testResult, [resultKey]: { ok, msg } };
    } catch (e) {
      const msg = e instanceof ApiError ? `连接失败（${e.status}）` : '连接失败，请检查配置';
      testResult = { ...testResult, [resultKey]: { ok: false, msg } };
    } finally {
      testingKey = null;
    }
  }

  // ---- TMDB 连接测试 ----
  async function testTMDB(resultKey: string = 'tmdb_api_key'): Promise<void> {
    testingKey = resultKey;
    const apiKey = values['tmdb_api_key'] ?? '';
    if (!apiKey) {
      testResult = {
        ...testResult,
        [resultKey]: { ok: false, msg: '请先填写 API Key' }
      };
      testingKey = null;
      return;
    }
    try {
      const payload = {
        // 掩码值发送 null，让后端回退到数据库中的真实 key
        api_key: isMaskedValue(apiKey) ? null : apiKey,
        base_url: values['tmdb_base_url'] ?? '',
        language: values['tmdb_language'] ?? 'zh-CN'
      };
      const res = await client.post<{ ok: boolean; message?: string; detail?: string }>(
        '/settings/test-tmdb',
        payload
      );
      const ok = res?.ok ?? true;
      const msg = res?.message || res?.detail || (ok ? '连接成功' : '连接失败');
      testResult = { ...testResult, [resultKey]: { ok, msg } };
    } catch (e) {
      const msg = e instanceof ApiError ? `连接失败（${e.status}）` : '连接失败，请检查配置';
      testResult = { ...testResult, [resultKey]: { ok: false, msg } };
    } finally {
      testingKey = null;
    }
  }

  // ---- 统一测试入口：根据 item 类型分派到 testTool / testAI / testTMDB ----
  async function runTest(item: SettingItem): Promise<void> {
    if (item.key === 'ai_api_key') {
      await testAI('ai_api_key');
    } else if (item.key === 'tmdb_api_key') {
      await testTMDB('tmdb_api_key');
    } else if (item.key === 'proxy_host') {
      await testProxy();
    } else {
      await testTool(item);
    }
  }

  // ---- 测试代理连通 ----
  async function testProxy(): Promise<void> {
    const host = (values['proxy_host'] ?? '').trim();
    const port = (values['proxy_port'] ?? '7890').trim();
    if (!host) {
      showToast('请先填写代理地址');
      return;
    }
    testingKey = 'proxy_host';
    try {
      const res = await client.post<{ ok: boolean; message: string }>('/settings/test-proxy', { host, port });
      showToast(res.message || (res.ok ? '代理连通' : '代理连接失败'));
    } catch {
      showToast('测试失败，请检查后端服务');
    } finally {
      testingKey = '';
    }
  }

  // ---- 打开数据目录 ----
  async function openDataDir(): Promise<void> {
    // 优先用后端数据根的真实路径（db_path 只读项可能还是旧默认值）
    const dir = dataRootInfo?.current ?? '';
    // 安全校验：dir 必须是本地路径（盘符开头或 Unix 绝对路径），且不能包含 URL scheme
    const isLocalPath =
      !!dir &&
      !dir.includes('://') &&
      (/^[A-Za-z]:[\\/]/.test(dir) || /^\/.*/.test(dir));
    if (!isLocalPath) {
      showToast('路径不合法，已拒绝打开');
      return;
    }
    if (!isTauriEnv()) {
      showToast('打开目录需在桌面端运行');
      return;
    }
    try {
      // 用 opener 的 openPath：shell.open 默认只放行 mailto/tel/http(s)，
      // 本地目录路径会被其作用域正则拒绝（且 shell.open 自 2.1.0 起已 deprecated）
      const { openPath } = await import('@tauri-apps/plugin-opener');
      await openPath(dir);
    } catch (e) {
      // 透出真实错误，避免把所有失败笼统归因为"非桌面端"
      showToast(`无法打开目录：${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // ---- 选择文件夹路径（工具类） ----
  async function pickPath(item: SettingItem): Promise<void> {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ multiple: false, title: `选择 ${item.label}` });
      if (typeof selected === 'string' && selected) {
        setValue(item.key, selected);
      }
    } catch {
      showToast('无法打开文件选择器');
    }
  }

  function togglePassword(key: string): void {
    showKeys = { ...showKeys, [key]: !showKeys[key] };
  }

  // 范围值派生显示
  function rangeText(item: SettingItem): string {
    const v = values[item.key] ?? item.default;
    return `${v}${item.unit ?? ''}`;
  }

  // 主题应用
  $effect(() => {
    const theme = values['theme'];
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    if (theme === 'light' || theme === 'dark') {
      root.setAttribute('data-theme', theme);
      root.style.colorScheme = theme;
    } else {
      // system 或未设置：移除属性，让 CSS media query 接管
      root.removeAttribute('data-theme');
      root.style.colorScheme = 'light dark';
    }
  });

  onMount(() => {
    void loadSettings();
    void loadDataRoot();
    void loadBackups();
  });

  onDestroy(() => {
    if (saveTimer) {
      clearTimeout(saveTimer);
      saveTimer = null;
      // 离开页面时若有未提交的修改（500ms 防抖窗口内），立即保存，
      // 避免"改完设置马上切走 → 修改丢失"。
      if (pendingKeys.size > 0) void flushSave();
    }
    if (toastTimer) clearTimeout(toastTimer);
  });
</script>

<svelte:head><title>设置 — vitoice</title></svelte:head>

<!-- ---- SVG 图标 snippets ---- -->
{#snippet catIcon(id: string)}
  {#if id === 'appearance'}
    <!-- 太阳：主题/外观 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="4"></circle>
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"></path>
    </svg>
  {:else if id === 'content'}
    <!-- 盾牌：内容管理 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
    </svg>
  {:else if id === 'tools'}
    <!-- 扳手：外部工具 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
    </svg>
  {:else if id === 'thumbnail'}
    <!-- 图片：缩略图 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
      <circle cx="9" cy="9" r="2"></circle>
      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"></path>
    </svg>
  {:else if id === 'ai'}
    <!-- 星星/闪光：AI 配置 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .962 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.962 0z"></path>
      <path d="M20 3v4M22 5h-4M4 17v2M5 18H3"></path>
    </svg>
  {:else if id === 'scrape'}
    <!-- 场记板：刮削 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20.2 6 3 11l-.9-2.4c-.3-.9.2-1.9 1-2.2l14-4.5c.9-.3 1.9.2 2.2 1z"></path>
      <path d="m6.2 5.3 3.1 3.9M12.4 3.4l3.1 4M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
    </svg>
  {:else if id === 'player'}
    <!-- 播放：播放器 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <polygon points="10 8 16 12 10 16 10 8" fill="currentColor"></polygon>
    </svg>
  {:else if id === 'subtitle'}
    <!-- 对话气泡：字幕 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
    </svg>
  {:else if id === 'database'}
    <!-- 圆柱体：数据库 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
      <path d="M3 5v14a9 3 0 0 0 18 0V5"></path>
      <path d="M3 12a9 3 0 0 0 18 0"></path>
    </svg>
  {:else if id === 'about'}
    <!-- 信息圆圈：关于 -->
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <line x1="12" y1="16" x2="12" y2="12"></line>
      <line x1="12" y1="8" x2="12.01" y2="8"></line>
    </svg>
  {/if}
{/snippet}

{#snippet eyeIcon()}
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"></path>
    <circle cx="12" cy="12" r="3"></circle>
  </svg>
{/snippet}

{#snippet eyeOffIcon()}
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"></path>
    <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"></path>
    <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"></path>
    <line x1="2" y1="2" x2="22" y2="22"></line>
  </svg>
{/snippet}

{#snippet folderIcon()}
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2z"></path>
  </svg>
{/snippet}

{#snippet testResultDisplay(result: { ok: boolean; msg: string })}
  <div class="test-result" class:ok={result.ok} class:fail={!result.ok}>
    <span class="test-symbol">{result.ok ? '✓' : '✗'}</span>
    <span class="test-text">{result.msg}</span>
  </div>
{/snippet}

<div class="settings-page">
  <!-- 右侧设置内容 -->
  <section class="cat-content">
    {#if loading && !loaded}
      <div class="state">加载中…</div>
    {:else if error && !loaded}
      <div class="state error">{error}</div>
    {:else}
      <div class="content-head">
        <h2>{categories.find((c) => c.id === activeCategory)?.label ?? ''}</h2>
        {#if activeCategory === 'about'}
          <span class="version-tag">v{APP_VERSION}</span>
        {/if}
      </div>

      {#if activeCategory === 'about'}
        <!-- 关于分区：静态信息 -->
        <div class="about-block">
          <img class="about-mark" src="/logo-mark.png" width="64" height="64" alt="vitoice logo" />
          <div class="about-logo">vitoice</div>
          <div class="about-version">版本 {APP_VERSION}</div>
          <p class="about-desc">
            vitoice 是一款桌面媒体管理应用，支持本地与网络资源的统一管理、智能打标、片段管理与播放。
          </p>
          <dl class="about-list">
            <div class="about-row">
              <dt>项目</dt>
              <dd>vitoice</dd>
            </div>
            <div class="about-row">
              <dt>技术栈</dt>
              <dd>Tauri · Svelte · FastAPI · SQLite</dd>
            </div>
            <div class="about-row">
              <dt>许可</dt>
              <dd>私有</dd>
            </div>
          </dl>
        </div>
      {:else}
        <!-- 设置项列表 -->
        {#if activeCategory === 'ai'}
          <!-- AI 功能说明 -->
          <div class="ai-doc">
            <h3 class="ai-doc-title">AI 功能说明</h3>
            <div class="ai-doc-body">
              <div class="ai-doc-item">
                <span class="ai-doc-icon">⚡</span>
                <div>
                  <strong>自动打标</strong>
                  <p>导入媒体后自动调用 AI 分析文件名和元数据，生成标签建议。在"导入时自动触发"开启时，扫描完成后自动执行。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">🔍</span>
                <div>
                  <strong>智能刮削</strong>
                  <p>当 TMDB 刮削失败时，可使用 AI 分析文件名提取关键信息（标题、年份），再进行二次 TMDB 匹配，提高刮削成功率。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">🏷️</span>
                <div>
                  <strong>快速打标</strong>
                  <p>在播放器中按 T 键唤出快速打标面板，AI 会根据当前媒体信息推荐标签，点击即可应用。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">💡</span>
                <div>
                  <strong>提示词</strong>
                  <p>AI 打标使用内置优化提示词，无需手动配置。系统会根据媒体类型（电影/电视剧/限制内容）自动选择合适的提示策略。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">①</span>
                <div>
                  <strong>获取 Token</strong>
                  <p>从任意 OpenAI 兼容服务商获取密钥，如
                    <button class="inlink" type="button" onclick={() => openExternalUrl('https://platform.openai.com/api-keys')}>OpenAI</button>、
                    <button class="inlink" type="button" onclick={() => openExternalUrl('https://platform.deepseek.com/api_keys')}>DeepSeek</button>、
                    <button class="inlink" type="button" onclick={() => openExternalUrl('https://platform.moonshot.cn')}>Kimi（Moonshot）</button>。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">②</span>
                <div>
                  <strong>填写地址与令牌</strong>
                  <p>「API 地址」填服务商接口（默认 https://api.openai.com/v1，需以 /v1 结尾），「API Token」粘贴密钥。点击「测试」验证连通。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">③</span>
                <div>
                  <strong>选择模型</strong>
                  <p>「模型名称」填服务商支持的模型，如 gpt-4o-mini、deepseek-chat、moonshot-v1-8k。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">④</span>
                <div>
                  <strong>开启自动打标</strong>
                  <p>打开「导入时自动打标」开关，扫描完成后即自动为媒体生成标签。</p>
                </div>
              </div>
              <div class="ai-doc-note">
                <strong>说明：</strong>所有字段仅本地存储、不上传。使用的模型需支持 OpenAI 兼容的 /chat/completions 接口，绝大多数主流服务商均兼容。
              </div>
            </div>
          </div>
        {/if}
        {#if activeCategory === 'scrape'}
          <!-- TMDB API Key 获取与配置说明 -->
          <div class="ai-doc">
            <h3 class="ai-doc-title">TMDB Key 获取与配置</h3>
            <div class="ai-doc-body">
              <div class="ai-doc-item">
                <span class="ai-doc-icon">①</span>
                <div>
                  <strong>注册 TMDB 账号</strong>
                  <p>打开
                    <button class="inlink" type="button" onclick={() => openExternalUrl('https://www.themoviedb.org')}>
                      themoviedb.org
                    </button>
                    免费注册并登录。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">②</span>
                <div>
                  <strong>申请 API 密钥</strong>
                  <p>在「设置 → API」页面点击「创建 / Create」，用途选择 Developer，填写应用名称与简介后提交，密钥即时可用。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">③</span>
                <div>
                  <strong>填入密钥</strong>
                  <p>将 v3 API Key（32 位十六进制）粘贴到上方「TMDB API Key」，或使用 v4 读取令牌（eyJ 开头）。点击「测试」验证连通性。</p>
                </div>
              </div>
              <div class="ai-doc-item">
                <span class="ai-doc-icon">④</span>
                <div>
                  <strong>可选配置</strong>
                  <p>「刮削语言」控制标题与简介的返回语言；直连不通时可填「API Base URL」反代地址（默认 https://api.themoviedb.org/3）。</p>
                </div>
              </div>
              <div class="ai-doc-note">
                <strong>说明：</strong>密钥仅在本地存储、绝不上传，安全可靠。未配置密钥时，导入媒体将跳过 TMDB 元数据（标题/年份/简介/海报）刮削，但本地文件解析与限制内容刮削不受影响。
              </div>
            </div>
          </div>
        {/if}
        <div class="settings-list">
          {#if activeCategory === 'scrape'}
            <SourceManager />
          {/if}
          {#each categoryItems as item (item.key)}
            <div class="setting-row">
              <div class="setting-label">
                <span class="label-text">{item.label}</span>
                {#if item.description}
                  <span class="label-desc">{item.description}</span>
                {/if}
              </div>
              <div class="setting-control">
                {#if item.type === 'text'}
                  <div class="input-with-action">
                    <input
                      type="text"
                      class="text-input"
                      value={values[item.key] ?? ''}
                      placeholder=""
                      oninput={(e) => setValue(item.key, (e.target as HTMLInputElement).value)}
                    />
                    {#if item.pickable}
                      <button class="action-btn icon-only" title="选择文件" onclick={() => pickPath(item)}>
                        {@render folderIcon()}
                      </button>
                    {/if}
                    {#if item.testable}
                      <button
                        class="action-btn test-btn"
                        onclick={() => runTest(item)}
                        disabled={testingKey === item.key}
                      >
                        {testingKey === item.key ? '测试中…' : '测试'}
                      </button>
                    {/if}
                  </div>
                {:else if item.type === 'password'}
                  <div class="input-with-action">
                    <input
                      type={showKeys[item.key] ? 'text' : 'password'}
                      class="text-input"
                      value={values[item.key] ?? ''}
                      oninput={(e) => setValue(item.key, (e.target as HTMLInputElement).value)}
                      placeholder="••••••••"
                      autocomplete="off"
                    />
                    <button
                      class="action-btn icon-only"
                      title={showKeys[item.key] ? '隐藏' : '显示'}
                      onclick={() => togglePassword(item.key)}
                    >
                      {#if showKeys[item.key]}
                        {@render eyeOffIcon()}
                      {:else}
                        {@render eyeIcon()}
                      {/if}
                    </button>
                    {#if item.testable}
                      <button
                        class="action-btn test-btn"
                        onclick={() => runTest(item)}
                        disabled={testingKey === item.key}
                      >
                        {testingKey === item.key ? '测试中…' : '测试'}
                      </button>
                    {/if}
                  </div>
                {:else if item.type === 'number'}
                  <div class="number-row">
                    <input
                      type="number"
                      class="text-input"
                      value={values[item.key] ?? item.default}
                      min={item.min}
                      max={item.max}
                      step={item.step}
                      oninput={(e) => setValue(item.key, (e.target as HTMLInputElement).value)}
                    />
                    {#if item.unit}<span class="unit">{item.unit}</span>{/if}
                  </div>
                {:else if item.type === 'range'}
                  <div class="range-row">
                    <input
                      type="range"
                      class="range-input"
                      value={values[item.key] ?? item.default}
                      min={item.min}
                      max={item.max}
                      step={item.step}
                      oninput={(e) => setValue(item.key, (e.target as HTMLInputElement).value)}
                    />
                    <span class="range-value">{rangeText(item)}</span>
                  </div>
                {:else if item.type === 'select'}
                  <select
                    class="select-input"
                    value={values[item.key] ?? item.default}
                    onchange={(e) => setValue(item.key, (e.target as HTMLSelectElement).value)}
                  >
                    {#each item.options ?? [] as opt (opt.value)}
                      <option value={opt.value}>{opt.label}</option>
                    {/each}
                  </select>
                {:else if item.type === 'toggle'}
                  <button
                    type="button"
                    class="toggle"
                    class:on={(values[item.key] ?? item.default) === 'true'}
                    onclick={() => setValue(item.key, (values[item.key] ?? item.default) === 'true' ? 'false' : 'true')}
                    role="switch"
                    aria-checked={(values[item.key] ?? item.default) === 'true'}
                    aria-label={item.label}
                  >
                    <span class="knob"></span>
                  </button>
                {:else if item.type === 'color'}
                  <div class="color-row">
                    <input
                      type="color"
                      class="color-input"
                      value={values[item.key] ?? item.default}
                      oninput={(e) => setValue(item.key, (e.target as HTMLInputElement).value)}
                    />
                    <span class="color-text">{values[item.key] ?? item.default}</span>
                  </div>
                {:else if item.type === 'readonly'}
                  <div class="input-with-action">
                    <input
                      type="text"
                      class="text-input readonly"
                      value={values[item.key] ?? item.default}
                      readonly
                    />
                    {#if item.key === 'db_path'}
                      <button class="action-btn" onclick={openDataDir}>打开数据目录</button>
                    {/if}
                  </div>
                {/if}

                {#if testResult[item.key]}
                  {@render testResultDisplay(testResult[item.key])}
                {/if}
              </div>
            </div>
          {/each}
        </div>

        {#if activeCategory === 'ai'}
          <!-- AI 分区：整体测试连接按钮 -->
          <div class="section-action">
            <button
              class="primary-btn section-action-btn"
              onclick={() => testAI('ai_connection')}
              disabled={testingKey === 'ai_connection'}
            >
              {testingKey === 'ai_connection' ? '测试中…' : '测试连接'}
            </button>
            {#if testResult.ai_connection}
              {@render testResultDisplay(testResult.ai_connection)}
            {/if}
          </div>
        {/if}
        {#if activeCategory === 'scrape'}
          <!-- 刮削分区：整体测试连接按钮 -->
          <div class="section-action">
            <button
              class="primary-btn section-action-btn"
              onclick={() => testTMDB('tmdb_connection')}
              disabled={testingKey === 'tmdb_connection'}
            >
              {testingKey === 'tmdb_connection' ? '测试中…' : '测试 TMDB 连接'}
            </button>
            {#if testResult.tmdb_connection}
              {@render testResultDisplay(testResult.tmdb_connection)}
            {/if}
          </div>
        {/if}
        {#if activeCategory === 'database'}
          <!-- 数据库分区：数据存储位置 -->
          <div class="section-block">
            <h3 class="section-title">数据存储位置</h3>
            <p class="section-desc">
              数据库与缩略图/海报等资产的根目录。默认在用户目录 .vitoice 下，可迁移到其他磁盘。
            </p>
            {#if dataRootInfo}
              <div class="dataroot-current">
                <span class="dataroot-label" class:custom={dataRootInfo.source === 'pointer'}>
                  {dataRootSourceLabel(dataRootInfo.source)}
                </span>
                <code class="dataroot-path">{dataRootInfo.current}</code>
              </div>
              {#if dataRootInfo.is_dev}
                <p class="dataroot-note">开发环境固定使用 backend/data，不支持迁移。</p>
              {:else if dataRootInfo.env_override}
                <p class="dataroot-note">已设置 VITOICE_DATA_ROOT 环境变量，应用内更改不生效。</p>
              {:else}
                <div class="dataroot-form">
                  <input
                    class="dataroot-input"
                    type="text"
                    bind:value={newDataRoot}
                    placeholder="例如 D:\\vitoice-data"
                    disabled={dataRootMigrating}
                  />
                  <button
                    class="primary-btn"
                    onclick={changeDataRoot}
                    disabled={dataRootMigrating || newDataRoot.trim() === dataRootInfo.current}
                  >
                    {dataRootMigrating ? '迁移中…' : '迁移数据'}
                  </button>
                </div>
                {#if dataRootResult?.ok}
                  <div class="dataroot-result">
                    <strong>✓ {dataRootResult.message}</strong>
                    <p>新位置：{dataRootResult.new_root}</p>
                    <p>已移动：{dataRootResult.moved_dirs?.length ? dataRootResult.moved_dirs.join('、') : '无资产目录'}</p>
                    <p>{dataRootResult.note}</p>
                    <p class="dataroot-restart">请关闭应用后重新启动以使用新位置。</p>
                  </div>
                {/if}
              {/if}
            {:else if dataRootError}
              <p class="dataroot-note">无法读取数据位置信息（后端未连接？）。</p>
            {:else}
              <p class="dataroot-note">加载中…</p>
            {/if}
          </div>

          <!-- 数据库分区：自动备份 -->
          <div class="section-block">
            <h3 class="section-title">数据库备份</h3>
            <p class="section-desc">
              每日自动备份一次数据库（保留最近 7 份），存放于数据目录的 backups 文件夹。
            </p>
            <div class="section-action">
              <button
                class="action-btn"
                onclick={createBackup}
                disabled={backingUp}
              >
                {backingUp ? '备份中…' : '立即备份'}
              </button>
              {#if backups.length > 0}
                <span class="asset-summary">{backups.length} 份备份</span>
              {/if}
            </div>
            {#if backups.length > 0}
              <ul class="backup-list">
                {#each backups.slice(0, 7) as b (b.name)}
                  <li class="backup-item">
                    <code>{b.name}</code>
                    <span>{formatBytes(b.size)}</span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <!-- 数据库分区：孤立缩略图/封面清理 -->
          <div class="section-block">
            <h3 class="section-title">存储清理</h3>
            <p class="section-desc">
              检测媒体记录已不存在但仍留在磁盘上的缩略图与封面文件（通常由彻底删除媒体产生）。
            </p>
            <div class="section-action">
              <button
                class="action-btn"
                onclick={() => loadAssetStats()}
                disabled={assetStatsLoading}
              >
                {assetStatsLoading ? '扫描中…' : '扫描孤立文件'}
              </button>
              {#if assetStats}
                <span class="asset-summary">
                  缩略图 {assetStats.thumbnails.count} 个 / 封面 {assetStats.posters.count} 个
                  （约 {formatBytes(assetStats.thumbnails.bytes + assetStats.posters.bytes)}）
                </span>
              {/if}
            </div>
            {#if assetStats && assetStats.thumbnails.count + assetStats.posters.count > 0}
              <div class="section-action danger-row">
                <button
                  class="primary-btn danger-btn"
                  onclick={() => cleanAssets()}
                  disabled={assetCleaning}
                >
                  {assetCleaning ? '清理中…' : '清理孤立文件'}
                </button>
              </div>
            {/if}
          </div>

          <!-- 数据库分区：重置所有数据 -->
          <div class="section-block">
            <h3 class="section-title">重置所有数据</h3>
            <p class="section-desc">
              清空全部媒体库、媒体、标签、系列、任务与设置，恢复到全新安装状态。
              重置前自动备份当前数据库到 backups 文件夹（pre-reset-*.db，不参与自动轮换）；
              备份文件与数据位置设置会保留。
            </p>
            <div class="section-action danger-row">
              <button
                class="primary-btn danger-btn"
                onclick={openResetDialog}
                disabled={resetBusy}
              >
                {resetBusy ? '重置中…' : '重置所有数据…'}
              </button>
            </div>
            {#if resetResult?.ok}
              <div class="dataroot-result">
                <strong>✓ {resetResult.message}</strong>
                <p>备份位置：<code>{resetResult.backup_path}</code></p>
                <p>
                  已清空 {resetResult.tables_cleared ?? 0} 张表，清理 {resetResult.removed_files ?? 0} 个资产文件
                  （约 {formatBytes(resetResult.freed_bytes ?? 0)}）
                </p>
                <p class="dataroot-restart">当前页面数据已失效，建议重启应用或刷新页面。</p>
              </div>
            {/if}
          </div>
        {/if}
      {/if}
    {/if}
  </section>
</div>

<!-- 重置所有数据：多层确认对话框（说明后果 + 输入确认词；后端二次校验） -->
<svelte:window onkeydown={handleResetKeydown} />
{#if resetDialogOpen}
  <div
    class="reset-backdrop"
    role="presentation"
    onclick={(e) => { if (e.target === e.currentTarget) closeResetDialog(); }}
  >
    <div class="reset-dialog" role="dialog" aria-modal="true" aria-labelledby="reset-dialog-title">
      <div class="reset-head">
        <h2 id="reset-dialog-title">重置所有数据</h2>
      </div>
      <div class="reset-body">
        <p>此操作将<strong>永久删除</strong>以下内容：</p>
        <ul>
          <li>全部媒体库与媒体记录</li>
          <li>标签、分段、系列、智能文件夹、任务记录</li>
          <li>全部设置（含 AI / TMDB 密钥、刮削源、代理配置）</li>
          <li>缩略图、截图、海报、剧照等缓存与资产文件</li>
        </ul>
        <p>
          重置前会自动备份当前数据库到 backups 文件夹
          （pre-reset-*.db，不参与自动轮换，可随时手动恢复）；数据位置设置保留。
        </p>
        <div class="reset-confirm-row">
          <label for="reset-confirm-input">请输入 <strong>重置</strong> 以确认：</label>
          <input
            id="reset-confirm-input"
            class="reset-input"
            type="text"
            bind:value={resetConfirmText}
            placeholder="重置"
            disabled={resetBusy}
          />
        </div>
      </div>
      <div class="reset-foot">
        <button class="reset-btn" onclick={closeResetDialog} disabled={resetBusy}>取消</button>
        <button
          class="reset-btn danger"
          onclick={doResetAllData}
          disabled={resetBusy || resetConfirmText.trim() !== '重置'}
        >
          {resetBusy ? '重置中…' : '确认重置'}
        </button>
      </div>
    </div>
  </div>
{/if}

{#if toast}
  <div class="toast">{toast}</div>
{/if}

<style>
  .settings-page {
    display: flex;
    flex: 1;
    min-height: 0;
  }

  .primary-btn {
    border: none;
    border-radius: var(--radius);
    background: var(--accent);
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    font-family: var(--font-body);
    transition: background var(--dur) var(--ease-out), opacity var(--dur) var(--ease-out);
    cursor: pointer;
  }

  .primary-btn:hover:not(:disabled) {
    background: var(--accent-hover);
  }

  .primary-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* ============ 右侧内容 ============ */
  .cat-content {
    flex: 1;
    overflow-y: auto;
    padding: 32px;
    min-width: 0;
    background: var(--bg);
  }

  .content-head {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 24px;
  }

  .content-head h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    color: var(--ink);
  }

  .version-tag {
    padding: 2px 10px;
    background: var(--accent-soft);
    color: var(--accent);
    border-radius: var(--radius-full);
    font-size: 12px;
    font-weight: 600;
  }

  .state {
    padding: 80px 0;
    text-align: center;
    color: var(--ink-tertiary);
    font-size: 14px;
  }

  .state.error {
    color: var(--danger);
  }

  /* ============ 设置项列表 ============ */
  .settings-list {
    display: flex;
    flex-direction: column;
    max-width: 720px;
  }

  .setting-row {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 24px;
    padding: 20px 0;
    border-bottom: 1px solid var(--rule-light);
    align-items: flex-start;
  }

  .setting-row:last-child {
    border-bottom: none;
  }

  .setting-label {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding-top: 6px;
  }

  .label-text {
    font-size: 13.5px;
    font-weight: 600;
    color: var(--ink);
  }

  .label-desc {
    font-size: 11.5px;
    color: var(--ink-tertiary);
    line-height: 1.5;
  }

  .setting-control {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  /* ============ 输入控件统一样式 ============ */
  .text-input {
    width: 100%;
    height: 34px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-surface);
    color: var(--ink);
    font-size: 13px;
    font-family: var(--font-body);
    transition: border-color var(--dur) var(--ease-out), box-shadow var(--dur) var(--ease-out);
  }

  .text-input::placeholder {
    color: var(--ink-faint);
  }

  .text-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .text-input.readonly {
    background: var(--bg-elevated);
    color: var(--ink-secondary);
    cursor: default;
  }

  .text-input.readonly:focus {
    border-color: var(--rule);
    box-shadow: none;
  }

  /* input + 行内按钮组合：统一 380px 宽度 */
  .input-with-action {
    display: flex;
    align-items: center;
    gap: 8px;
    width: min(100%, 380px);
  }

  .input-with-action .text-input {
    flex: 1;
    min-width: 0;
  }

  /* number + 单位组合：统一 380px 宽度 */
  .number-row {
    display: flex;
    align-items: center;
    gap: 8px;
    width: min(100%, 380px);
  }

  .number-row .text-input {
    flex: 1;
    min-width: 0;
  }

  .unit {
    font-size: 12.5px;
    color: var(--ink-tertiary);
    flex-shrink: 0;
  }

  /* select：统一 380px 宽度 */
  .select-input {
    width: min(100%, 380px);
    height: 34px;
    padding: 0 32px 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-surface);
    color: var(--ink);
    font-size: 13px;
    font-family: var(--font-body);
    transition: border-color var(--dur) var(--ease-out), box-shadow var(--dur) var(--ease-out);
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23a8a8b3' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    cursor: pointer;
  }

  .select-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  /* range：固定 240px 宽度 */
  .range-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .range-input {
    width: 240px;
    flex-shrink: 0;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: var(--rule);
    border-radius: var(--radius-full);
    outline: none;
    cursor: pointer;
  }

  .range-input::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 16px;
    height: 16px;
    border-radius: var(--radius-full);
    background: var(--accent);
    cursor: pointer;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    transition: transform var(--dur-fast) var(--ease-out);
  }

  .range-input::-webkit-slider-thumb:hover {
    transform: scale(1.2);
  }

  .range-input::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--accent);
    cursor: pointer;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  }

  .range-value {
    min-width: 56px;
    font-size: 12.5px;
    color: var(--ink);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    font-family: var(--font-mono);
  }

  /* toggle：固定 44×24 */
  .toggle {
    width: 44px;
    height: 24px;
    border-radius: var(--radius-full);
    background: var(--rule);
    border: none;
    padding: 2px;
    display: flex;
    align-items: center;
    transition: background var(--dur) var(--ease-out);
    flex-shrink: 0;
    cursor: pointer;
  }

  .toggle.on {
    background: var(--accent);
  }

  .knob {
    width: 20px;
    height: 20px;
    border-radius: var(--radius-full);
    background: #fff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
    transition: transform var(--dur) var(--ease-spring);
  }

  .toggle.on .knob {
    transform: translateX(20px);
  }

  /* color：固定 80px 输入 + 色值文字 */
  .color-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .color-input {
    width: 80px;
    height: 34px;
    padding: 2px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-surface);
    cursor: pointer;
    transition: border-color var(--dur) var(--ease-out);
  }

  .color-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .color-text {
    font-size: 12.5px;
    color: var(--ink-tertiary);
    font-family: var(--font-mono);
  }

  /* ============ 行内动作按钮（选择 / 显示 / 测试） ============ */
  .action-btn {
    height: 34px;
    padding: 0 14px;
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--bg-surface);
    color: var(--ink-secondary);
    font-size: 12.5px;
    font-weight: 500;
    font-family: var(--font-body);
    white-space: nowrap;
    transition: border-color var(--dur) var(--ease-out), color var(--dur) var(--ease-out), background var(--dur) var(--ease-out);
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }

  .action-btn.icon-only {
    width: 34px;
    padding: 0;
  }

  .action-btn svg {
    width: 14px;
    height: 14px;
  }

  .action-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* ============ 测试结果显示 ============ */
  .test-result {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    padding: 4px 0 0;
    line-height: 1.4;
  }

  .test-result.ok {
    color: var(--ok);
  }

  .test-result.fail {
    color: var(--danger);
  }

  .test-symbol {
    font-weight: 700;
    font-size: 13px;
    flex-shrink: 0;
  }

  .test-text {
    color: var(--ink-secondary);
  }

  .test-result.ok .test-text {
    color: var(--ok);
  }

  .test-result.fail .test-text {
    color: var(--danger);
  }

  /* ============ AI 分区：整体测试连接 ============ */
  .section-action {
    margin-top: 28px;
    padding-top: 20px;
    border-top: 1px solid var(--rule-light);
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    max-width: 720px;
  }

  .section-action-btn {
    height: 36px;
    padding: 0 20px;
  }

  /* ============ 数据库分区：数据存储位置 / 备份 ============ */
  .dataroot-current {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 14px;
    min-width: 0;
  }

  .dataroot-label {
    flex-shrink: 0;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 99px;
    background: var(--rule-light);
    color: var(--ink-secondary);
  }

  .dataroot-label.custom {
    background: color-mix(in srgb, var(--accent) 15%, transparent);
    color: var(--accent);
  }

  .dataroot-path {
    font-size: 12px;
    color: var(--ink-secondary);
    word-break: break-all;
  }

  .dataroot-note {
    margin: 10px 0 0;
    font-size: 12px;
    color: var(--ink-tertiary, var(--ink-secondary));
  }

  .dataroot-form {
    display: flex;
    gap: 10px;
    margin-top: 14px;
  }

  .dataroot-input {
    flex: 1;
    min-width: 0;
    height: 36px;
    padding: 0 12px;
    border: 1px solid var(--rule-light);
    border-radius: var(--radius);
    background: var(--bg-surface);
    color: var(--ink);
    font-size: 13px;
    font-family: var(--font-body);
  }

  .dataroot-input:focus {
    outline: none;
    border-color: var(--accent);
  }

  .dataroot-result {
    margin-top: 14px;
    padding: 12px 14px;
    border-radius: var(--radius);
    background: color-mix(in srgb, var(--ok) 8%, transparent);
    font-size: 12px;
    line-height: 1.7;
    color: var(--ink-secondary);
  }

  .dataroot-result strong {
    color: var(--ok);
  }

  .dataroot-result p {
    margin: 2px 0 0;
  }

  .dataroot-restart {
    font-weight: 600;
    color: var(--ink);
  }

  .backup-list {
    list-style: none;
    margin: 14px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .backup-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    color: var(--ink-secondary);
  }

  .backup-item code {
    font-family: var(--font-mono, monospace);
    word-break: break-all;
  }

  /* ============ 数据库分区：存储清理 ============ */
  .section-block {
    margin-top: 28px;
    padding-top: 20px;
    border-top: 1px solid var(--rule-light);
    max-width: 720px;
  }

  .section-title {
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 600;
    color: var(--ink);
  }

  .section-desc {
    margin: 0 0 12px;
    font-size: 13px;
    color: var(--ink-tertiary);
    line-height: 1.5;
  }

  .asset-summary {
    font-size: 13px;
    color: var(--ink-secondary);
  }

  .danger-row {
    margin-top: 12px;
  }

  .danger-btn {
    background: var(--danger);
    border-color: var(--danger);
    color: #fff;
  }

  .danger-btn:hover {
    filter: brightness(1.1);
  }

  /* ============ 关于 ============ */
  .about-block {
    max-width: 480px;
  }

  .about-mark {
    display: block;
    width: 64px;
    height: 64px;
    border-radius: 14px;
    margin-bottom: 12px;
  }

  .about-logo {
    font-size: 32px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: 0;
    margin-bottom: 4px;
    font-family: var(--font-display);
  }

  .about-version {
    font-size: 13px;
    color: var(--ink-tertiary);
    margin-bottom: 20px;
  }

  .about-desc {
    font-size: 13px;
    color: var(--ink-secondary);
    line-height: 1.7;
    margin: 0 0 24px;
  }

  .about-list {
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    overflow: hidden;
    margin: 0;
  }

  .about-row {
    display: grid;
    grid-template-columns: 100px 1fr;
    padding: 10px 14px;
    border-top: 1px solid var(--rule-light);
    font-size: 13px;
  }

  .about-row:first-child {
    border-top: none;
  }

  .about-row dt {
    color: var(--ink-tertiary);
    margin: 0;
  }

  .about-row dd {
    color: var(--ink);
    margin: 0;
  }

  /* ============ Toast ============ */
  .toast {
    position: fixed;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 18px;
    background: var(--ink);
    color: var(--bg);
    border-radius: var(--radius-full);
    font-size: 13px;
    font-weight: 500;
    z-index: 2000;
    box-shadow: var(--shadow-lg);
    animation: toast-in var(--dur) var(--ease-out);
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translate(-50%, 10px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  /* ============ AI 功能说明 ============ */
  .ai-doc {
    background: var(--bg-surface);
    border: 1px solid var(--rule);
    border-radius: var(--radius-lg);
    padding: 20px;
    margin-bottom: 20px;
  }
  .ai-doc-title {
    margin: 0 0 14px;
    font-size: 15px;
    font-weight: 700;
    color: var(--ink);
  }
  .ai-doc-body {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .ai-doc-item {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }
  .ai-doc-icon {
    font-size: 18px;
    line-height: 1.4;
    flex-shrink: 0;
  }
  .ai-doc-item strong {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 2px;
  }
  .ai-doc-item p {
    margin: 0;
    font-size: 12px;
    color: var(--ink-tertiary);
    line-height: 1.5;
  }
  .ai-doc-note {
    padding: 10px 12px;
    background: var(--accent-soft);
    border-radius: var(--radius);
    font-size: 12px;
    color: var(--ink-secondary);
    line-height: 1.6;
  }
  .ai-doc-note strong {
    color: var(--accent);
  }

  /* 说明块内的可点击链接（TMDB 官方站） */
  .ai-doc-item .inlink {
    padding: 0;
    background: none;
    border: none;
    font: inherit;
    color: var(--accent);
    text-decoration: underline;
    cursor: pointer;
  }
  .ai-doc-item .inlink:hover {
    text-decoration: none;
    color: var(--accent-strong, var(--accent));
  }

  /* ---- 重置所有数据：确认对话框 ---- */
  .reset-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.32);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: resetFade 200ms ease;
  }
  @keyframes resetFade {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  .reset-dialog {
    width: 100%;
    max-width: 460px;
    background: var(--bg2);
    border-radius: var(--radius-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
    overflow: hidden;
    animation: resetPop 200ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  @keyframes resetPop {
    from { opacity: 0; transform: translateY(-8px) scale(0.96); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }
  .reset-head {
    padding: 20px 24px 0;
  }
  .reset-head h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--accent2, #ff3b30);
  }
  .reset-body {
    padding: 10px 24px 4px;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.6;
  }
  .reset-body ul {
    margin: 6px 0;
    padding-left: 20px;
  }
  .reset-body strong {
    color: var(--ink);
  }
  .reset-confirm-row {
    margin: 14px 0 8px;
  }
  .reset-confirm-row label {
    display: block;
    margin-bottom: 6px;
    color: var(--ink);
  }
  .reset-input {
    width: 100%;
    height: 34px;
    padding: 0 12px;
    border: 1px solid var(--rule);
    border-radius: var(--radius, 8px);
    background: var(--bg);
    color: var(--ink);
    font-size: 13px;
  }
  .reset-input:focus {
    outline: none;
    border-color: var(--accent2, #ff3b30);
  }
  .reset-foot {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    padding: 12px 24px 20px;
  }
  .reset-btn {
    height: 34px;
    padding: 0 16px;
    border: 1px solid var(--rule);
    border-radius: var(--radius, 8px);
    background: var(--bg2);
    color: var(--ink);
    font-size: 13px;
    font-weight: 500;
    transition: all 200ms ease;
  }
  .reset-btn:hover:not(:disabled) {
    border-color: var(--muted);
  }
  .reset-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .reset-btn.danger {
    background: #ff3b30;
    border-color: #ff3b30;
    color: #fff;
  }
  .reset-btn.danger:hover:not(:disabled) {
    filter: brightness(1.08);
  }
</style>
