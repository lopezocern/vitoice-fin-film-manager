// 详情页子组件共享类型
// Segment / Subtitle 从 media.metadata 中读取，结构与播放器页面的本地类型保持一致

export interface Segment {
  id: string;
  start: number;
  end?: number;
  label?: string;
}

export interface Subtitle {
  id: string;
  language: string;
  type: 'external' | 'embedded' | 'network';
  default?: boolean;
  url?: string;
}
