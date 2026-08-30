# vitoice 媒体管理项目 — UX 与性能优化分析报告

> 分析范围：前端 Svelte 组件（PosterWall / ListView / +page / Sidebar / FilterBar）、API 客户端、后端 media.py 列表与图片端点、设置与样式系统。仅读取分析，未修改任何文件。

---

## 一、性能瓶颈

### 1.1 大列表渲染：缺少虚拟化（高优先级）

- **PosterWall.svelte**（`g:\Code\vitoice_fin\frontend\src\lib\components\media\PosterWall.svelte`）
  使用 `{#each items as media (media.id)}` 一次性渲染全部传入的 `items`，没有任何虚拟滚动。每页最大 120 张卡片（`pageSize` 可选 120），每张卡片含图片 + 多个覆盖层（时长/收藏/进度条）。当用户选择 120/页或客户端筛选模式一次性拉取 1000 条时，DOM 节点数会暴增。
- **ListView.svelte**（`g:\Code\vitoice_fin\frontend\src\lib\components\media\ListView.svelte`）
  同样无虚拟滚动，每行是 8 列 grid + 缩略图 + 标签列表，1000 行时渲染开销显著。
- **建议**：引入虚拟滚动（如 `svelte-virtual-list` 或自研 IntersectionObserver 方案），仅渲染视口内 + 缓冲区卡片。对 ListView 尤其重要。

### 1.2 客户端筛选的“全量拉取”反模式（高优先级）

在 `+page.svelte` 的 `loadMedia()` 中（第 185-192 行）：

```js
} else if (clientFilterActive) {
  const params = { ...buildApiParams(), page: 1, page_size: 1000 };
  const res = await mediaApi.list(params);
  const filtered = applyClientFilters(res.items ?? []);
  allFiltered = filtered;
  items = paginate(filtered);
```

当“分辨率”或“时长”筛选激活时，前端请求 `page_size: 1000` 的全量数据再在客户端过滤分页。对大库（数千～数万条目）这是严重的性能与内存问题：
- 单次传输可能达数 MB JSON；
- 后端 `page_size` 上限为 100（见下文），1000 会被截断为 100，导致**筛选结果不完整**（隐藏 bug）；
- 智能文件夹 `preview` 同样全量拉取后客户端过滤。

- **建议**：将分辨率/时长筛选下沉到后端（后端已支持 `resolution_min`、`duration_min`/`duration_max`，只需前端补传参数），彻底移除客户端分页路径。

### 1.3 图片加载策略薄弱（高优先级）

- **PosterWall / ListView** 已使用 `loading="lazy"`（好），但存在以下不足：
  1. **无 `decoding="async"`**：大图解码阻塞主线程。
  2. **无尺寸变体 / srcset**：ListView 的 40×40 mini-thumb 与 PosterWall 的 ~180px 卡片，都请求**原始全尺寸**缩略图（`mediaApi.thumbnailUrl(id)` / `posterUrl(id)`），浪费带宽。
  3. **无 `onerror` 回退**：缩略图 404 时仅显示 alt 文本/裂图图标，不会回退到 fallback 占位符（代码里明明有 `.thumb-fallback` 分支，但只在无 `poster`/`thumbnail` 字段时生效，图片加载失败时不触发）。
  4. **无 LQIP / 模糊占位**：加载前是纯色块，无渐进式体验。
- **后端缩略图/海报端点**（`media.py` 第 734-756 行）返回 `FileResponse`，**无 `Cache-Control` / `ETag` / `Last-Modified` 头**。浏览器只能用启发式缓存，刷新时可能重复请求 60-120 张图。这是媒体墙场景下最显著的重复网络开销。
- **建议**：
  - 后端为 thumbnail/poster 端点增加 `Cache-Control: public, max-age=604800, immutable` 与 `ETag`（基于文件 mtime/size）；
  - 前端 `<img>` 增加 `decoding="async"`、`width`/`height`（或保持 aspect-ratio）、`onerror` 回退；
  - 后端按需生成多档缩略图（small/medium/large），前端用 `srcset` 选择。

### 1.4 API 客户端缺失缓存/去重/重试（中高优先级）

`client.ts`（`g:\Code\vitoice_fin\frontend\src\lib\api\client.ts`）是一个极简封装：
- **无请求缓存**：同一 GET（如 `tagsApi.list()`、`librariesApi.list()`）被多处重复发起。
- **无请求去重**：并发相同请求各自独立发出（如 `+page.svelte` 的 `loadSidebarData` 与 Sidebar 的 `librariesStore.reload` 可能同时拉取标签）。
- **无重试逻辑**：网络抖动直接报错，无指数退避。
- **无超时**：`fetch` 无 `AbortSignal` 传入（接口定义了 `signal` 但 `client.get/post` 未暴露）。
- **BASE_URL 硬编码** `http://127.0.0.1:8765/api`，无环境变量适配。
- **建议**：为 GET 增加带 TTL 的内存缓存 + 同 key 并发去重（Promise 复用）；为可重试错误增加 1-2 次指数退避；暴露 `signal` 与超时。

### 1.5 后端列表查询的潜在慢点（中优先级）

`media.py` `list_media`（第 68-181 行）：
- **全文搜索用 `ILIKE '%{search}%'`**（第 132-139 行）：前导通配符无法使用 B-tree 索引，全表扫描。大库下搜索会明显变慢。建议改用 SQLite FTS5 / PostgreSQL `tsvector` 或至少 trigram 索引。
- **计数查询** `select(func.count()).select_from(query.subquery())`（第 152 行）：把带全部过滤条件的查询包成子查询再 count，复杂筛选下较重。可考虑用 `select(func.count(Media.id))` 配合相同 where 子句，或缓存 total。
- **列表接口疑似 N+1**：列表返回 `MediaResponse.model_validate(m)`，若 `MediaResponse` 含 `tags` 字段而查询未 `selectinload(Media.video_tags)`（详情接口才做了 selectinload），会触发懒加载 N+1。需核实 schema；若是，列表接口应加 `selectinload`。
- **page_size 上限 100**（第 86 行 `le=100`）：前端却传 1000，被静默截断为 100 —— 与 1.2 叠加导致筛选结果不全。

### 1.6 侧边栏标签操作的过度刷新（中优先级）

`Sidebar.svelte` 中每一次标签操作（重命名/改色/移动/删除/加子标签）都调用 `librariesStore.reload()`，而 `reload()`（`libraries.svelte.ts`）并行发起 **6 个请求**（库列表、标签、标签类型、智能文件夹、总计数、收藏计数）。单个标签改名触发 6 次网络请求 + 全量重渲染，非常浪费。
- **建议**：标签操作后只局部更新标签数据（仅重新 `tagsApi.list()`），或后端返回更新后的标签直接替换 store 中对应项。

### 1.7 侧边栏派生计算的重复开销（低优先级）

- `filteredTags` 每次 navigation 变化都调用 `flattenTags(tags)` 重建数组；
- `groupedTags` / `manageTagList` 每次展开/折叠都重建 Map 并 walk 整棵标签树。
- 标签量大（数百～上千）时会有可感知延迟。可用 `Map` 缓存 + 增量更新优化。

---

## 二、UX 改进点

### 2.1 缺失全局搜索（高优先级 — 重大缺失功能）

后端 `list_media` 已支持 `search` 参数（标题/文件名 ILIKE），但前端**完全没有搜索框**：
- `FilterState`（`types.ts`）无 `search`/`q` 字段；
- `buildApiParams()` 不传 `search`；
- FilterBar 只有类型/分辨率/评分/时长/标签五个 chip。
- **建议**：在工具栏增加防抖搜索输入框，接入 `search` 参数。这是媒体库最核心的功能之一。

### 2.2 “继续观看 / 最近添加”导航名不副实（功能 bug）

`buildApiParams()` 只处理 `library`/`favorite`/`tag` 三种 navNode。侧边栏的“继续观看（continue）”和“最近添加（recent）”节点会落入默认分支，加载的是**全部媒体按 created_at 降序**，与“继续观看”语义完全不符：
- “继续观看”应按播放进度过滤（后端有 `is_watched`，或按 `playback_position > 0` 排序）；
- “最近添加”可保留 created_at 但应限制窗口（如近 30 天）或区别于“全部媒体”。
- **建议**：为 `continue` 节点增加进度排序/过滤；为 `recent` 限制时间范围。

### 2.3 筛选无结果时无空状态（中优先级）

当筛选条件导致 `items` 为空但非加载/错误/TV 场景时，代码直接渲染空的 `PosterWall`/`ListView`，页面呈现一片空白，用户不知道是“无结果”还是“加载中”。
- **建议**：增加“没有匹配的媒体，试试调整筛选条件”空状态 + “清除筛选”按钮。

### 2.4 翻页时无加载指示（中优先级）

骨架屏仅在 `items.length === 0` 时显示。翻到第 2 页时，旧内容仍可见，`loading=true` 但无任何视觉反馈（无顶部进度条、无骨架叠加）。用户点击下一页后页面“卡住”数秒无反应。
- **建议**：翻页时显示轻量加载指示（顶部进度条或半透明覆盖 + spinner），或保留旧数据 + 角标“加载中”。

### 2.5 视图/筛选/排序/页码未持久化（中优先级）

`view`/`filter`/`sort`/`page` 均为组件内 `$state`，既未写入 URL 也未存 localStorage：
- 刷新页面丢失所有上下文；
- 无法分享特定视图链接；
- 浏览器后退不恢复状态。
- **建议**：将关键状态同步到 URL query（`?view=list&sort=rating&page=2`），支持深链接与浏览器前进/后退。

### 2.6 无限滚动缺失（低优先级）

仅传统分页，无“加载更多”/无限滚动选项。对浏览大库的用户，频繁翻页体验割裂。可作为海报墙的可选模式。

### 2.7 批量操作缺失（中优先级 — 重要功能缺口）

列表/海报墙均无多选（checkbox / Shift 多选），无法批量打标签、删除、移动到其他库、收藏。媒体管理类应用这是高频需求。

### 2.8 删除/破坏性操作无撤销（低优先级）

标签删除有确认弹窗（好），但无“撤销”窗口。媒体删除后也无 toast 提示路径。建议增加 undo toast。

### 2.9 无快速预览/Lightbox（低优先级）

点击海报直接跳转详情页，无法在不离开列表的情况下快速预览。可考虑 hover 预览或点击弹出 lightbox。

### 2.10 过滤维度不全（低优先级）

后端支持 `is_watched`、`is_favorite`、`duration_min/max`、`resolution_min`、`rating_max` 等，前端 FilterBar 仅暴露部分。缺少“已看/未看”筛选（后端已支持）。

---

## 三、可访问性（A11y）缺口

### 3.1 FilterBar 下拉菜单完全不可键盘操作（高优先级）

`FilterBar.svelte` 的 chip 下拉是纯 `<div class="menu">` + `<button>`：
- 触发按钮无 `aria-haspopup`、`aria-expanded`；
- 菜单无 `role="listbox"`/`menu`，选项无 `role="option"`；
- 无方向键导航、无 Escape 关闭（仅靠 window click 关闭）、无焦点陷阱、关闭后焦点不归还触发器；
- 标签多选菜单同样不可键盘操作。
- **建议**：改用 combobox/listbox 模式，实现 `aria-expanded` + 方向键 + Enter + Escape + 焦点管理。

### 3.2 排序按钮缺少 ARIA 状态（中优先级）

`+page.svelte` 的排序按钮组（第 330-350 行）：
- 容器有 `role="group" aria-label="排序"`（好）；
- 但单个排序按钮**无 `aria-pressed`**（对比：视图切换按钮有 `aria-pressed`），仅靠视觉下划线表达选中；
- 无 `aria-sort` 标注。
- **建议**：为 `.sort-btn` 加 `aria-pressed={sort.field === o.field}`。

### 3.3 分页页码无 ARIA（低优先级）

页码按钮（第 511 行）无 `aria-current="page"`，屏幕阅读器无法识别当前页。上/下页箭头有 `aria-label`（好）。

### 3.4 侧边栏分组折叠无 `aria-expanded`（低优先级）

标签类型分组的折叠按钮（`.tag-group-head` / `.mt-group-head`）无 `aria-expanded`、`aria-controls`，屏幕阅读器不知展开状态。

### 3.5 折叠侧栏的 tooltip 仅 hover 触发（低优先级）

收起态用 CSS `:hover::after` 显示 `data-tip` tooltip，键盘焦点无法触发，且部分按钮仅有 `data-tip` 而无 `aria-label`。键盘用户无法获取图标含义。

### 3.6 右键菜单 / 颜色选择器不可键盘访问（低优先级）

- 右键菜单（`tagContextMenu`/`typeContextMenu`）通过 `oncontextmenu` 触发，菜单项虽是 `<button>`，但菜单无焦点管理、无 Escape 关闭（仅 backdrop 有 keydown）、打开后焦点不进入菜单；
- 颜色色板（`.color-swatch`）是 `<button>` 但无 `aria-label`（颜色值），屏幕阅读器读不出；
- 移动到类型选择器同理。

### 3.7 缺少全局键盘快捷键（低优先级）

无 `/` 聚焦搜索、`j/k` 上下导航、`g` 然后 `g` 回首页、方向键翻页等。媒体库应用通常提供快捷键提升效率。

### 3.8 图片 alt 文本不一致（低优先级）

PosterWall 的 img 有 `alt={media.title ?? media.filename}`（好），但 ListView 的 img `alt=""`（第 45/47 行），屏幕阅读器完全忽略缩略图。虽可接受（标题在相邻列），但建议统一策略。

---

## 四、样式系统评价

`app.css`（`g:\Code\vitoice_fin\frontend\src\app.css`）质量很高：
- 完整的设计令牌（颜色/圆角/阴影/字体/动效时长/缓动）；
- 完善的三态主题（深色默认 / `[data-theme='light']` / `prefers-color-scheme` 自动跟随），且支持强制切换；
- 全局 `:focus-visible` 焦点环、骨架 shimmer、glass 毛玻璃工具类；
- 字体通过 `@fontsource` 本地化（离线可用）。

**小问题**：浅色主题变量在三处重复定义（`[data-theme='light']`、`@media prefers-color-scheme`、部分在 `[data-theme='dark']` 段缺失阴影补丁）。建议抽成共享变量集减少维护成本，但不影响性能。

---

## 五、优先级总结

| 优先级 | 问题 | 类别 |
|--------|------|------|
| P0 | 客户端筛选全量拉取 1000 条 + 后端截断为 100（数据不全 + 性能） | 性能/正确性 |
| P0 | 缺失全局搜索（后端已支持，前端未接入） | UX 缺失 |
| P0 | 缩略图/海报端点无缓存头，媒体墙重复请求 | 性能 |
| P1 | PosterWall / ListView 无虚拟滚动 | 性能 |
| P1 | API 客户端无缓存/去重/重试 | 性能 |
| P1 | 图片无 onerror 回退 / 无尺寸变体 / 无 decoding=async | 性能/UX |
| P1 | FilterBar 下拉不可键盘操作 | A11y |
| P1 | “继续观看/最近添加”导航语义不正确 | 功能 bug |
| P2 | 筛选无结果无空状态 | UX |
| P2 | 翻页无加载指示 | UX |
| P2 | 视图/筛选/页码未持久化到 URL | UX |
| P2 | 排序按钮缺 aria-pressed | A11y |
| P2 | 侧边栏单标签操作触发 6 请求全量刷新 | 性能 |
| P2 | 无批量操作 | UX 缺失 |
| P3 | ILIKE 前导通配符全表扫描 | 性能 |
| P3 | 全局键盘快捷键缺失 | A11y/UX |
| P3 | 无限滚动 / 快速预览 / 撤销 | UX |
