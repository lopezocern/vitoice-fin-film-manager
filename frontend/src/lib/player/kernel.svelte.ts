/**
 * 播放内核门面：统一「mpv 原生内核」与「<video> 回退」两条后端。
 *
 * - 桌面端（Tauri）：mpv 以 wid 子窗口嵌入当前窗口，WebView 只叠控制层；
 *   mpv 自己解码，HEVC/AC3/DTS/MKV 不再需要后端实时转码。
 * - 浏览器端（npm run dev 调试）：继续用 <video>，保留原有能力。
 *
 * 页面只与本类交互，不再直接操作 <video> 元素或 mpv 命令。
 */
import type { UnlistenFn } from '@tauri-apps/api/event';
import { invoke } from '@tauri-apps/api/core';
import {
  isTauriRuntime,
  mpvCommand,
  mpvDestroy,
  mpvGetProperty,
  mpvInit,
  mpvListen,
  mpvSetProperty,
  mpvSetVideoMarginRatio,
  type MpvEvent,
  type MpvFormat,
  type VideoMarginRatio
} from './mpv';

/** 需要持续同步到前端的 mpv 属性（格式串与 wrapper 的 observe 调用一致）。 */
const OBSERVED: Record<string, MpvFormat> = {
  pause: 'flag',
  'time-pos': 'double',
  duration: 'double',
  'eof-reached': 'flag',
  'paused-for-cache': 'flag',
  'demuxer-cache-time': 'double',
  width: 'int64',
  height: 'int64'
};

/**
 * mpv 初始化参数。要点：
 * - keep-open=yes：播完停在末帧，eof-reached 才可观测（用于连播/推荐）。
 * - osc/osd/input-*：一律关掉，控制层与快捷键全部由 WebView 负责，mpv 不抢键盘不画 UI。
 * - 字幕改由 mpv 自己渲染（画面在 mpv 子窗口里，HTML 覆盖层无法与帧严格同步）：
 *   sub-auto=no 阻止自动挂载同名字幕，sid=no 默认不选轨，全部由 sub-add/sid 显式控制。
 */
const MPV_BASE_OPTIONS: Record<string, string> = {
  vo: 'gpu-next',
  hwdec: 'auto-safe',
  'keep-open': 'yes',
  'force-window': 'yes',
  osc: 'no',
  'osd-level': '0',
  'input-default-bindings': 'no',
  'input-vo-keyboard': 'no',
  'cursor-autohide': 'no',
  sid: 'no',
  'sub-auto': 'no',
  'sub-visibility': 'no',
  'audio-display': 'no',
  'msg-level': 'all=warn'
};

/** mpv 的 OSD/字幕按窗口高度相对 720 缩放；换算成"等效像素"需要除以该基准。 */
const MPV_OSD_REFERENCE_HEIGHT = 720;

export interface SubtitleStyle {
  /** 目标等效像素字号（与旧的 HTML 覆盖层视觉一致） */
  fontSize: number;
  /** 字幕垂直位置：'top' 贴顶部，'bottom' 贴底部 */
  position: 'top' | 'bottom' | string;
  /** #RRGGBB */
  color: string;
  /** 描边宽度（等效像素） */
  stroke: number;
  /** 背景不透明度 0~1 */
  bgOpacity: number;
}

/** 事件回调之外的属性兜底轮询间隔：属性观测偶有不回调（实测 vo-configured 等）。 */
const POLL_INTERVAL_MS = 400;

export interface KernelSource {
  /** mpv 直接接受本地绝对路径与 http(s) URL，无需区分。 */
  url: string;
}

export class PlayerKernel {
  readonly label: string;
  /** true = mpv 原生内核；false = <video> 回退。 */
  readonly native: boolean;

  ready = $state(false);
  paused = $state(true);
  currentTime = $state(0);
  duration = $state(0);
  buffered = $state(0);
  waiting = $state(false);
  ended = $state(false);
  errorCode = $state(0);
  errorMessage = $state('');
  videoWidth = $state(0);
  videoHeight = $state(0);

  onLoadedMetadata?: () => void;
  onEnded?: () => void;
  onError?: (code: number, message: string) => void;

  private unlisten: UnlistenFn | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private video: HTMLVideoElement | null = null;
  private metadataFired = false;
  private endedFired = false;
  /** 下一个文件/源的起播位置；<video> 后端在 loadedmetadata 时应用。 */
  private pendingStart = 0;
  private loadSeq = 0;

  constructor(label: string) {
    this.label = label;
    this.native = isTauriRuntime();
  }

  // —— 生命周期 ——

  async init(): Promise<void> {
    if (!this.native) {
      this.ready = true;
      return;
    }
    if (this.ready) return;
    await mpvInit(this.label, {
      initialOptions: MPV_BASE_OPTIONS,
      observedProperties: OBSERVED
    });
    this.unlisten = await mpvListen(this.label, (e) => this.onMpvEvent(e));
    this.ready = true;
    this.pollTimer = setInterval(() => void this.poll(), POLL_INTERVAL_MS);
  }

  async destroy(): Promise<void> {
    this.loadSeq += 1;
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    this.unlisten?.();
    this.unlisten = null;
    const el = this.video;
    if (el) {
      try {
        el.pause();
        el.removeAttribute('src');
        el.load();
      } catch {
        /* 元素已分离 */
      }
    }
    if (this.native && this.ready) {
      await mpvDestroy(this.label).catch(() => {});
    }
    this.ready = false;
  }

  /** 绑定 <video> 回退元素（mpv 模式下不需要）。 */
  attachVideo(el: HTMLVideoElement | null): void {
    if (this.video === el) return;
    if (this.video) this.detachVideo(this.video);
    this.video = el;
    if (!el) return;
    el.addEventListener('timeupdate', this.onVideoTimeUpdate);
    el.addEventListener('progress', this.onVideoProgress);
    el.addEventListener('loadedmetadata', this.onVideoLoadedMetadata);
    el.addEventListener('ended', this.onVideoEnded);
    el.addEventListener('waiting', this.onVideoWaiting);
    el.addEventListener('playing', this.onVideoPlaying);
    el.addEventListener('canplay', this.onVideoPlaying);
    el.addEventListener('play', this.onVideoPlayState);
    el.addEventListener('pause', this.onVideoPlayState);
    el.addEventListener('error', this.onVideoError);
    this.ready = true;
  }

  private detachVideo(el: HTMLVideoElement): void {
    el.removeEventListener('timeupdate', this.onVideoTimeUpdate);
    el.removeEventListener('progress', this.onVideoProgress);
    el.removeEventListener('loadedmetadata', this.onVideoLoadedMetadata);
    el.removeEventListener('ended', this.onVideoEnded);
    el.removeEventListener('waiting', this.onVideoWaiting);
    el.removeEventListener('playing', this.onVideoPlaying);
    el.removeEventListener('canplay', this.onVideoPlaying);
    el.removeEventListener('play', this.onVideoPlayState);
    el.removeEventListener('pause', this.onVideoPlayState);
    el.removeEventListener('error', this.onVideoError);
  }

  /** 设置下一次加载的起播位置（<video> 回退用；mpv 在 load 时直接消费）。 */
  setResume(position: number): void {
    this.pendingStart = Number.isFinite(position) && position > 0 ? position : 0;
  }

  // —— 加载与控制 ——

  async load(source: KernelSource): Promise<void> {
    const seq = ++this.loadSeq;
    this.metadataFired = false;
    this.endedFired = false;
    this.ended = false;
    this.errorCode = 0;
    this.errorMessage = '';
    this.waiting = false;
    this.buffered = 0;
    this.currentTime = this.pendingStart;

    if (!this.native) {
      const el = this.video;
      if (el) {
        el.src = source.url;
        el.load();
      }
      return;
    }

    try {
      // --start 不是可运行时写入的属性（set_property 会报 "error accessing property"），
      // 只能作为 loadfile 的 per-file 选项传入，否则抛异常会连带跳过 loadfile。
      const start = Math.max(0, Math.round(this.pendingStart));
      await mpvCommand(
        this.label,
        'loadfile',
        start > 0 ? [source.url, 'replace', '0', `start=${start}`] : [source.url, 'replace']
      );
    } catch (e) {
      if (seq === this.loadSeq) this.fail(2, String(e));
    }
  }

  async play(): Promise<void> {
    this.paused = false;
    if (!this.native) {
      await this.video?.play().catch(() => {});
      return;
    }
    await mpvSetProperty(this.label, 'pause', false).catch(() => {});
  }

  async pause(): Promise<void> {
    this.paused = true;
    if (!this.native) {
      this.video?.pause();
      return;
    }
    await mpvSetProperty(this.label, 'pause', true).catch(() => {});
  }

  async seek(target: number): Promise<void> {
    if (!Number.isFinite(target)) return;
    this.currentTime = target;
    if (!this.native) {
      if (this.video) this.video.currentTime = target;
      return;
    }
    await mpvCommand(this.label, 'seek', [target, 'absolute']).catch(() => {});
  }

  async stepFrame(forward: boolean): Promise<void> {
    if (!this.native) {
      const el = this.video;
      if (el) el.currentTime = el.currentTime + (forward ? 1 / 30 : -1 / 30);
      return;
    }
    await mpvCommand(this.label, forward ? 'frame-step' : 'frame-back-step').catch(() => {});
  }

  async setVolume(value: number): Promise<void> {
    const v = Math.max(0, Math.min(1, value));
    if (!this.native) {
      if (this.video) this.video.volume = v;
      return;
    }
    await mpvSetProperty(this.label, 'volume', v * 100).catch(() => {});
  }

  async setMuted(muted: boolean): Promise<void> {
    if (!this.native) {
      if (this.video) this.video.muted = muted;
      return;
    }
    await mpvSetProperty(this.label, 'mute', muted).catch(() => {});
  }

  async setSpeed(rate: number): Promise<void> {
    if (!this.native) {
      if (this.video) this.video.playbackRate = rate;
      return;
    }
    await mpvSetProperty(this.label, 'speed', rate).catch(() => {});
  }

  /** 把 mpv 画面限制在给定比例的内缩区域内（对齐播放页舞台）。 */
  async setMarginRatio(ratio: VideoMarginRatio): Promise<void> {
    if (!this.native || !this.ready) return;
    await mpvSetVideoMarginRatio(this.label, ratio).catch(() => {});
  }

  /** 抓取当前帧为 PNG。mpv 走原生 screenshot-to-file（Rust 侧读回字节）。 */
  async captureFrame(): Promise<Blob | null> {
    if (!this.native) {
      const el = this.video;
      if (!el || !el.videoWidth || !el.videoHeight) return null;
      const canvas = document.createElement('canvas');
      canvas.width = el.videoWidth;
      canvas.height = el.videoHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;
      try {
        ctx.drawImage(el, 0, 0, canvas.width, canvas.height);
      } catch {
        return null;
      }
      return new Promise((resolve) => {
        try {
          canvas.toBlob((b) => resolve(b), 'image/png');
        } catch {
          resolve(null);
        }
      });
    }
    try {
      const bytes = await invoke<ArrayBuffer>('mpv_screenshot', {
        windowLabel: this.label,
        mode: 'video'
      });
      return new Blob([bytes], { type: 'image/png' });
    } catch {
      return null;
    }
  }

  // —— 字幕（mpv 原生渲染）——
  //
  // 画面由 mpv 子窗口渲染，WebView 里的 HTML 覆盖层拿不到与帧对齐的时间基准，
  // 因此字幕交回 mpv 自己画。字幕源统一由调用方取成文本后落临时文件再 sub-add，
  // 这样外挂 / 内封 / 网络三种来源走同一条路，不必区分格式与路径合法性。

  /** 挂载并选中一条字幕；传 null 表示移除全部字幕轨。 */
  async setSubtitleFile(path: string | null): Promise<void> {
    if (!this.native || !this.ready) return;
    await mpvCommand(this.label, 'sub-remove').catch(() => {});
    if (!path) return;
    await mpvCommand(this.label, 'sub-add', [path, 'select']).catch(() => {});
  }

  /** 显隐当前字幕轨（保留已挂载的轨，便于快速开关）。 */
  async setSubVisible(visible: boolean): Promise<void> {
    if (!this.native || !this.ready) return;
    await mpvSetProperty(this.label, 'sub-visibility', visible).catch(() => {});
  }

  /**
   * 应用全局字幕样式。字号/描边按窗口高度换算回 mpv 的 720 基准缩放单位，
   * 以贴近旧 HTML 覆盖层的等效像素观感。
   */
  async applySubtitleStyle(style: SubtitleStyle): Promise<void> {
    if (!this.native || !this.ready) return;
    const h = typeof window !== 'undefined' && window.innerHeight > 0 ? window.innerHeight : 720;
    const scale = MPV_OSD_REFERENCE_HEIGHT / h;
    const size = Math.max(8, Math.round(style.fontSize * scale));
    const border = Math.max(0, Number((style.stroke * scale).toFixed(2)));
    // mpv：0 = 顶部，100 = 底部
    const pos = style.position === 'top' ? 8 : 82;
    const bgAlpha = Math.max(0, Math.min(255, Math.round(style.bgOpacity * 255)));
    await Promise.all([
      mpvSetProperty(this.label, 'sub-font-size', size),
      mpvSetProperty(this.label, 'sub-border-size', border),
      mpvSetProperty(this.label, 'sub-pos', pos),
      mpvSetProperty(this.label, 'sub-color', style.color),
      mpvSetProperty(this.label, 'sub-border-color', '#000000'),
      mpvSetProperty(this.label, 'sub-bg-color', '#000000'),
      mpvSetProperty(this.label, 'sub-bg-alpha', bgAlpha)
    ]).catch(() => {});
  }

  /** 选择音轨（'auto' 交给 mpv 自动挑选，'no' 关闭声音）。 */
  async setAudioTrack(id: number | 'auto' | 'no'): Promise<void> {
    if (!this.native || !this.ready) return;
    await mpvSetProperty(this.label, 'aid', id).catch(() => {});
  }

  /** 切换硬解模式（对应设置页的"硬件视频解码"开关）。 */
  async setHwdec(enabled: boolean): Promise<void> {
    if (!this.native || !this.ready) return;
    await mpvSetProperty(this.label, 'hwdec', enabled ? 'auto-safe' : 'no').catch(() => {});
  }

  /** 读任意 mpv 属性（媒体信息面板/诊断用）。 */
  async getProperty<T = unknown>(name: string, format: MpvFormat = 'string'): Promise<T | null> {
    if (!this.native || !this.ready) return null;
    return mpvGetProperty<T>(this.label, name, format);
  }

  // —— mpv 属性同步 ——

  private onMpvEvent(event: MpvEvent): void {
    const name = event?.name;
    if (typeof name !== 'string') return;
    this.applyProperty(name, event.data);
  }

  private applyProperty(name: string, data: unknown): void {
    switch (name) {
      case 'pause':
        this.paused = data === true;
        break;
      case 'time-pos':
        if (typeof data === 'number' && Number.isFinite(data)) this.currentTime = data;
        break;
      case 'duration':
        if (typeof data === 'number' && Number.isFinite(data) && data > 0) {
          this.duration = data;
          this.maybeMetadata();
        }
        break;
      case 'eof-reached':
        this.handleEof(data === true);
        break;
      case 'paused-for-cache':
        this.waiting = data === true;
        break;
      case 'demuxer-cache-time':
        if (typeof data === 'number' && Number.isFinite(data)) this.buffered = data;
        break;
      case 'width':
        if (typeof data === 'number') this.videoWidth = data;
        break;
      case 'height':
        if (typeof data === 'number') this.videoHeight = data;
        break;
      default:
        break;
    }
  }

  /** 观测事件对部分属性不回调，用一次轮询补齐关键状态。 */
  private async poll(): Promise<void> {
    if (!this.native) return;
    const [pos, pause, dur, eof, cache] = await Promise.all([
      mpvGetProperty<number>(this.label, 'time-pos', 'double'),
      mpvGetProperty<boolean>(this.label, 'pause', 'flag'),
      mpvGetProperty<number>(this.label, 'duration', 'double'),
      mpvGetProperty<boolean>(this.label, 'eof-reached', 'flag'),
      mpvGetProperty<boolean>(this.label, 'paused-for-cache', 'flag')
    ]);
    if (typeof pos === 'number' && Number.isFinite(pos)) this.currentTime = pos;
    if (typeof pause === 'boolean') this.paused = pause;
    if (typeof dur === 'number' && Number.isFinite(dur) && dur > 0) {
      this.duration = dur;
      this.maybeMetadata();
    }
    if (typeof eof === 'boolean') this.handleEof(eof);
    if (typeof cache === 'boolean') this.waiting = cache;
  }

  private maybeMetadata(): void {
    if (this.metadataFired || this.duration <= 0) return;
    this.metadataFired = true;
    this.onLoadedMetadata?.();
  }

  private handleEof(reached: boolean): void {
    if (!reached) {
      this.endedFired = false;
      this.ended = false;
      return;
    }
    if (this.endedFired) return;
    this.endedFired = true;
    this.ended = true;
    this.paused = true;
    this.onEnded?.();
  }

  private fail(code: number, message: string): void {
    this.errorCode = code;
    this.errorMessage = message;
    this.onError?.(code, message);
  }

  // —— <video> 回退事件 ——

  private onVideoTimeUpdate = (): void => {
    const el = this.video;
    if (!el) return;
    const t = el.currentTime;
    if (Number.isFinite(t)) this.currentTime = t;
  };

  private onVideoProgress = (): void => {
    const el = this.video;
    if (!el) return;
    try {
      if (el.buffered.length) this.buffered = el.buffered.end(el.buffered.length - 1);
    } catch {
      /* ignore */
    }
  };

  private onVideoLoadedMetadata = (): void => {
    const el = this.video;
    if (!el) return;
    if (Number.isFinite(el.duration) && el.duration > 0) this.duration = el.duration;
    if (this.pendingStart > 0 && el.duration > 0 && this.pendingStart < el.duration * 0.95) {
      el.currentTime = this.pendingStart;
      this.currentTime = this.pendingStart;
    }
    this.pendingStart = 0;
    this.maybeMetadata();
  };

  private onVideoEnded = (): void => {
    this.handleEof(true);
  };

  private onVideoWaiting = (): void => {
    this.waiting = true;
  };

  private onVideoPlaying = (): void => {
    this.waiting = false;
  };

  private onVideoPlayState = (): void => {
    const el = this.video;
    if (el) this.paused = el.paused;
  };

  private onVideoError = (): void => {
    const el = this.video;
    const err = el?.error;
    if (!err) return;
    this.fail(err.code, err.message);
  };
}