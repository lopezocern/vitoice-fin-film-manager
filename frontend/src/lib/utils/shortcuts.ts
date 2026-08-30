export type ShortcutCategory = 'playback' | 'navigation' | 'tagging' | 'general';

export interface ShortcutDef {
  key: string;
  description: string;
  category: ShortcutCategory;
  shift?: boolean;
  ctrl?: boolean;
  alt?: boolean;
  cmd?: string;
}

export const SHORTCUTS: ShortcutDef[] = [
  // 播放控制
  { key: ' ', description: '播放 / 暂停', category: 'playback', cmd: 'play_pause' },
  { key: 'j', description: '后退 10 秒', category: 'playback', cmd: 'seek_back_10' },
  { key: 'l', description: '前进 10 秒', category: 'playback', cmd: 'seek_forward_10' },
  { key: 'ArrowLeft', description: '步进后退', category: 'playback', cmd: 'step_back' },
  { key: 'ArrowRight', description: '步进前进', category: 'playback', cmd: 'step_forward' },
  { key: ',', description: '后退单帧', category: 'playback', cmd: 'frame_back' },
  { key: '.', description: '前进单帧', category: 'playback', cmd: 'frame_forward' },
  { key: 'f', description: '全屏切换', category: 'playback', cmd: 'fullscreen' },

  // 标记与打标
  { key: 'i', description: '标记片段起点', category: 'tagging', cmd: 'mark_in' },
  { key: 'o', description: '标记片段终点', category: 'tagging', cmd: 'mark_out' },
  { key: 't', description: '打开标签面板', category: 'tagging', cmd: 'tag_panel' },
  { key: 'a', description: 'AI 自动打标', category: 'tagging', cmd: 'ai_tag' },
  { key: 's', description: '截图当前帧', category: 'tagging', cmd: 'screenshot' },
  { key: 'c', description: '字幕切换', category: 'playback', cmd: 'captions' },

  // 评分与收藏
  { key: '1', description: '评分 1 星', category: 'navigation', cmd: 'rate_1' },
  { key: '2', description: '评分 2 星', category: 'navigation', cmd: 'rate_2' },
  { key: '3', description: '评分 3 星', category: 'navigation', cmd: 'rate_3' },
  { key: '4', description: '评分 4 星', category: 'navigation', cmd: 'rate_4' },
  { key: '5', description: '评分 5 星', category: 'navigation', cmd: 'rate_5' },
  { key: 'r', description: '收藏 / 取消收藏', category: 'navigation', cmd: 'favorite' }
];

export const SHORTCUT_MAP: Record<string, ShortcutDef> = SHORTCUTS.reduce(
  (acc, s) => {
    if (s.cmd) acc[s.cmd] = s;
    return acc;
  },
  {} as Record<string, ShortcutDef>
);

export function matchShortcut(event: KeyboardEvent, def: ShortcutDef): boolean {
  const key = event.key.toLowerCase();
  const targetKey = def.key.toLowerCase();
  const isSpace = key === ' ' || key === 'spacebar';
  const targetIsSpace = targetKey === ' ';
  return (
    (key === targetKey || (isSpace && targetIsSpace)) &&
    !!event.shiftKey === !!def.shift &&
    !!event.ctrlKey === !!def.ctrl &&
    !!event.altKey === !!def.alt
  );
}

export function findShortcutByEvent(event: KeyboardEvent): ShortcutDef | undefined {
  return SHORTCUTS.find((s) => matchShortcut(event, s));
}

export function shortcutLabel(def: ShortcutDef): string {
  const parts: string[] = [];
  if (def.ctrl) parts.push('Ctrl');
  if (def.shift) parts.push('Shift');
  if (def.alt) parts.push('Alt');
  if (def.key === ' ') {
    parts.push('Space');
  } else if (def.key === 'ArrowLeft') {
    parts.push('←');
  } else if (def.key === 'ArrowRight') {
    parts.push('→');
  } else {
    parts.push(def.key.toUpperCase());
  }
  return parts.join(' + ');
}
