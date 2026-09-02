// 无边框窗口（decorations:false）下，系统 maximize() 会覆盖任务栏。
// 本工具用"手动最大化到工作区"替代：记录原尺寸/位置，setSize 到
// screen.availWidth/availHeight（不含任务栏的工作区），setPosition(0,0)。
// 还原时恢复原尺寸/位置。

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

/** 工作区尺寸（不含任务栏，逻辑像素；多屏时取主屏） */
export function workAreaSize(): WinSize {
  return {
    width: window.screen.availWidth,
    height: window.screen.availHeight,
  };
}

/** 手动最大化到工作区 / 还原。返回操作后的最大化状态。 */
export async function toggleWorkAreaMaximize(win: WindowLike): Promise<boolean> {
  if (!win || typeof win.setSize !== 'function' || typeof win.setPosition !== 'function') {
    // 降级：系统 toggleMaximize（浏览器/异常环境）
    await win?.toggleMaximize?.();
    return false;
  }
  if (workAreaMaximized) {
    // 还原
    if (prevSize && prevPos) {
      await win.setSize(prevSize);
      await win.setPosition(prevPos);
    } else {
      await win.unmaximize?.();
    }
    workAreaMaximized = false;
  } else {
    // 记录当前，放大到工作区
    prevSize = (await win.outerSize?.()) ?? null;
    prevPos = (await win.outerPosition?.()) ?? null;
    const { width, height } = workAreaSize();
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

/** 尺寸是否等于/超过工作区（判断窗口是否被放大到铺满工作区） */
export function sizeLooksMaximized(size: WinSize): boolean {
  const { width, height } = workAreaSize();
  return size.width >= width - 2 && size.height >= height - 2;
}
