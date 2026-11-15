# 播放器 mpv 原生内核迁移 — 完整实施方案

> 目标版本：v3.1（桌面端播放内核替换）
> 前置：POC 已完成并验证通过（验证脚手架已在实施完成后移除）
> 状态：已实施完成 —— 静态校验通过（svelte-check 0 error / cargo check / 前端构建），dev 启动冒烟通过；待视觉验收

---

## 一、目标与范围

**要解决的问题**：WebView2 的 `<video>` 对 HEVC / AC3 / DTS / MKV 等编码支持不全，只能靠后端实时转码兜底，导致起播慢、CPU 高、拖动进度卡顿、部分片源直接播不了。播放是核心功能，需要根本解法。

**做法**：桌面端把解码内核从 WebView2 换成 **mpv（libmpv）**，由 mpv 自己解复用 + 硬解 + 渲染；WebView 退化为"控制层 + 覆盖层"。浏览器调试环境（`npm run dev`）继续走 `<video>` 回退。

**范围内**：
- 播放页（`/player`）全量迁移到内核抽象
- 迷你置顶小窗（`/mini-player`）迁移
- 字幕、音轨、截图/封面、上/下一个、倍速、逐帧、A-B 循环等既有能力对齐
- 打包分发（DLL 随包）与权限
- 全量回归验证

**范围外**：
- 不改动媒体库/详情页/管理页的交互与视觉（已完成的滚动定位、详情页箭头不在本次范围）
- 不改后端转码服务（保留，作为浏览器回退与网络转码兜底）
- 不做 mpv 的 OSC/内建 UI（全部关闭，控制层仍由 WebView 负责）

---

## 二、已验证结论（POC）

| 验证项 | 结论 | 证据 |
| --- | --- | --- |
| 插件集成 | `tauri-plugin-libmpv 0.3` 注册成功，`libmpv-wrapper.dll` 加载成功 | 运行日志 `Successfully loaded libmpv-wrapper` |
| HEVC 硬解 | 8bit（`hevc8.mp4`）与 10bit（`hevc10_ac3.mkv`）均走 d3d11va 硬解，画面正常 | POC 自动验证报告 |
| 音频 | AC3 解码正常，音画同步 | POC 报告 `audio-codec` |
| seek | `absolute` / `relative` 均生效，跳转后位置正确 | POC 报告 seek 列 |
| 画面可见 | 窗口 `background_color(Color(0,0,0,0))` + 页面背景透明 → mpv 画面可透出 | `.tmp-poc-video.png` |
| 层级关系 | WebView2 位于 mpv 子窗口**之上**，HTML 控制层/覆盖层可正常叠加 | POC 面板可点击、可见 |
| 截图 | `mpv_screenshot`（`screenshot-to-file` + 读回字节）可用 | Rust 命令已实现 |
| 多窗口约束 | 所有窗口必须共用同一 `additionalBrowserArgs`，否则 WebView2 环境创建失败（HRESULT 0x8007139F）且静默无提示 | `open_mpv_poc_window` 注释 |
| 窗口级透明 | **不可用**：`transparent(true)` 走 tao 软缓冲合成，本环境 `E_INVALIDARG` 建不出 webview | 已排除，改用 WebView 表面透明 |

**已落地代码**：

| 文件 | 状态 | 说明 |
| --- | --- | --- |
| `src-tauri/Cargo.toml` | 已完成 | 引入 `tauri-plugin-libmpv 0.3`、`tauri-plugin-log` |
| `src-tauri/src/main.rs` | 已完成（含 POC） | 主窗口透明底、`mpv_screenshot`、关闭时回收 mpv |
| `src-tauri/capabilities/default.json` | 已完成 | `main`/`mini`/`poc` 均已含 `libmpv:default` |
| `frontend/src/lib/player/mpv.ts` | 已完成 | IPC 薄封装（init/command/set_property/get_property/margin/listen） |
| `frontend/src/lib/player/kernel.svelte.ts` | 已完成主体 | `PlayerKernel` 双后端门面 |
| `frontend/src/routes/player/+page.svelte` | **部分接入** | 已建 kernel 实例、改 `streamUrl`/`needsTranscoding`、加 `stageEl`；**40+ 处仍直接操作 `videoEl`** |
| `frontend/src/routes/mini-player/+page.svelte` | 未迁移 | 仍是 `<video>` |

---

## 三、架构设计

### 3.1 宿主形态：主窗口内嵌（已定）

mpv 以 `wid` 子窗口嵌入**当前 Tauri 窗口客户区**，WebView 只负责叠加控制层与覆盖层。

- 不新建独立播放窗口（避免第二套窗口生命周期/焦点/全屏管理）
- 不启用窗口级 `transparent(true)`，只把 WebView2 默认底刷成 alpha=0
- 播放页之外的页面由 CSS 不透明背景铺满，观感不变

### 3.2 分层与真相源

```
player/+page.svelte          视图 / 快捷键 / 控制层 / 覆盖层
        │  只调用内核方法、只读内核状态（单向依赖）
        ▼
PlayerKernel (kernel.svelte.ts)    ← 播放状态唯一真相源
   ├── native = true   → mpv.ts → plugin:libmpv|*  （桌面端）
   └── native = false  → <video>                    （浏览器调试）
```

**硬性约束**：迁移完成后 `player/+page.svelte` 中不再出现 `videoEl.` 直读直写（fallback 元素仅经 `kernel.attachVideo()` 挂载）。

### 3.3 画面区域对齐（关键技术点）

mpv 子窗口铺满整个窗口客户区，而播放页画面只占"舞台"矩形。必须用 `set_video_margin_ratio` 把 mpv 画面内缩到舞台矩形。

- **计算**：以窗口客户区为基准，求舞台矩形的 `left/top/right/bottom` 四边边距占比（0~1）
- **触发时机**（缺一不可）：
  1. `onMount` 首次布局
  2. `ResizeObserver(stageEl)` — 控制条显隐、侧栏折叠导致舞台变化
  3. 窗口 `resize` / 全屏切换 / 退出全屏
  4. 路由切换进入播放页（元素挂载后）
  5. DPI 缩放变化（`devicePixelRatio` 变化）
- **背景**：播放页根容器必须透明，否则会盖住 mpv 画面；顶栏/侧栏/控制条保持不透明
- **容错**：比例未变化时跳过 IPC（避免 resize 抖动期间高频调用）

### 3.4 字幕策略（决策点，默认方案 A）

现状 `SubtitleTrack.svelte` 是 WebView 内的 HTML 覆盖层，由 `currentTime` 驱动。因 WebView 在 mpv 之上，覆盖层在 mpv 模式下**依然可用**。

- **方案 A（默认，推荐）**：保留 HTML 覆盖层
  - 同步依赖 mpv `time-pos` 的 `observe_property` 事件（高频推送），400ms 轮询仅作兜底
  - 优点：零改动复用现有字幕 UI（样式、位置、双字幕、字号）
  - 风险：IPC 事件延迟可能导致字幕轻微抖动
- **方案 B（兜底）**：改由 mpv 自己渲染（`sub-add <path>` + `sid` + `sub-visibility`）
  - 优点：与画面帧严格同步，随 letterbox/缩放正确对位
  - 代价：样式/位置控制改用 mpv 属性（`sub-font-size`/`sub-pos`/`sub-delay`）；后端字幕需落临时文件再 `sub-add`

**执行**：先按 A 落地，Phase 5 用真实字幕文件压测；若同步不达标再切 B。内核在 Phase 1 即预留 B 所需接口（`subAddFile`/`setSubVisible`/`setSubDelay`/`getTrackList`），切换成本可控。

### 3.5 网络播放策略

| 源类型 | native（mpv） | fallback（`<video>`） |
| --- | --- | --- |
| 本地文件 | 直接传绝对路径，**不转码** | 后端 HTTP 流（必要时 `?start=`） |
| HLS | mpv 原生解 HLS，**不加载 hls.js** | hls.js / 原生 HLS |
| direct 代理流 | 直接把代理 URL 交给 mpv | 直接赋 `src` |

### 3.6 图片

仍由 `<img>` 渲染，内核不参与。

---

## 四、分阶段实施

### Phase 1 — 内核收尾

文件：`frontend/src/lib/player/kernel.svelte.ts`、`frontend/src/lib/player/mpv.ts`

- **播放控制**：`play` / `pause` / `seek` / `stepFrame` / `setSpeed`（已有，补齐错误处理与幂等）
- **音量**：`setVolume` / `setMuted`（已有）；补 `setVolumeGain`
- **音轨/字幕轨**：`getTrackList()`、`setAudioTrack(id)`、`setSubVisible(bool)`、`subAddFile(path)`、`setSubDelay`、`setAudioDelay`
- **画面**：`setAspect`、`setVideoZoom`、`setPanScan`、`setVideoRotate`
- **画面调色**：`setProperty` 通用通道（亮度/对比度/饱和度/伽马）
- **循环**：`setAbLoop(a, b)` / `clearAbLoop()`
- **观测属性扩充**：`hwdec-current`、`video-codec`、`audio-codec`、`track-list`、`chapter-list`、`vo-configured`
- **事件扩充**：`file-loaded`（触发 loadedmetadata，比 duration 更可靠）、`onWaiting`/`onPlaying` 回调
- **通用读属性**：导出 `getProperty`（媒体信息面板用）
- **生命周期**：`destroy()` 幂等；Rust 侧窗口关闭时已 `destroy`，前端需容错不报错
- **验收**：`native=false` 分支在浏览器下可正常编译运行

### Phase 2 — 播放页迁移（工作量最大）

文件：`frontend/src/routes/player/+page.svelte`（约 3000 行，40+ 处 `videoEl` 引用）

替换清单：

| 现状 | 迁移后 |
| --- | --- |
| `bind:paused/duration/volume/muted/playbackRate` | 读 `kernel.*`，写走 `kernel.setX()` |
| `onTimeUpdate` / `onProgress` | `kernel.currentTime` / `kernel.buffered`（事件 + 轮询兜底） |
| `onLoadedMetadata` | `kernel.onLoadedMetadata` |
| `onEnded` | `kernel.onEnded`（`eof-reached` + `keep-open=yes`） |
| `onVideoError` | `kernel.onError` |
| `togglePlay` | `kernel.play()` / `kernel.pause()` |
| `seek`（含转码 `?start` 重载、`seekable` 判定、原生 seek 验证） | native 下直接 `kernel.seek(t)`；fallback 保留旧逻辑 |
| `setVolume` / `toggleMute` | `kernel.setVolume()` / `kernel.setMuted()` |
| 倍速菜单 | `kernel.setSpeed()` |
| 逐帧快捷键 | `kernel.stepFrame()` |
| 截图 / 设为封面 | `kernel.captureFrame()` |
| 上/下一个（`queueNav` 已有） | 逻辑不变，native 下 `kernel.load(新源)` |
| 网络 HLS / direct | 统一交给 mpv（见 3.5） |
| 卸载清理 | `kernel.destroy()` |

新增/调整：
- **舞台对齐**：`ResizeObserver(stageEl)` → `kernel.setMarginRatio(...)`（见 3.3）
- **播放页透明背景**：仅播放页根容器透明（不改 `AppShell`，避免影响其他页面）
- **转码相关 UI**：native 下不再出现"正在转码"提示与 `?start=` 重载路径
- **加载态**：`kernel.waiting` 驱动 spinner，替代原 `onwaiting`

保持不变：快捷键、进度条拖拽、字幕菜单、标签/片段面板、迷你窗入口、限制遮罩、导航箭头。

### Phase 3 — 迷你窗迁移

文件：`frontend/src/routes/mini-player/+page.svelte`、`src-tauri/src/main.rs`

- mpv 实例按窗口 label 绑定 → mini 页使用 `new PlayerKernel('mini')`
- **Rust 侧**：mini 窗口创建需带 `background_color(Color(0,0,0,0))` 与相同 `webview_browser_args`；若前端 `WebviewWindow` JS API 无法设置，改为 Rust 命令建窗
- 布局：标题条 + 舞台区（透明 + margin ratio 对齐）+ 控制条
- 进度：主窗暂停并落盘 → mini 读回续播（现有机制保留）
- 关闭：`saveProgress(true)` → 关窗 → 回收 `mini` 的 mpv 实例

### Phase 4 — 打包与分发

- **DLL 分发**（关键，已实现）：
  - `libmpv-wrapper.dll`（约 0.37 MB）+ `libmpv-2.dll`（约 95.8 MB）
  - 插件从 **exe 同级目录**加载：`exe_dir/libmpv-wrapper.dll`
  - 开发态：`build.rs` 的 `copy_mpv_dlls()` 把 `src-tauri/lib/*.dll` 复制到 `target/<profile>/`（大小相同则跳过，避免占用中的 DLL 触发 os error 32）
  - 生产态：`bundle.resources` 映射 `lib/*.dll` → exe 同级文件名，安装后与 exe 同目录，无需 `setup()` 再复制
  - 注意：`bundle.externalBin` 不适用（那是 sidecar）
- **体积**：安装包预计增至 ~150 MB+，需在发布说明中明确告知
- **权限**：`main`/`mini` 已含 `libmpv:default`；`mpv_screenshot` 无需额外权限
- **POC 清理**（已完成）：移除 `/poc-mpv` 路由、`VITOICE_MPV_POC` 开关、`open_mpv_poc_window`、`mpv_poc_clips` 命令，以及 capabilities 里的 `poc` 窗口条目
- **硬件解码开关**：现有 `video_hw_decode` 设置项在 native 下语义变化 → 映射到 mpv `hwdec`（`auto-safe` ↔ `no`），设置页文案同步更新

### Phase 5 — 回归验证

| 类别 | 用例 |
| --- | --- |
| 格式 | HEVC 8bit / 10bit、H.264、AC3 / DTS / EAC3、MKV / MP4 / MOV / TS / AVI |
| 交互 | 播放/暂停、拖动进度、倍速、逐帧、音量/静音、A-B 循环、上/下一个 |
| 字幕 | 外挂/内封、切换、显隐、延迟、样式、双字幕 |
| 音轨 | 多音轨切换 |
| 画面 | 窗口 resize、全屏切换、侧栏折叠、DPI 缩放、控制层显隐后舞台对齐 |
| 截图 | 截图、设为封面 |
| 迷你窗 | 开启、续播、关闭回收 mpv |
| 托盘 | 关闭到托盘音频停止、mpv 回收、再次唤起可继续 |
| 网络 | HLS、direct 代理流 |
| 多显示器 | 拖到副屏、跨屏 DPI 变化 |
| 回退 | 浏览器 `http://127.0.0.1:5173` 全流程可用 |

---

## 五、风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| mpv 子窗口铺满客户区 | 画面溢出到控制条/顶栏区域 | `set_video_margin_ratio` 对齐 + ResizeObserver 兜底 |
| 窗口 resize 期间比例抖动 | 高频 IPC 卡顿 | 比例未变化时跳过调用；必要时节流 |
| 播放页背景不透明 | mpv 画面被完全遮挡 | 播放页根容器强制透明；其他页面保持不透明 |
| 字幕 IPC 同步延迟 | 字幕抖动 | 先方案 A 压测；不达标切方案 B（接口已预留） |
| DLL 未随包 / 位置错误 | 生产环境 mpv 初始化失败 | `setup()` 早期复制到 exe 同级；安装包内做启动自检日志 |
| 安装包体积激增 | 分发体验 | 发布说明告知；评估 DLL 压缩 |
| 关闭到托盘时 mpv 未回收 | 后台仍有音频/资源泄漏 | 主窗口 `CloseRequested` 已 destroy；补前端 `destroy()` 兜底 |
| 多窗口 WebView2 参数不一致 | 新窗口静默创建失败 | 所有窗口统一走 `webview_browser_args()` |
| 迁移期间播放页回归 | 核心功能受损 | 分阶段提交，每阶段后跑 Phase 5 清单子集 |

---

## 六、验收标准

1. 桌面端播放 HEVC 10bit + AC3 的 MKV：起播 ≤2s、无转码、拖动进度 ≤500ms 出画面、音画同步
2. `player/+page.svelte` 中不再存在 `videoEl.` 直接读写（fallback 挂载除外）
3. 窗口 resize / 全屏 / 侧栏折叠后，画面始终精确落在舞台矩形内，无溢出、无错位
4. 字幕、音轨、截图、封面、倍速、逐帧、上/下一个、迷你窗功能与迁移前行为一致
5. 关闭到托盘后音频停止、mpv 实例回收；重新唤起可继续播放
6. 生产安装包在无开发环境的机器上可正常初始化 mpv 并播放
7. 浏览器 `npm run dev` 下 `<video>` 回退全流程可用