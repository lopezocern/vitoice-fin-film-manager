/**
 * tauri-plugin-libmpv 的薄封装：只做 IPC 调用与事件订阅，不含任何播放语义。
 * 播放语义（状态机、属性同步、双后端切换）见 kernel.svelte.ts。
 */
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

/** 与 wrapper 的 mpv_observe_property 格式串一致。 */
export type MpvFormat = 'flag' | 'double' | 'int64' | 'string' | 'node';

export interface MpvInitConfig {
  initialOptions?: Record<string, string | number | boolean>;
  observedProperties?: Record<string, MpvFormat>;
}

export interface MpvEvent {
  name?: string;
  data?: unknown;
  event?: string;
}

export interface VideoMarginRatio {
  left?: number;
  right?: number;
  top?: number;
  bottom?: number;
}

export function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/** 读当前 Tauri 窗口 label（mpv 实例按窗口 label 绑定）；浏览器环境回退 'main'。 */
export function resolveWindowLabel(): string {
  try {
    const internals = (
      window as unknown as {
        __TAURI_INTERNALS__?: { metadata?: { currentWindow?: { label?: string } } };
      }
    ).__TAURI_INTERNALS__;
    return internals?.metadata?.currentWindow?.label ?? 'main';
  } catch {
    return 'main';
  }
}

export async function mpvInit(windowLabel: string, config: MpvInitConfig): Promise<void> {
  await invoke('plugin:libmpv|init', {
    mpvConfig: {
      initialOptions: config.initialOptions ?? {},
      observedProperties: config.observedProperties ?? {}
    },
    windowLabel
  });
}

export async function mpvDestroy(windowLabel: string): Promise<void> {
  await invoke('plugin:libmpv|destroy', { windowLabel });
}

export async function mpvCommand(
  windowLabel: string,
  name: string,
  args: unknown[] = []
): Promise<void> {
  await invoke('plugin:libmpv|command', { name, args, windowLabel });
}

export async function mpvSetProperty(
  windowLabel: string,
  name: string,
  value: unknown
): Promise<void> {
  await invoke('plugin:libmpv|set_property', { name, value, windowLabel });
}

/** 属性不可用时插件会报错（如 idle 状态下的 time-pos），统一吞掉返回 null。 */
export async function mpvGetProperty<T = unknown>(
  windowLabel: string,
  name: string,
  format: MpvFormat
): Promise<T | null> {
  try {
    const value = await invoke<T>('plugin:libmpv|get_property', { name, format, windowLabel });
    return value ?? null;
  } catch {
    return null;
  }
}

export async function mpvSetVideoMarginRatio(
  windowLabel: string,
  ratio: VideoMarginRatio
): Promise<void> {
  await invoke('plugin:libmpv|set_video_margin_ratio', { ratio, windowLabel });
}

export async function mpvListen(
  windowLabel: string,
  handler: (event: MpvEvent) => void
): Promise<UnlistenFn> {
  return listen<MpvEvent>(`mpv-event-${windowLabel}`, (e) => handler(e.payload));
}

/** 把字幕文本落成临时文件并返回路径（mpv 的 sub-add 只接受路径/URL）。 */
export async function mpvWriteSubtitle(text: string, ext?: string): Promise<string> {
  return invoke<string>('mpv_write_subtitle', { text, ext });
}