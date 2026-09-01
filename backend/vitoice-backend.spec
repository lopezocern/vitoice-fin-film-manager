# -*- mode: python ; coding: utf-8 -*-
# vitoice-backend.spec — PyInstaller 打包配置
# 用途：把 FastAPI 后端打成独立可执行目录（onedir），随 Tauri 安装包分发。
# 构建（backend/ 目录下）：.venv/Scripts/python.exe -m PyInstaller --noconfirm --clean vitoice-backend.spec
# 产物：dist/vitoice-backend/vitoice-backend.exe（+ _internal/ 依赖目录）

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('curl_cffi')

# uvicorn 各可选组件（PyInstaller 静态分析对动态导入不敏感，显式声明）
hiddenimports += [
    'aiosqlite',  # SQLAlchemy 运行时按 dialect 字符串动态导入，静态分析抓不到
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.http.httptools_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.websockets_impl',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'anyio._backends._asyncio',
]

a = Analysis(
    ['run_server.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas + [('bin', 'bin')],  # ffmpeg/ffprobe → _internal/bin/（ffmpeg_utils 的 _BACKEND_DIR 解析目标）
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pytest', 'IPython'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='vitoice-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 保留控制台子系统；Tauri 侧用 CREATE_NO_WINDOW 隐藏
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='vitoice-backend',
)
