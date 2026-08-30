// Shared utilities, constants, and types used by Sidebar sub-components
// (MediaSidebar, ManageSidebar, TagOverlays).

export type { TagType } from '$lib/stores/libraries.svelte';

/** 安全校验颜色值：仅允许 #RRGGBB 格式，避免任意字符串注入到 style */
export const safeColor = (c: string | null | undefined): string =>
  /^#[0-9a-fA-F]{6}$/.test(c ?? '') ? (c as string) : '';

/** 标签类型显示名映射（AV 类型使用中文名，更直观） */
export const typeNameDisplay: Record<string, string> = {
  'actor': '演员',
  'genre': '类型',
  'theme': '主题',
  'custom': '自定义',
  'collection': '合集',
  'studio': '工作室',
  'av_actress': '女优',
  'av_genre': '限制内容类型',
  'av_studio': '厂商',
  'av_series': '系列',
  'av_director': '导演',
};

export const displayTypeName = (name: string): string => typeNameDisplay[name] ?? name;

/** 标签颜色调色板（含 null = 清除颜色，使用类型默认色） */
export const TAG_PALETTE = [
  '#635bff', '#f59e0b', '#34c759', '#ff3b30', '#ff2d55',
  '#af52de', '#5ac8fa', '#ff9500', '#8e8e93', '#00c7be',
  null,
];

/** 标签类型颜色调色板 */
export const TYPE_PALETTE = [
  '#635bff', '#f59e0b', '#34c759', '#ff3b30', '#ff2d55',
  '#af52de', '#5ac8fa', '#ff9500', '#8e8e93', '#00c7be',
];
