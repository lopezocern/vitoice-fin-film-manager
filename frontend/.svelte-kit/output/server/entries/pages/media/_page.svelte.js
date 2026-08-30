import { a as attr_class, c as attr, e as escape_html, d as derived, h as attr_style, f as ensure_array_like, i as stringify, s as store_get, k as head, u as unsubscribe_stores } from "../../../chunks/index.js";
import { g as goto } from "../../../chunks/client.js";
import { l as librariesStore, p as page } from "../../../chunks/libraries.svelte.js";
import { B as BASE_URL, c as client } from "../../../chunks/client2.js";
import { n as navigation } from "../../../chunks/navigation.svelte.js";
import "clsx";
import { i as isAvMedia, m as mediaApi, h as hasNetworkSource } from "../../../chunks/media.js";
import { f as formatTime, c as formatResolution, b as formatSize } from "../../../chunks/format.js";
import { s as settingsStore } from "../../../chunks/settings.svelte.js";
const seriesApi = {
  /** List all series, optionally filtered by library. Paginated. */
  list: async (libraryId, page2 = 1, pageSize = 60) => {
    const params = { page: page2, page_size: pageSize };
    if (libraryId) params.library_id = libraryId;
    return client.get("/series", params);
  },
  /** Get series detail with episodes grouped by season. */
  get: async (id) => client.get(`/series/${id}`),
  /** Get previous/next episode navigation for a media within its series. */
  getEpisodeNav: async (mediaId) => client.get(`/series/episodes/${mediaId}/nav`),
  /** Build the poster URL for a series. */
  posterUrl: (id) => `${BASE_URL}/series/${id}/poster`
};
const mediaScroll = {
  top: 0,
  page: 0,
  anchorId: "",
  anchorOffset: 0,
  savedItems: null,
  savedSeries: null
};
function FilterBar($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { filter, filterOptions } = $$props;
    let openMenu = null;
    const typeOptions = [
      { value: "", label: "全部媒体" },
      { value: "video", label: "视频" },
      { value: "audio", label: "音频" },
      { value: "image", label: "图片" }
    ];
    const resolutionOptions = [
      { value: "", label: "全部分辨率" },
      { value: "4k", label: "4K 及以上" },
      { value: "1080p", label: "1080p" },
      { value: "720p", label: "720p" },
      { value: "480p", label: "480p" },
      { value: "other", label: "其他" }
    ];
    const ratingOptions = [
      { value: "", label: "全部评分" },
      { value: "1", label: "★ 1 星及以上" },
      { value: "2", label: "★ 2 星及以上" },
      { value: "3", label: "★ 3 星及以上" },
      { value: "4", label: "★ 4 星及以上" },
      { value: "5", label: "★ 5 星" }
    ];
    const durationOptions = [
      { value: "", label: "全部时长" },
      { value: "short", label: "< 10 分钟" },
      { value: "medium", label: "10 - 60 分钟" },
      { value: "long", label: "> 60 分钟" }
    ];
    const genreOptions = derived(() => [
      { value: "", label: "全部题材" },
      ...(filterOptions?.genres ?? []).map((g) => ({ value: g, label: g }))
    ]);
    const countryOptions = derived(() => [
      { value: "", label: "全部地区" },
      ...(filterOptions?.countries ?? []).map((c) => ({ value: c, label: c }))
    ]);
    const yearOptions = derived(() => [
      { value: "", label: "全部年份" },
      { value: "0", label: "未知年份" },
      ...(filterOptions?.years ?? []).map((y) => ({ value: String(y), label: String(y) }))
    ]);
    const typeLabel = derived(() => typeOptions.find((o) => o.value === (filter.type ?? ""))?.label ?? "媒体");
    const genreLabel = derived(() => genreOptions().find((o) => o.value === (filter.genre ?? ""))?.label ?? "题材");
    const countryLabel = derived(() => countryOptions().find((o) => o.value === (filter.country ?? ""))?.label ?? "地区");
    const yearLabel = derived(() => yearOptions().find((o) => o.value === String(filter.year ?? ""))?.label ?? "年份");
    const resLabel = derived(() => resolutionOptions.find((o) => o.value === (filter.resolution ?? ""))?.label ?? "分辨率");
    const ratingLabel = derived(() => ratingOptions.find((o) => o.value === String(filter.ratingMin ?? ""))?.label ?? "评分");
    const durationLabel = derived(() => durationOptions.find((o) => o.value === (filter.duration ?? ""))?.label ?? "时长");
    const activeCount = derived(() => (filter.type ? 1 : 0) + (filter.genre ? 1 : 0) + (filter.country ? 1 : 0) + (filter.year !== void 0 ? 1 : 0) + (filter.resolution ? 1 : 0) + (filter.ratingMin ? 1 : 0) + (filter.duration ? 1 : 0));
    $$renderer2.push(`<div class="filter-bar svelte-akuiaw"><div class="chips svelte-akuiaw"><div class="chip-wrap svelte-akuiaw" data-menu="type"><button${attr_class("chip svelte-akuiaw", void 0, { "active": !!filter.type })} aria-haspopup="listbox"${attr("aria-expanded", openMenu === "type")}><span>${escape_html(typeLabel())}</span><span class="caret svelte-akuiaw">▾</span></button> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="chip-wrap svelte-akuiaw" data-menu="genre"><button${attr_class("chip svelte-akuiaw", void 0, { "active": !!filter.genre })} aria-haspopup="listbox"${attr("aria-expanded", openMenu === "genre")}><span>${escape_html(genreLabel())}</span><span class="caret svelte-akuiaw">▾</span></button> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="chip-wrap svelte-akuiaw" data-menu="country"><button${attr_class("chip svelte-akuiaw", void 0, { "active": !!filter.country })} aria-haspopup="listbox"${attr("aria-expanded", openMenu === "country")}><span>${escape_html(countryLabel())}</span><span class="caret svelte-akuiaw">▾</span></button> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="chip-wrap svelte-akuiaw" data-menu="year"><button${attr_class("chip svelte-akuiaw", void 0, { "active": !!filter.year })} aria-haspopup="listbox"${attr("aria-expanded", openMenu === "year")}><span>${escape_html(yearLabel())}</span><span class="caret svelte-akuiaw">▾</span></button> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="chip-wrap svelte-akuiaw" data-menu="resolution"><button${attr_class("chip svelte-akuiaw", void 0, { "active": !!filter.resolution })} aria-haspopup="listbox"${attr("aria-expanded", openMenu === "resolution")}><span>${escape_html(resLabel())}</span><span class="caret svelte-akuiaw">▾</span></button> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="chip-wrap svelte-akuiaw" data-menu="rating"><button${attr_class("chip svelte-akuiaw", void 0, { "active": !!filter.ratingMin })} aria-haspopup="listbox"${attr("aria-expanded", openMenu === "rating")}><span>${escape_html(ratingLabel())}</span><span class="caret svelte-akuiaw">▾</span></button> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="chip-wrap svelte-akuiaw" data-menu="duration"><button${attr_class("chip svelte-akuiaw", void 0, { "active": !!filter.duration })} aria-haspopup="listbox"${attr("aria-expanded", openMenu === "duration")}><span>${escape_html(durationLabel())}</span><span class="caret svelte-akuiaw">▾</span></button> `);
    {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div> `);
    if (activeCount() > 0) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<button class="clear svelte-akuiaw">清除筛选 (${escape_html(activeCount())})</button>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div></div>`);
  });
}
function getProgress(meta) {
  if (!meta) return 0;
  const pos = meta.playback_position ?? meta.progress ?? meta.playback_progress ?? meta.position;
  if (typeof pos !== "number" || !Number.isFinite(pos) || pos <= 0) return 0;
  const dur = typeof meta.duration === "number" ? meta.duration : 0;
  if (Number.isFinite(dur) && dur > 0) {
    return Math.max(0, Math.min(100, pos / dur * 100));
  }
  return Math.max(0, Math.min(100, pos));
}
function PosterWall($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let {
      items,
      onSelect,
      onplay,
      mode = "mixed",
      density = 180
      /** 点击封面图直接播放（进播放器） */
    } = $$props;
    const restrictedLibIds = derived(() => new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id))));
    function shouldMask(media) {
      return settingsStore.maskRestricted && restrictedLibIds().has(String(media.library_id));
    }
    const posterRatio = {};
    $$renderer2.push(`<div${attr_class("poster-wall svelte-1ywh4zk", void 0, {
      "poster-mode": (
        // 桌面应用（Windows/macOS）：一次性渲染全部 items。
        // 之前 200/步的增量渲染会导致：①返回时锚点卡片可能未渲染，滚动位置恢复偏；
        // ②时间轴等分组里 >200 条的组只显示前 200 条（"年份缺媒体"）。
        // 桌面端 DOM 承受能力足够，直接全量渲染最可靠。
        mode === "poster"
      )
    })}${attr_style(`--media-card-width:${density}px`)}><!--[-->`);
    const each_array = ensure_array_like(items);
    for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
      let media = each_array[$$index];
      const p = getProgress(media.metadata);
      const filled = Math.max(0, Math.min(5, media.rating));
      const av = isAvMedia(media);
      const usesSeriesCover = media.series_id != null;
      const hasImage = usesSeriesCover || !!media.poster || !!media.thumbnail;
      const ratioCls = hasImage ? posterRatio[String(media.id)] : void 0;
      const defaultRatio = usesSeriesCover || media.poster ? av && !usesSeriesCover ? "4 / 3" : "2 / 3" : "4 / 3";
      const ratioStr = mode === "poster" ? "2 / 3" : ratioCls ?? defaultRatio;
      const isWide = !usesSeriesCover && mode === "mixed" && (ratioCls === "4 / 3" || !ratioCls && !media.poster && !!media.thumbnail);
      $$renderer2.push(`<button${attr_class("poster svelte-1ywh4zk", void 0, { "av-poster": !hasImage && av, "wide": isWide })}${attr("data-id", media.id)}><div${attr_class("poster-thumb svelte-1ywh4zk", void 0, {
        "av-poster": av,
        "has-poster": !!media.poster,
        "playable": onplay && media.type !== "image"
      })}${attr("title", media.type !== "image" ? "点击封面播放" : "查看详情")}${attr_style("", { "aspect-ratio": hasImage ? ratioStr : void 0 })}>`);
      if (usesSeriesCover) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<img${attr("src", seriesApi.posterUrl(media.series_id))}${attr("alt", media.series_title ?? media.title ?? media.filename)} loading="lazy" class="svelte-1ywh4zk" onerror="this.__e=event" onload="this.__e=event"/>`);
      } else if (media.poster) {
        $$renderer2.push("<!--[1-->");
        $$renderer2.push(`<img${attr("src", mediaApi.posterUrl(media.id, media.updated_at))}${attr("alt", media.title ?? media.filename)} loading="lazy" class="svelte-1ywh4zk" onerror="this.__e=event" onload="this.__e=event"/>`);
      } else if (media.thumbnail) {
        $$renderer2.push("<!--[2-->");
        $$renderer2.push(`<img${attr("src", mediaApi.thumbnailUrl(media.id, media.updated_at))}${attr("alt", media.filename)} loading="lazy" class="svelte-1ywh4zk" onerror="this.__e=event" onload="this.__e=event"/>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<div class="thumb-fallback svelte-1ywh4zk"><span>${escape_html(media.type === "video" ? "▶" : media.type === "audio" ? "♪" : "▣")}</span></div>`);
      }
      $$renderer2.push(`<!--]--> `);
      if (media.duration) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="duration svelte-1ywh4zk">${escape_html(formatTime(media.duration))}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (!media.file_missing && (media.source_type === "network" || media.source_type === "both")) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="net-badge svelte-1ywh4zk"${attr("title", media.source_type === "both" ? "本地 + 网络源" : "网络媒体")}>${escape_html(media.source_type === "both" ? "本+网" : "网")}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (media.favorite) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="fav svelte-1ywh4zk">♥</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (media.file_missing) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span${attr_class("missing-badge svelte-1ywh4zk", void 0, { "has-network": hasNetworkSource(media) })}${attr("title", hasNetworkSource(media) ? "本地文件丢失 — 可从网络源播放" : "本地文件丢失")}>${escape_html(hasNetworkSource(media) ? "🔗" : "⚠")}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (p > 0) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="progress svelte-1ywh4zk"><div class="progress-fill svelte-1ywh4zk"${attr_style(`width:${stringify(p)}%`)}></div></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (shouldMask(media)) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="content-mask svelte-1ywh4zk" title="限制内容 — 点击查看"><span class="mask-icon svelte-1ywh4zk">🔞</span></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (onplay && media.type !== "image") {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="play-hint svelte-1ywh4zk" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22"><path d="M8 5v14l11-7z" fill="currentColor"></path></svg></span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div> <div class="poster-info svelte-1ywh4zk" title="查看详情"><div class="poster-title svelte-1ywh4zk"${attr("title", media.title ?? media.filename)}>${escape_html(media.title ?? media.filename)}</div> <div class="poster-meta svelte-1ywh4zk">`);
      if (media.year) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="muted svelte-1ywh4zk">${escape_html(media.year)}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (media.rating > 0) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="rating svelte-1ywh4zk">${escape_html("★".repeat(filled))}<span class="rating-dim svelte-1ywh4zk">${escape_html("★".repeat(5 - filled))}</span></span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (media.type) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="muted svelte-1ywh4zk">${escape_html(media.type)}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div></div></button>`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
function SeriesWall($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { items, mode = "poster", density = 180 } = $$props;
    const restrictedLibIds = derived(() => new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id))));
    function shouldMask(series) {
      return settingsStore.maskRestricted && restrictedLibIds().has(String(series.library_id));
    }
    const groups = derived(() => {
      const grouped = /* @__PURE__ */ new Map();
      for (const series of items) {
        const key = series.year ? String(series.year) : "unknown";
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(series);
      }
      return [...grouped.entries()].sort(([a], [b]) => a === "unknown" ? 1 : b === "unknown" ? -1 : Number(b) - Number(a)).map(([key, series]) => ({ key, label: key === "unknown" ? "未知年份" : `${key}年`, series }));
    });
    function seriesCard($$renderer3, s) {
      $$renderer3.push(`<button class="series-card svelte-14kte6c"${attr("data-id", s.id)}><div class="card-thumb svelte-14kte6c">`);
      if (s.poster_path) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<img${attr("src", seriesApi.posterUrl(s.id))}${attr("alt", s.title)} loading="lazy" class="svelte-14kte6c"/>`);
      } else {
        $$renderer3.push("<!--[-1-->");
        $$renderer3.push(`<div class="thumb-fallback svelte-14kte6c"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"></rect><line x1="2" y1="8" x2="22" y2="8"></line><polyline points="9,14 12,14 12,11"></polyline></svg></div>`);
      }
      $$renderer3.push(`<!--]--> <span class="ep-count svelte-14kte6c">${escape_html(s.episode_count)} 集</span> `);
      if (shouldMask(s)) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<div class="content-mask svelte-14kte6c" title="限制内容 — 点击查看"><span class="mask-icon svelte-14kte6c">🔞</span></div>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div> <div class="card-info svelte-14kte6c"><div class="card-title svelte-14kte6c"${attr("title", s.title)}>${escape_html(s.title)}</div> <div class="card-meta svelte-14kte6c">`);
      if (s.year) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<span class="muted svelte-14kte6c">${escape_html(s.year)}</span>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--> `);
      if (s.total_seasons) {
        $$renderer3.push("<!--[0-->");
        $$renderer3.push(`<span class="muted svelte-14kte6c">${escape_html(s.total_seasons)} 季</span>`);
      } else {
        $$renderer3.push("<!--[-1-->");
      }
      $$renderer3.push(`<!--]--></div></div></button>`);
    }
    $$renderer2.push(`<div${attr_class("series-view svelte-14kte6c", void 0, {
      "list-mode": mode === "list",
      "timeline-mode": mode === "timeline"
    })}${attr_style(`--media-card-width:${density}px`)}>`);
    if (mode === "timeline") {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<!--[-->`);
      const each_array = ensure_array_like(groups());
      for (let $$index_1 = 0, $$length = each_array.length; $$index_1 < $$length; $$index_1++) {
        let group = each_array[$$index_1];
        $$renderer2.push(`<section class="series-year svelte-14kte6c"><div class="year-head svelte-14kte6c"><strong class="svelte-14kte6c">${escape_html(group.label)}</strong><span class="svelte-14kte6c">${escape_html(group.series.length)} 部</span></div> <div class="series-wall svelte-14kte6c"><!--[-->`);
        const each_array_1 = ensure_array_like(group.series);
        for (let $$index = 0, $$length2 = each_array_1.length; $$index < $$length2; $$index++) {
          let s = each_array_1[$$index];
          seriesCard($$renderer2, s);
        }
        $$renderer2.push(`<!--]--></div></section>`);
      }
      $$renderer2.push(`<!--]-->`);
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<div class="series-wall svelte-14kte6c"><!--[-->`);
      const each_array_2 = ensure_array_like(items);
      for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
        let s = each_array_2[$$index_2];
        seriesCard($$renderer2, s);
      }
      $$renderer2.push(`<!--]--></div>`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
function UnifiedWall($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const posterRatio = {};
    let { items, density = 180 } = $$props;
    const restrictedLibIds = derived(() => new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id))));
    function shouldMask(libraryId) {
      return settingsStore.maskRestricted && restrictedLibIds().has(String(libraryId));
    }
    $$renderer2.push(`<div class="unified-wall svelte-rtkj1d"${attr_style(`--media-card-width:${density}px`)}><!--[-->`);
    const each_array = ensure_array_like(items);
    for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
      let item = each_array[$$index];
      if (item.kind === "series") {
        $$renderer2.push("<!--[0-->");
        const s = item.data;
        $$renderer2.push(`<button class="card series-card svelte-rtkj1d"><div class="card-thumb svelte-rtkj1d">`);
        if (s.poster_path) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<img${attr("src", seriesApi.posterUrl(s.id))}${attr("alt", s.title)} loading="lazy" class="svelte-rtkj1d"/>`);
        } else {
          $$renderer2.push("<!--[-1-->");
          $$renderer2.push(`<div class="thumb-fallback svelte-rtkj1d"><svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"></rect><line x1="2" y1="8" x2="22" y2="8"></line><polyline points="9,14 12,14 12,11"></polyline></svg></div>`);
        }
        $$renderer2.push(`<!--]--> <span class="badge ep-count svelte-rtkj1d">${escape_html(s.episode_count)} 集</span> <span class="badge type-tag svelte-rtkj1d">剧集</span> `);
        if (shouldMask(s.library_id)) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<div class="content-mask svelte-rtkj1d" title="限制内容 — 点击查看"><span class="mask-icon svelte-rtkj1d">🔞</span></div>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div> <div class="card-info svelte-rtkj1d"><div class="card-title svelte-rtkj1d"${attr("title", s.title)}>${escape_html(s.title)}</div> <div class="card-meta svelte-rtkj1d">`);
        if (s.year) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="muted svelte-rtkj1d">${escape_html(s.year)}</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (s.total_seasons) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="muted svelte-rtkj1d">${escape_html(s.total_seasons)} 季</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div></div></button>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        const m = item.data;
        const p = getProgress(m.metadata);
        const filled = Math.max(0, Math.min(5, m.rating));
        const av = isAvMedia(m);
        const usesSeriesCover = m.series_id != null;
        const hasImage = usesSeriesCover || !!m.poster || !!m.thumbnail;
        const ratioCls = hasImage ? posterRatio[String(m.id)] : void 0;
        const defaultRatio = usesSeriesCover || m.poster ? av && !usesSeriesCover ? "4 / 3" : "2 / 3" : "4 / 3";
        const ratioStr = ratioCls ?? defaultRatio;
        const isWide = !usesSeriesCover && (ratioCls === "4 / 3" || !ratioCls && !m.poster && !!m.thumbnail);
        $$renderer2.push(`<button${attr_class("card media-card svelte-rtkj1d", void 0, { "av-poster": !hasImage && av, "wide": isWide })}><div${attr_class("card-thumb svelte-rtkj1d", void 0, { "av-poster": av, "has-poster": !!m.poster })}${attr_style("", { "aspect-ratio": hasImage ? ratioStr : void 0 })}>`);
        if (usesSeriesCover) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<img${attr("src", seriesApi.posterUrl(m.series_id))}${attr("alt", m.series_title ?? m.title ?? m.filename)} loading="lazy" class="svelte-rtkj1d" onerror="this.__e=event" onload="this.__e=event"/>`);
        } else if (m.poster) {
          $$renderer2.push("<!--[1-->");
          $$renderer2.push(`<img${attr("src", mediaApi.posterUrl(m.id, m.updated_at))}${attr("alt", m.title ?? m.filename)} loading="lazy" class="svelte-rtkj1d" onerror="this.__e=event" onload="this.__e=event"/>`);
        } else if (m.thumbnail) {
          $$renderer2.push("<!--[2-->");
          $$renderer2.push(`<img${attr("src", mediaApi.thumbnailUrl(m.id, m.updated_at))}${attr("alt", m.filename)} loading="lazy" class="svelte-rtkj1d" onerror="this.__e=event" onload="this.__e=event"/>`);
        } else {
          $$renderer2.push("<!--[-1-->");
          $$renderer2.push(`<div class="thumb-fallback svelte-rtkj1d"><span>${escape_html(m.type === "video" ? "▶" : m.type === "audio" ? "♪" : "▣")}</span></div>`);
        }
        $$renderer2.push(`<!--]--> `);
        if (m.duration) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="badge duration svelte-rtkj1d">${escape_html(formatTime(m.duration))}</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (!m.file_missing && (m.source_type === "network" || m.source_type === "both")) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="badge net-badge svelte-rtkj1d"${attr("title", m.source_type === "both" ? "本地 + 网络源" : "网络媒体")}>${escape_html(m.source_type === "both" ? "本+网" : "网")}</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (m.favorite) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="badge fav svelte-rtkj1d">♥</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (m.file_missing) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span${attr_class("badge missing-badge svelte-rtkj1d", void 0, { "has-network": hasNetworkSource(m) })}${attr("title", hasNetworkSource(m) ? "本地文件丢失 — 可从网络源播放" : "本地文件丢失")}>${escape_html(hasNetworkSource(m) ? "🔗" : "⚠")}</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (p > 0) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<div class="progress svelte-rtkj1d"><div class="progress-fill svelte-rtkj1d"${attr_style(`width:${stringify(p)}%`)}></div></div>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (shouldMask(m.library_id)) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<div class="content-mask svelte-rtkj1d" title="限制内容 — 点击查看"><span class="mask-icon svelte-rtkj1d">🔞</span></div>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div> <div class="card-info svelte-rtkj1d"><div class="card-title svelte-rtkj1d"${attr("title", m.title ?? m.filename)}>${escape_html(m.title ?? m.filename)}</div> <div class="card-meta svelte-rtkj1d">`);
        if (m.year) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="muted svelte-rtkj1d">${escape_html(m.year)}</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (m.rating > 0) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="rating svelte-rtkj1d">${escape_html("★".repeat(filled))}<span class="rating-dim svelte-rtkj1d">${escape_html("★".repeat(5 - filled))}</span></span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div></div></button>`);
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
function ListView($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { items, libraryMap = {}, tagMap = {} } = $$props;
    const restrictedLibIds = derived(() => new Set(librariesStore.libraries.filter((l) => l.is_restricted).map((l) => String(l.id))));
    function shouldMask(media) {
      return settingsStore.maskRestricted && restrictedLibIds().has(String(media.library_id));
    }
    $$renderer2.push(`<div class="list-view svelte-1jeoif4"><div class="list-head svelte-1jeoif4"><div class="col col-thumb svelte-1jeoif4"></div> <div class="col col-title svelte-1jeoif4">标题</div> <div class="col col-lib svelte-1jeoif4">库</div> <div class="col col-duration svelte-1jeoif4">时长</div> <div class="col col-res svelte-1jeoif4">分辨率</div> <div class="col col-size svelte-1jeoif4">大小</div> <div class="col col-rating svelte-1jeoif4">评分</div> <div class="col col-tags svelte-1jeoif4">标签</div></div> <div class="list-body"><!--[-->`);
    const each_array = ensure_array_like(
      // 桌面应用（Windows/macOS）：一次性渲染全部 items（见 PosterWall 说明）
      items
    );
    for (let $$index_1 = 0, $$length = each_array.length; $$index_1 < $$length; $$index_1++) {
      let media = each_array[$$index_1];
      const p = getProgress(media.metadata);
      $$renderer2.push(`<button class="row svelte-1jeoif4"${attr("data-id", media.id)}><div class="col col-thumb svelte-1jeoif4"><div class="mini-thumb svelte-1jeoif4"${attr("title", media.type !== "image" ? "点击封面播放" : "查看详情")}>`);
      if (media.series_id != null) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<img${attr("src", seriesApi.posterUrl(media.series_id))} alt="" loading="lazy" class="svelte-1jeoif4" onerror="this.__e=event"/>`);
      } else if (media.poster) {
        $$renderer2.push("<!--[1-->");
        $$renderer2.push(`<img${attr("src", mediaApi.posterUrl(media.id, media.updated_at))} alt="" loading="lazy" class="svelte-1jeoif4" onerror="this.__e=event"/>`);
      } else if (media.thumbnail) {
        $$renderer2.push("<!--[2-->");
        $$renderer2.push(`<img${attr("src", mediaApi.thumbnailUrl(media.id, media.updated_at))} alt="" loading="lazy" class="svelte-1jeoif4" onerror="this.__e=event"/>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`<span class="fb">${escape_html(media.type === "video" ? "▶" : media.type === "audio" ? "♪" : "▣")}</span>`);
      }
      $$renderer2.push(`<!--]--> `);
      if (!media.file_missing && (media.source_type === "network" || media.source_type === "both")) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="net-tag svelte-1jeoif4">${escape_html(media.source_type === "both" ? "本+网" : "网")}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (shouldMask(media)) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="content-mask svelte-1jeoif4" title="限制内容 — 点击查看"><span class="mask-icon svelte-1jeoif4">🔞</span></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div></div> <div class="col col-title svelte-1jeoif4"${attr("title", media.filename)}><span${attr_class("title-text svelte-1jeoif4", void 0, { "missing": media.file_missing })}>${escape_html(media.filename)}</span> `);
      if (media.file_missing) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span${attr_class("missing-tag svelte-1jeoif4", void 0, { "has-net": hasNetworkSource(media) })}>${escape_html(hasNetworkSource(media) ? "🔗网络" : "⚠丢失")}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (media.favorite) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="fav svelte-1jeoif4">♥</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> `);
      if (p > 0) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="mini-prog svelte-1jeoif4"${attr("title", `播放进度 ${stringify(Math.round(p))}%`)}><span${attr_style(`width:${stringify(p)}%`)} class="svelte-1jeoif4"></span></span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div> <div class="col col-lib svelte-1jeoif4">${escape_html(libraryMap[media.library_id] ?? "—")}</div> <div class="col col-duration svelte-1jeoif4">${escape_html(media.duration ? formatTime(media.duration) : "—")}</div> <div class="col col-res svelte-1jeoif4">${escape_html(formatResolution(media.width, media.height))}</div> <div class="col col-size svelte-1jeoif4">${escape_html(formatSize(media.size))}</div> <div class="col col-rating svelte-1jeoif4">`);
      if (media.rating > 0) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<span class="rating svelte-1jeoif4">${escape_html("★".repeat(media.rating))}</span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`—`);
      }
      $$renderer2.push(`<!--]--></div> <div class="col col-tags svelte-1jeoif4">`);
      if (media.tags && media.tags.length) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="tag-list svelte-1jeoif4"><!--[-->`);
        const each_array_1 = ensure_array_like(media.tags.slice(0, 3));
        for (let $$index = 0, $$length2 = each_array_1.length; $$index < $$length2; $$index++) {
          let tid = each_array_1[$$index];
          $$renderer2.push(`<span class="tag svelte-1jeoif4">${escape_html(tagMap?.[tid] ?? tid)}</span>`);
        }
        $$renderer2.push(`<!--]--> `);
        if (media.tags.length > 3) {
          $$renderer2.push("<!--[0-->");
          $$renderer2.push(`<span class="tag more svelte-1jeoif4">+${escape_html(media.tags.length - 3)}</span>`);
        } else {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
        $$renderer2.push(`—`);
      }
      $$renderer2.push(`<!--]--></div></button>`);
    }
    $$renderer2.push(`<!--]--></div></div>`);
  });
}
function TimelineView($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { items, onSelect, onplay, density = 180 } = $$props;
    function yearOf(media) {
      const y = media.year;
      if (y && y > 1900) return y;
      const rd = media.release_date;
      if (rd) {
        const parsed = parseInt(rd.slice(0, 4), 10);
        if (!isNaN(parsed) && parsed > 1900) return parsed;
      }
      return 0;
    }
    function groupKey(media) {
      const y = yearOf(media);
      if (!y) return { key: "unknown", label: "未知年份" };
      return { key: String(y), label: `${y}年` };
    }
    const groups = derived(() => {
      const map = /* @__PURE__ */ new Map();
      for (const m of items) {
        const { key, label } = groupKey(m);
        if (!map.has(key)) map.set(key, { key, label, items: [] });
        map.get(key).items.push(m);
      }
      return Array.from(map.values()).sort((a, b) => {
        if (a.key === "unknown") return 1;
        if (b.key === "unknown") return -1;
        return Number(b.key) - Number(a.key);
      });
    });
    $$renderer2.push(`<div class="timeline svelte-v8bvo1">`);
    const each_array = ensure_array_like(groups());
    if (each_array.length !== 0) {
      $$renderer2.push("<!--[-->");
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let group = each_array[$$index];
        $$renderer2.push(`<section class="tl-group svelte-v8bvo1"><div class="tl-head svelte-v8bvo1"><span class="tl-label svelte-v8bvo1">${escape_html(group.label)}</span> <span class="tl-count svelte-v8bvo1">${escape_html(group.items.length)} 项</span></div> `);
        PosterWall($$renderer2, { items: group.items, onSelect, onplay, mode: "mixed", density });
        $$renderer2.push(`<!----></section>`);
      }
    } else {
      $$renderer2.push("<!--[!-->");
      $$renderer2.push(`<div class="tl-empty svelte-v8bvo1">暂无媒体</div>`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
function WatchCenter($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let {
      loading = false,
      error = null
    } = $$props;
    $$renderer2.push(`<div class="watch-center svelte-kh62qd">`);
    if (loading && true) {
      $$renderer2.push("<!--[0-->");
      $$renderer2.push(`<div class="loading-grid svelte-kh62qd" aria-label="正在加载观看中心"><!--[-->`);
      const each_array_1 = ensure_array_like(Array(6));
      for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
        each_array_1[$$index_1];
        $$renderer2.push(`<div class="loading-card svelte-kh62qd"></div>`);
      }
      $$renderer2.push(`<!--]--></div>`);
    } else if (error && true) {
      $$renderer2.push("<!--[1-->");
      $$renderer2.push(`<div class="home-state svelte-kh62qd"><strong class="svelte-kh62qd">观看中心暂时无法加载</strong><span class="svelte-kh62qd">${escape_html(error)}</span></div>`);
    } else {
      $$renderer2.push("<!--[-1-->");
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    function parseFilterFromUrl(sp) {
      const f = {};
      const type = sp.get("type");
      if (type) f.type = type;
      const genre = sp.get("genre");
      if (genre) f.genre = genre;
      const country = sp.get("country");
      if (country) f.country = country;
      const year = sp.get("year");
      if (year) f.year = Number(year);
      const resolution = sp.get("resolution");
      if (resolution) f.resolution = resolution;
      const ratingMin = sp.get("rating_min");
      if (ratingMin) f.ratingMin = Number(ratingMin);
      const duration = sp.get("duration");
      if (duration) f.duration = duration;
      const tags2 = sp.get("tags");
      if (tags2) f.tags = tags2.split(",").filter(Boolean);
      return f;
    }
    function parseSortFromUrl(sp) {
      const field = sp.get("sort") || "created_at";
      const order = sp.get("order") || "desc";
      return { field, order };
    }
    store_get($$store_subs ??= {}, "$pageStore", page).url.pathname;
    const initialParams = store_get($$store_subs ??= {}, "$pageStore", page).url.searchParams;
    let pageMode = initialParams.get("mode") === "library" || initialParams.has("view") || initialParams.has("section") ? "library" : "center";
    const initialSection = initialParams.get("section");
    let section = initialSection && ["all", "movie", "tv", "image", "audio"].includes(initialSection) ? initialSection : "all";
    const initialIsTv = initialSection === "tv";
    let filter = initialIsTv ? {} : parseFilterFromUrl(initialParams);
    let sort = initialIsTv ? { field: "created_at", order: "desc" } : parseSortFromUrl(initialParams);
    let view = initialParams.get("view") || "" || "mixed";
    let page$1 = 1;
    let density = 180;
    let items = [];
    let seriesItems = [];
    let total = 0;
    let homeLoading = false;
    let homeError = null;
    let searchInput = initialIsTv ? "" : initialParams.get("q") || "";
    let searchQuery = initialIsTv ? "" : initialParams.get("q") || "";
    let libraries = [];
    let tags = [];
    let filterOptions = { genres: [], countries: [], years: [] };
    const libraryMap = derived(() => Object.fromEntries(libraries.map((l) => [l.id, l.name])));
    const currentLibrary = derived(() => {
      if (navigation.current.type !== "library") return null;
      return libraries.find((l) => l.id === navigation.current.value) ?? null;
    });
    const isTvLibrary = derived(() => currentLibrary()?.scrape_mode === "tv");
    const hasTvLibraries = derived(() => libraries.some((l) => l.scrape_mode === "tv"));
    const navNode = derived(() => navigation.current);
    const clientFilterActive = derived(() => !!filter.resolution || !!filter.duration);
    const hasActiveFilter = derived(() => !!searchQuery.trim() || !!filter.type || !!filter.genre || !!filter.country || filter.year != null || !!filter.resolution || filter.ratingMin != null || !!filter.duration || (filter.tags ?? []).length > 0);
    const smartFolderMode = derived(() => navNode().type === "smartfolder");
    const showSeriesInAll = derived(() => section === "all" && navNode().type === "all" && hasTvLibraries() && !clientFilterActive() && !smartFolderMode());
    const showSeriesOnly = derived(() => section === "tv" || section === "all" && isTvLibrary() && navNode().type === "library");
    const unifiedItems = derived(() => {
      if (!showSeriesInAll()) return [];
      const seriesPart = seriesItems.map((s) => ({ kind: "series", data: s }));
      const mediaPart = items.map((m) => ({ kind: "media", data: m }));
      return [...seriesPart, ...mediaPart];
    });
    const tagMap = derived(() => Object.fromEntries(tags.map((t) => [t.id, t.name])));
    const heading = derived(() => navNode().label || "全部媒体");
    const sortOptions = [
      { field: "created_at", label: "添加时间" },
      { field: "filename", label: "标题" },
      { field: "rating", label: "评分" },
      { field: "duration", label: "时长" },
      { field: "progress", label: "进度" }
    ];
    librariesStore.revision;
    function saveScrollState(preferId) {
      const container = document.querySelector(".media-content");
      mediaScroll.top = container?.scrollTop ?? 0;
      mediaScroll.page = page$1;
      mediaScroll.anchorId = "";
      mediaScroll.anchorOffset = 0;
      mediaScroll.savedItems = items;
      mediaScroll.savedSeries = seriesItems;
      if (!container) return;
      let card = null;
      if (preferId) {
        card = container.querySelector(`[data-id="${preferId}"]`);
      }
      if (!card) {
        const vTop = container.getBoundingClientRect().top;
        for (const c of container.querySelectorAll("[data-id]")) {
          const r = c.getBoundingClientRect();
          if (r.bottom > vTop + 4) {
            card = c;
            break;
          }
        }
      }
      if (card) {
        const vTop = container.getBoundingClientRect().top;
        mediaScroll.anchorId = card.getAttribute("data-id") ?? "";
        mediaScroll.anchorOffset = card.getBoundingClientRect().top - vTop;
        console.log("[scroll] saved", {
          top: mediaScroll.top,
          page: mediaScroll.page,
          anchorId: mediaScroll.anchorId,
          anchorOffset: mediaScroll.anchorOffset,
          snapshot: items.length
        });
      } else {
        console.log("[scroll] saved (no card)", {
          top: mediaScroll.top,
          page: mediaScroll.page,
          snapshot: items.length
        });
      }
    }
    function onSelect(media) {
      saveScrollState(media.id);
      goto(`/detail/${media.id}`);
    }
    function onPlayMedia(m) {
      if (m.type === "image") return;
      saveScrollState(m.id);
      const from = encodeURIComponent(location.pathname + location.search);
      goto(`/player?id=${m.id}&from=${from}`);
    }
    Array.from({ length: 18 });
    head("14bqwv7", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>${escape_html(heading())} — vitoice</title>`);
      });
    });
    $$renderer2.push(`<div class="media-page svelte-14bqwv7"><div class="ambient-glow svelte-14bqwv7" aria-hidden="true"></div> <nav class="page-mode-tabs svelte-14bqwv7" aria-label="媒体页面"><button${attr_class("svelte-14bqwv7", void 0, { "active": pageMode === "center" })}>观看中心</button> <button${attr_class("svelte-14bqwv7", void 0, { "active": pageMode === "library" })}>媒体库</button></nav> `);
    if (pageMode === "center") {
      $$renderer2.push("<!--[0-->");
      WatchCenter($$renderer2, {
        loading: homeLoading,
        error: homeError
      });
    } else {
      $$renderer2.push("<!--[-1-->");
      $$renderer2.push(`<header class="page-header svelte-14bqwv7"><div class="header-title-row svelte-14bqwv7"><span class="accent-dot svelte-14bqwv7" aria-hidden="true"></span> <h1 class="title svelte-14bqwv7">${escape_html(heading())}</h1></div> <p class="subtitle svelte-14bqwv7"><span class="count-pill svelte-14bqwv7"><span class="count-num svelte-14bqwv7">${escape_html(total.toLocaleString("zh-CN"))}</span> <span class="count-unit svelte-14bqwv7">${escape_html(isTvLibrary() ? "部剧" : "项媒体")}</span></span></p></header> <nav class="section-tabs svelte-14bqwv7" aria-label="媒体分类"><!--[-->`);
      const each_array = ensure_array_like([
        { id: "all", label: "全部", count: total },
        { id: "movie", label: "电影", count: 0 },
        { id: "tv", label: "电视剧", count: 0 },
        { id: "image", label: "图片", count: 0 },
        { id: "audio", label: "音频", count: 0 }
      ]);
      for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
        let tab = each_array[$$index];
        $$renderer2.push(`<button${attr_class("section-tab svelte-14bqwv7", void 0, { "active": section === tab.id })}${attr("aria-current", section === tab.id ? "page" : void 0)}><span class="svelte-14bqwv7">${escape_html(tab.label)}</span> <span class="section-count svelte-14bqwv7">${escape_html(tab.count.toLocaleString("zh-CN"))}</span></button>`);
      }
      $$renderer2.push(`<!--]--></nav> `);
      {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> <div class="toolbar svelte-14bqwv7"><div class="toolbar-left svelte-14bqwv7">`);
      if (!showSeriesOnly()) {
        $$renderer2.push("<!--[0-->");
        FilterBar($$renderer2, { filter, filterOptions });
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div> <div class="toolbar-right svelte-14bqwv7">`);
      if (!showSeriesOnly()) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="search-box svelte-14bqwv7"><svg class="search-icon svelte-14bqwv7" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="7" cy="7" r="4.5" class="svelte-14bqwv7"></circle><line x1="10.5" y1="10.5" x2="13.5" y2="13.5" stroke-linecap="round" class="svelte-14bqwv7"></line></svg> <input type="text" class="search-input svelte-14bqwv7" placeholder="搜索标题或文件名…"${attr("value", searchInput)}/></div> <span class="toolbar-divider svelte-14bqwv7" aria-hidden="true"></span> <div class="sort-group svelte-14bqwv7" role="group" aria-label="排序"><!--[-->`);
        const each_array_2 = ensure_array_like(sortOptions);
        for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
          let o = each_array_2[$$index_2];
          $$renderer2.push(`<button${attr_class("sort-btn svelte-14bqwv7", void 0, { "active": sort.field === o.field })}${attr("title", o.label)}><span class="sort-label svelte-14bqwv7">${escape_html(o.label)}</span> `);
          if (sort.field === o.field) {
            $$renderer2.push("<!--[0-->");
            $$renderer2.push(`<svg class="sort-arrow svelte-14bqwv7" viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">`);
            if (sort.order === "asc") {
              $$renderer2.push("<!--[0-->");
              $$renderer2.push(`<polyline points="3,8 6,4 9,8" class="svelte-14bqwv7"></polyline>`);
            } else {
              $$renderer2.push("<!--[-1-->");
              $$renderer2.push(`<polyline points="3,4 6,8 9,4" class="svelte-14bqwv7"></polyline>`);
            }
            $$renderer2.push(`<!--]--></svg>`);
          } else {
            $$renderer2.push("<!--[-1-->");
          }
          $$renderer2.push(`<!--]--></button>`);
        }
        $$renderer2.push(`<!--]--></div> <span class="toolbar-divider svelte-14bqwv7" aria-hidden="true"></span>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--> <div class="view-switch svelte-14bqwv7" role="group" aria-label="视图模式"><button${attr_class("vs-btn svelte-14bqwv7", void 0, { "active": view === "mixed" })} title="混合媒体墙"${attr("aria-pressed", view === "mixed")}><svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true" class="svelte-14bqwv7"><rect x="2" y="2" width="5" height="7" rx="1" class="svelte-14bqwv7"></rect><rect x="9" y="2" width="5" height="3" rx="1" class="svelte-14bqwv7"></rect><rect x="9" y="7" width="5" height="7" rx="1" class="svelte-14bqwv7"></rect><rect x="2" y="11" width="5" height="3" rx="1" class="svelte-14bqwv7"></rect></svg></button> <button${attr_class("vs-btn svelte-14bqwv7", void 0, { "active": view === "poster" })} title="海报墙"${attr("aria-pressed", view === "poster")}><svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true" class="svelte-14bqwv7"><rect x="2.25" y="2.25" width="4.75" height="4.75" rx="1.25" class="svelte-14bqwv7"></rect><rect x="9" y="2.25" width="4.75" height="4.75" rx="1.25" class="svelte-14bqwv7"></rect><rect x="2.25" y="9" width="4.75" height="4.75" rx="1.25" class="svelte-14bqwv7"></rect><rect x="9" y="9" width="4.75" height="4.75" rx="1.25" class="svelte-14bqwv7"></rect></svg></button> <button${attr_class("vs-btn svelte-14bqwv7", void 0, { "active": view === "list" })} title="列表"${attr("aria-pressed", view === "list")}><svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true" class="svelte-14bqwv7"><line x1="2.5" y1="4" x2="13.5" y2="4" class="svelte-14bqwv7"></line><line x1="2.5" y1="8" x2="13.5" y2="8" class="svelte-14bqwv7"></line><line x1="2.5" y1="12" x2="13.5" y2="12" class="svelte-14bqwv7"></line></svg></button> <button${attr_class("vs-btn svelte-14bqwv7", void 0, { "active": view === "timeline" })} title="时间轴"${attr("aria-pressed", view === "timeline")}><svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="svelte-14bqwv7"><rect x="2" y="3.25" width="12" height="10.5" rx="1.5" class="svelte-14bqwv7"></rect><line x1="2" y1="6.25" x2="14" y2="6.25" class="svelte-14bqwv7"></line><line x1="5" y1="1.75" x2="5" y2="4" class="svelte-14bqwv7"></line><line x1="11" y1="1.75" x2="11" y2="4" class="svelte-14bqwv7"></line><line x1="5" y1="9" x2="5" y2="11" class="svelte-14bqwv7"></line><line x1="8" y1="9" x2="8" y2="11" class="svelte-14bqwv7"></line><line x1="11" y1="9" x2="11" y2="11" class="svelte-14bqwv7"></line></svg></button></div> <span class="toolbar-divider svelte-14bqwv7" aria-hidden="true"></span> <label class="density-control svelte-14bqwv7" title="调整卡片密度"><span class="svelte-14bqwv7">紧凑</span> <input type="range" min="132" max="220" step="4"${attr("value", density)} aria-label="卡片密度" class="svelte-14bqwv7"/> <span class="svelte-14bqwv7">舒展</span></label></div></div> <div class="media-content svelte-14bqwv7">`);
      if (showSeriesOnly() && seriesItems.length > 0) {
        $$renderer2.push("<!--[2-->");
        SeriesWall($$renderer2, {
          items: seriesItems,
          mode: view,
          density
        });
      } else if (showSeriesOnly() && seriesItems.length === 0) {
        $$renderer2.push("<!--[3-->");
        $$renderer2.push(`<div class="empty-state anim-fade-in svelte-14bqwv7"><div class="empty-illustration-wrap svelte-14bqwv7"><svg class="empty-illustration svelte-14bqwv7" viewBox="0 0 240 180" width="220" height="165" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><defs class="svelte-14bqwv7"><linearGradient id="cardGrad" x1="0" y1="0" x2="1" y2="1" class="svelte-14bqwv7"><stop offset="0%" stop-color="var(--accent)" stop-opacity="0.28" class="svelte-14bqwv7"></stop><stop offset="100%" stop-color="var(--accent2)" stop-opacity="0.14" class="svelte-14bqwv7"></stop></linearGradient><linearGradient id="playGrad" x1="0" y1="0" x2="1" y2="1" class="svelte-14bqwv7"><stop offset="0%" stop-color="var(--accent)" class="svelte-14bqwv7"></stop><stop offset="100%" stop-color="var(--accent-hover)" class="svelte-14bqwv7"></stop></linearGradient><radialGradient id="glowGrad" cx="0.5" cy="0.5" r="0.5" class="svelte-14bqwv7"><stop offset="0%" stop-color="var(--accent)" stop-opacity="0.18" class="svelte-14bqwv7"></stop><stop offset="100%" stop-color="var(--accent)" stop-opacity="0" class="svelte-14bqwv7"></stop></radialGradient></defs><circle cx="120" cy="92" r="78" fill="url(#glowGrad)" class="svelte-14bqwv7"></circle><rect class="card-back svelte-14bqwv7" x="78" y="34" width="100" height="124" rx="16" fill="var(--accent)" opacity="0.06"></rect><rect class="card-back2 svelte-14bqwv7" x="86" y="40" width="100" height="124" rx="16" fill="var(--accent)" opacity="0.05"></rect><rect x="70" y="30" width="100" height="124" rx="15" fill="url(#cardGrad)" stroke="var(--accent)" stroke-opacity="0.38" stroke-width="1.4" class="svelte-14bqwv7"></rect><rect x="80" y="40" width="80" height="12" rx="3" fill="var(--accent)" opacity="0.14" class="svelte-14bqwv7"></rect><circle cx="86" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><circle cx="94" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><circle cx="102" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><circle cx="110" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><circle cx="118" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><circle cx="126" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><circle cx="134" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><circle cx="142" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><circle cx="150" cy="46" r="1.7" fill="var(--bg-elevated)" class="svelte-14bqwv7"></circle><path d="M106 72 L106 112 L140 92 Z" fill="url(#playGrad)" class="svelte-14bqwv7"></path><rect x="82" y="126" width="56" height="6" rx="3" fill="var(--accent)" opacity="0.22" class="svelte-14bqwv7"></rect><rect x="82" y="138" width="34" height="5" rx="2.5" fill="var(--accent)" opacity="0.12" class="svelte-14bqwv7"></rect><circle class="sparkle s1 svelte-14bqwv7" cx="48" cy="56" r="2.4" fill="var(--accent2)"></circle><circle class="sparkle s2 svelte-14bqwv7" cx="188" cy="68" r="1.8" fill="var(--accent)"></circle><circle class="sparkle s3 svelte-14bqwv7" cx="178" cy="142" r="2.2" fill="var(--accent2)"></circle><circle class="sparkle s4 svelte-14bqwv7" cx="52" cy="132" r="1.6" fill="var(--accent)"></circle><path class="sparkle s5 svelte-14bqwv7" d="M196 104 L196 110 M193 107 L199 107" stroke="var(--accent2)" stroke-width="1.4" stroke-linecap="round"></path></svg></div> <h2 class="empty-title svelte-14bqwv7">暂无剧集</h2> <p class="empty-desc svelte-14bqwv7">扫描电视剧库后，系统将自动按剧名聚合展示。<br class="svelte-14bqwv7"/>请确认库中已导入视频文件并完成扫描。</p> <a class="empty-cta svelte-14bqwv7" href="/libraries"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="svelte-14bqwv7"><polyline points="2,8 6,12 14,4" class="svelte-14bqwv7"></polyline></svg> <span class="svelte-14bqwv7">前往库管理</span></a></div>`);
      } else if (showSeriesInAll() && unifiedItems().length > 0) {
        $$renderer2.push("<!--[4-->");
        UnifiedWall($$renderer2, {
          items: unifiedItems(),
          density
        });
      } else if (showSeriesInAll() && unifiedItems().length === 0) {
        $$renderer2.push("<!--[5-->");
        $$renderer2.push(`<div class="state anim-fade-in svelte-14bqwv7"><div class="state-title svelte-14bqwv7">暂无媒体</div> <div class="state-hint svelte-14bqwv7">请确认已导入媒体文件并完成扫描。</div></div>`);
      } else if (items.length === 0 && unifiedItems().length === 0) {
        $$renderer2.push("<!--[6-->");
        $$renderer2.push(`<div class="state anim-fade-in svelte-14bqwv7"><div class="state-title svelte-14bqwv7">${escape_html(hasActiveFilter() ? "没有匹配的媒体" : "暂无媒体")}</div> <div class="state-hint svelte-14bqwv7">${escape_html(hasActiveFilter() ? "尝试调整筛选条件或搜索关键词。" : "请确认已导入媒体文件并完成扫描。")}</div></div>`);
      } else if (view === "mixed" || view === "poster") {
        $$renderer2.push("<!--[7-->");
        PosterWall($$renderer2, { items, onSelect, onplay: onPlayMedia, mode: view, density });
      } else if (view === "list") {
        $$renderer2.push("<!--[8-->");
        ListView($$renderer2, {
          items,
          libraryMap: libraryMap(),
          tagMap: tagMap()
        });
      } else {
        $$renderer2.push("<!--[-1-->");
        TimelineView($$renderer2, { items, onSelect, onplay: onPlayMedia, density });
      }
      $$renderer2.push(`<!--]--> `);
      if ((items.length > 0 || seriesItems.length > 0 || unifiedItems().length > 0) && true) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="infinite-sentinel svelte-14bqwv7"></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]--></div> `);
      if ((items.length > 0 || seriesItems.length > 0 || unifiedItems().length > 0) && true) {
        $$renderer2.push("<!--[0-->");
        $$renderer2.push(`<div class="infinite-footer svelte-14bqwv7"><div class="infinite-status svelte-14bqwv7" aria-live="polite">`);
        {
          $$renderer2.push("<!--[-1-->");
        }
        $$renderer2.push(`<!--]--></div></div>`);
      } else {
        $$renderer2.push("<!--[-1-->");
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
export {
  _page as default
};
