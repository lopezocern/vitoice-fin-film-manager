<script lang="ts">
  // 字幕轨道组件：解析 SRT / VTT / ASS，按当前时间显示对应字幕。
  // 字幕内容通过 file_path（URL）或 /media/{id}/subtitles/{sid}/content 端点尽力获取；
  // 后端尚未提供 content 端点时静默隐藏（无字幕状态）。
  import { untrack } from 'svelte';
  import { BASE_URL } from '$lib/api/client';
  import { settingsStore } from '$lib/stores/settings.svelte';

  interface SubtitleInfo {
    id: number;
    language: string;
    title?: string | null;
    file_path?: string | null;
    file_format?: string | null;
  }

  interface Cue {
    start: number;
    end: number;
    text: string;
  }

  let {
    subtitle = null,
    mediaId = '',
    currentTime = 0,
    enabled = true,
  }: {
    subtitle?: SubtitleInfo | null;
    mediaId?: string;
    currentTime?: number;
    enabled?: boolean;
  } = $props();

  let cues = $state<Cue[]>([]);
  let failed = $state(false);

  // Derive subtitle styling from the global settings store.
  // Position: 'bottom' → 82%, 'top' → 8%.
  const fontSize = $derived(settingsStore.subtitleFontSize);
  const position = $derived(settingsStore.subtitlePosition === 'top' ? 8 : 82);
  const textColor = $derived(settingsStore.subtitleColor);
  const strokeWidth = $derived(settingsStore.subtitleStroke);
  const bgOpacity = $derived(settingsStore.subtitleBgOpacity);

  const currentText = $derived.by(() => {
    if (!cues.length) return null;
    // 从后往前找第一个包含当前时间的条目（更稳）
    for (let i = cues.length - 1; i >= 0; i--) {
      const c = cues[i];
      if (currentTime >= c.start && currentTime <= c.end) return c.text;
    }
    return null;
  });

  function parseTimecodeToSeconds(tc: string): number {
    // 支持 HH:MM:SS,mmm / HH:MM:SS.mmm / MM:SS.mmm
    const t = tc.trim().replace(',', '.');
    const parts = t.split(':');
    let h = 0, m = 0, s = 0;
    if (parts.length === 3) {
      h = Number(parts[0]) || 0;
      m = Number(parts[1]) || 0;
      s = Number(parts[2]) || 0;
    } else if (parts.length === 2) {
      m = Number(parts[0]) || 0;
      s = Number(parts[1]) || 0;
    } else {
      s = Number(parts[0]) || 0;
    }
    return h * 3600 + m * 60 + s;
  }

  function stripTags(text: string): string {
    return text
      .replace(/\{[^}]*\}/g, '') // ASS override 块 {...}
      .replace(/<[^>]+>/g, '') // HTML / VTT 内联标签
      .replace(/\\N/g, '\n') // ASS 硬换行
      .replace(/\\n/g, ' ') // ASS 软换行
      .replace(/\\h/g, ' ') // ASS 硬空格
      .trim();
  }

  function parseSrt(content: string): Cue[] {
    const out: Cue[] = [];
    const blocks = content.replace(/\r\n/g, '\n').split(/\n\n+/);
    for (const block of blocks) {
      const lines = block.split('\n').filter((l) => l.trim().length > 0);
      if (!lines.length) continue;
      let idx = 0;
      // 跳过块序号行（纯数字）
      if (/^\d+$/.test(lines[0].trim())) idx = 1;
      const tcLine = lines[idx];
      if (!tcLine || !tcLine.includes('-->')) continue;
      const [a, b] = tcLine.split('-->');
      const start = parseTimecodeToSeconds(a);
      const end = parseTimecodeToSeconds(b);
      const text = lines.slice(idx + 1).join('\n');
      const clean = stripTags(text);
      if (clean) out.push({ start, end, text: clean });
    }
    return out;
  }

  function parseVtt(content: string): Cue[] {
    // WEBVTT 与 SRT 结构兼容，去掉头后复用解析器
    const body = content.replace(/^WEBVTT[^\n]*\n/i, '').replace(/\r\n/g, '\n');
    return parseSrt(body);
  }

  function parseAss(content: string): Cue[] {
    const out: Cue[] = [];
    const lines = content.replace(/\r\n/g, '\n').split('\n');
    let inEvents = false;
    let fmt: string[] = [];
    for (const raw of lines) {
      const l = raw.trim();
      if (l.startsWith('[')) {
        inEvents = l.toLowerCase().startsWith('[events');
        continue;
      }
      if (!inEvents) continue;
      if (l.toLowerCase().startsWith('format:')) {
        fmt = l.slice(7).split(',').map((s) => s.trim().toLowerCase());
        continue;
      }
      if (l.toLowerCase().startsWith('dialogue:')) {
        const rest = l.slice(9);
        const cols = rest.split(',');
        if (!fmt.length) continue;
        const startIdx = fmt.indexOf('start');
        const endIdx = fmt.indexOf('end');
        const textIdx = fmt.indexOf('text');
        if (startIdx < 0 || endIdx < 0 || textIdx < 0) continue;
        const start = parseTimecodeToSeconds(cols[startIdx] ?? '0');
        const end = parseTimecodeToSeconds(cols[endIdx] ?? '0');
        // text 列之后可能含逗号，重新拼接
        const text = cols.slice(textIdx).join(',');
        const clean = stripTags(text);
        if (clean && end > start) out.push({ start, end, text: clean });
      }
    }
    return out;
  }

  function detectAndParse(content: string, fmt?: string | null): Cue[] {
    const lower = (fmt ?? '').toLowerCase();
    const sample = content.slice(0, 200).toUpperCase();
    if (lower === 'ass' || lower === 'ssa' || sample.includes('[SCRIPT INFO]')) {
      return parseAss(content);
    }
    if (lower === 'vtt' || sample.startsWith('WEBVTT')) {
      return parseVtt(content);
    }
    return parseSrt(content);
  }

  // F7 fix: a request sequence guard — fast subtitle-track switching must
  // not let a slow older response overwrite the current track.
  let subReqSeq = 0;
  async function loadSubtitle(sub: SubtitleInfo): Promise<void> {
    const mySeq = ++subReqSeq;
    cues = [];
    failed = false;
    let text: string | null = null;
    try {
      if (sub.file_path && /^https?:\/\//i.test(sub.file_path)) {
        const r = await fetch(sub.file_path);
        if (r.ok) text = await r.text();
      } else {
        // 后端 content 端点（如未实现会 404，静默处理）
        const r = await fetch(`${BASE_URL}/media/${mediaId}/subtitles/${sub.id}/content`);
        if (r.ok) {
          const data = await r.json();
          // Backend returns {content, format, language, source} — extract text (H8 fix)
          text = typeof data === 'object' && data !== null ? (data.content as string) || null : null;
        }
      }
    } catch {
      text = null;
    }
    if (mySeq !== subReqSeq) return; // stale response — drop it
    if (!text) {
      failed = true;
      return;
    }
    cues = detectAndParse(text, sub.file_format);
  }

  // 字幕或启用状态变化时重新加载
  $effect(() => {
    const sub = subtitle;
    const en = enabled;
    if (sub && en) {
      // untrack：loadSubtitle 的同步部分写 cues/failed（$state），防御性隔离
      untrack(() => void loadSubtitle(sub));
    } else {
      cues = [];
    }
  });
</script>

{#if enabled && currentText}
  <div
    class="subtitle-track"
    style={`--sub-font:${fontSize}px; --sub-pos:${position}%; --sub-color:${textColor}; --sub-stroke:${strokeWidth}px; --sub-bg:${bgOpacity};`}
  >
    <p>{currentText}</p>
  </div>
{/if}

<style>
  .subtitle-track {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    bottom: var(--sub-pos);
    max-width: 86%;
    text-align: center;
    pointer-events: none;
    z-index: 5;
    background: rgba(0, 0, 0, var(--sub-bg));
    border-radius: 4px;
    padding: 0.15em 0.4em;
  }
  .subtitle-track p {
    margin: 0;
    font-size: var(--sub-font);
    line-height: 1.35;
    color: var(--sub-color);
    text-shadow:
      calc(var(--sub-stroke) * -1px) calc(var(--sub-stroke) * -1px) 0 #000,
      var(--sub-stroke) calc(var(--sub-stroke) * -1px) 0 #000,
      calc(var(--sub-stroke) * -1px) var(--sub-stroke) 0 #000,
      var(--sub-stroke) var(--sub-stroke) 0 #000,
      0 0 4px rgba(0, 0, 0, 0.9),
      0 2px 6px rgba(0, 0, 0, 0.8);
    font-weight: 600;
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
