// 无边框窗口（decorations:false）的窗口尺寸工具。
//
// 实测（2560x1440 屏 / 任务栏 48px）：系统 maximize 的客户区精确等于工作区
// 2560x1392（任务栏保持可见），且 WRY_WEBVIEW 客户区始终与窗口矩形一致——
// 既不存在"最大化盖住任务栏"，也不存在"客户区比窗口小"。因此贴底元素按
// 100% 视口排布即可，不需要任何遮挡补偿。

export interface WinSize {
  width: number;
  height: number;
}
export interface WinPos {
  x: number;
  y: number;
}

export interface WindowLike {
  minimize(): Promise<void>;
  close(): Promise<void>;
  toggleMaximize?(): Promise<void>;
  unmaximize?(): Promise<void>;
  isMaximized?(): Promise<boolean>;
  // Tauri v2 的 setSize/setPosition 参数为 LogicalSize|PhysicalSize|Size。
  // 这里只声明我们实际传入的结构化形状（{width,height} / {x,y}），真实窗口
  // 对象由调用方经 `as unknown as WindowLike` 适配（TopNav、player 页）。
  setSize?(size: { width: number; height: number }): Promise<void>;
  setPosition?(pos: { x: number; y: number }): Promise<void>;
  outerSize?(): Promise<WinSize>;
  outerPosition?(): Promise<WinPos>;
}

let prevSize: WinSize | null = null;
let prevPos: WinPos | null = null;
let workAreaMaximized = false;

/** 工作区尺寸（不含任务栏，CSS 逻辑像素；多屏时取主屏） */
export function workAreaSize(): WinSize {
  return {
    width: window.screen.availWidth,
    height: window.screen.availHeight,
  };
}

/** 逻辑像素 → 物理像素。Tauri setSize 把普通对象按物理像素解释，而
 *  availWidth/availHeight 是 CSS 逻辑像素；忽略 DPI 缩放会让窗口在高分屏
 *  下被放大超出工作区，底部盖到任务栏后面（"没真正最大化"）。 */
export function toPhysical(size: WinSize): WinSize {
  const scale = window.devicePixelRatio || 1;
  return { width: Math.round(size.width * scale), height: Math.round(size.height * scale) };
}

/** 手动最大化到工作区 / 还原。返回操作后的最大化状态。 */
export async function toggleWorkAreaMaximize(win: WindowLike): Promise<boolean> {
  if (!win || typeof win.setSize !== 'function' || typeof win.setPosition !== 'function') {
    // 降级：系统 toggleMaximize（浏览器/异常环境）
    await win?.toggleMaximize?.();
    return false;
  }
  // 用实际尺寸判断，而不是只看模块级标记：窗口可能被 Win+↑ / 双击等外部路径
  // 放大过，此时点"最大化"按钮应当还原而不是再次 setSize。
  const size = (await win.outerSize?.()) ?? null;
  const maximized = workAreaMaximized || (size ? sizeLooksMaximized(size) : false);
  if (maximized) {
    // 系统最大化状态下 setSize/setPosition 无效，先退回普通状态
    if (await win.isMaximized?.()) await win.unmaximize?.();
    if (prevSize && prevPos) {
      await win.setSize(prevSize);
      await win.setPosition(prevPos);
    }
    workAreaMaximized = false;
  } else {
    // 记录当前，放大到工作区
    prevSize = size;
    prevPos = (await win.outerPosition?.()) ?? null;
    // setSize 按物理像素解释：avail* 是逻辑像素，需换算（防 DPI 缩放溢出/遮挡任务栏）
    const { width, height } = toPhysical(workAreaSize());
    await win.setSize({ width, height });
    await win.setPosition({ x: 0, y: 0 });
    workAreaMaximized = true;
  }
  return workAreaMaximized;
}

/** 当前是否为"工作区最大化"状态（供 onResized 回调同步图标） */
export function isWorkAreaMaximized(): boolean {
  return workAreaMaximized;
}

/** 尺寸是否等于/超过工作区（供 onResized 回调同步图标）。
 *  outerSize() 返回物理像素，故与物理化后的工作区比较。 */
export function sizeLooksMaximized(size: WinSize): boolean {
  const { width, height } = toPhysical(workAreaSize());
  return size.width >= width - 2 && size.height >= height - 2;
}