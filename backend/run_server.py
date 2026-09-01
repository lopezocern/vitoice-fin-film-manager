"""vitoice backend sidecar entry（PyInstaller 打包入口）。

启动策略（幂等）：
1. 若 127.0.0.1:{port}/health 已有 vitoice 后端在跑 → 静默退出，
   避免与手动 start-backend.ps1 / 另一应用实例双绑端口。
2. 否则以 uvicorn 启动 FastAPI app（默认 prod 数据根 ~/.vitoice）。

Tauri 壳在应用启动时拉起本进程、退出时回收；
Windows 下以 CREATE_NO_WINDOW 启动，控制台不可见。
"""
import os
import sys


def _health_ok(port: int, timeout: float = 1.0) -> bool:
    """探测端口上是否已有 vitoice 后端（而非任意占用者）。"""
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=timeout
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> None:
    # 生产默认 41011（与开发态 8765 分离，二者可共存）；
    # Tauri 壳 spawn 时也会显式传 VITOICE_PORT 覆盖。
    port = int(os.environ.get("VITOICE_PORT", "41011"))

    if _health_ok(port):
        print(
            f"[vitoice-backend] port {port} already serving vitoice, exiting.",
            flush=True,
        )
        return

    import uvicorn

    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
