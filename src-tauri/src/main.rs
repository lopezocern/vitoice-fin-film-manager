// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    window::Color,
    Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};
use tauri_plugin_libmpv::MpvExt;

/// 后端 sidecar 子进程句柄——退出时 kill，避免遗留 uvicorn 进程。
struct BackendChild(Mutex<Option<Child>>);

// 端口分离：开发态 8765（start-backend.ps1 / dev.ps1），生产打包 41011，
// 二者可同时运行互不冲突。前端生产构建经 .env.production 注入 41011。
#[cfg(debug_assertions)]
const BACKEND_PORT: u16 = 8765;
#[cfg(not(debug_assertions))]
const BACKEND_PORT: u16 = 41011;

// ---- 硬件视频解码开关（本地持久化，供窗口创建时选择浏览器参数）----
// 主窗口在 setup() 里按该开关决定 additionalBrowserArgs：关硬件视频解码时追加
// --disable-accelerated-video-decode（GPU 合成保留，仅视频解码回落 CPU）。
// 存到 app_config_dir（%APPDATA%/com.vitoice.app/），前端设置页经 invoke 读写，
// 修改后需重启应用生效。
const HW_DECODE_FILE: &str = "video_hw_decode.pref";

fn hw_decode_pref_path(app: &tauri::AppHandle) -> Option<std::path::PathBuf> {
    app.path().app_config_dir().ok().map(|d| d.join(HW_DECODE_FILE))
}

fn hw_decode_enabled(app: &tauri::AppHandle) -> bool {
    let Some(p) = hw_decode_pref_path(app) else {
        return true;
    };
    match std::fs::read_to_string(p) {
        Ok(s) => {
            let s = s.trim();
            s != "0" && !s.eq_ignore_ascii_case("off") && !s.eq_ignore_ascii_case("false")
        }
        Err(_) => true,
    }
}

/// 随开关拼接 WebView2 浏览器参数。保留 wry 默认的三个 disable-features。
fn webview_browser_args(hw_decode: bool) -> String {
    let mut args =
        "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection,AudioServiceOutOfProcess"
            .to_string();
    // AudioServiceOutOfProcess 让 WebView2 音频服务跑进宿主进程（vitoice.exe），
    // Windows 音量合成器/声音设置才能归属到 vitoice 而非 "Microsoft Edge WebView2"。
    if !hw_decode {
        args.push_str(" --disable-accelerated-video-decode");
    }
    args
}

#[tauri::command]
fn get_video_hw_decode(app: tauri::AppHandle) -> bool {
    hw_decode_enabled(&app)
}

#[tauri::command]
fn set_video_hw_decode(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    std::fs::write(dir.join(HW_DECODE_FILE), if enabled { "1" } else { "0" })
        .map_err(|e| e.to_string())
}

/// 定位打包在资源目录里的后端 sidecar exe。
/// 兼容两种资源映射布局（Tauri 版本差异），都指向 PyInstaller onedir 产物：
///   $RESOURCE/resources/backend/vitoice-backend/vitoice-backend.exe
///   $RESOURCE/backend/vitoice-backend/vitoice-backend.exe
/// 开发态（资源目录无 sidecar）返回 None——由外部 start-backend.ps1 提供后端。
fn backend_exe(app: &tauri::AppHandle) -> Option<std::path::PathBuf> {
    let res_dir = app.path().resource_dir().ok()?;
    let candidates = [
        res_dir.join("resources").join("backend").join("vitoice-backend").join("vitoice-backend.exe"),
        res_dir.join("backend").join("vitoice-backend").join("vitoice-backend.exe"),
    ];
    candidates.into_iter().find(|p| p.is_file())
}

/// 启动后端 sidecar（隐藏控制台窗口，stdout/stderr 落日志文件）。
fn spawn_backend(app: &tauri::AppHandle) -> Option<Child> {
    let exe = backend_exe(app)?;
    let workdir = exe.parent()?.to_path_buf();

    let mut cmd = Command::new(&exe);
    cmd.current_dir(&workdir);
    // 显式传端口，覆盖 sidecar 默认值（双保险：exe 默认也是 41011）
    cmd.env("VITOICE_PORT", BACKEND_PORT.to_string());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    // 后端日志：应用日志目录（%APPDATA%/com.vitoice.app/logs/backend.log）
    if let Ok(log_dir) = app.path().app_log_dir() {
        if std::fs::create_dir_all(&log_dir).is_ok() {
            if let Ok(file) = std::fs::File::create(log_dir.join("backend.log")) {
                let clone = file.try_clone().ok()?;
                cmd.stdout(Stdio::from(file));
                cmd.stderr(Stdio::from(clone));
            }
        }
    }

    match cmd.spawn() {
        Ok(child) => {
            println!("[vitoice] backend sidecar spawned: {}", exe.display());
            Some(child)
        }
        Err(e) => {
            eprintln!("[vitoice] failed to spawn backend sidecar: {e}");
            None
        }
    }
}

/// TCP 轮询等待后端端口就绪（后端 /health 在绑定后立即可达）。
fn wait_port_ready(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

/// 唤起主窗口：从托盘/二次启动时恢复显示并聚焦。
/// 窗口可能处于隐藏（关闭到托盘）或最小化状态，两者都要还原。
fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// 创建系统托盘图标与右键菜单（显示主窗口 / 退出）。
/// 左键单击托盘直接唤起主窗口（不弹菜单），右键弹菜单。
fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let show_item = MenuItem::with_id(app, "show", "显示主窗口", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "退出 vitoice", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_item, &quit_item])?;

    let mut builder = TrayIconBuilder::with_id("main-tray")
        .tooltip("vitoice")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main_window(app),
            // 走 app.exit：触发 RunEvent::Exit，从而回收后端 sidecar 子进程
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });

    if let Some(icon) = app.default_window_icon().cloned() {
        builder = builder.icon(icon);
    }

    builder.build(app)?;
    Ok(())
}

// ==================== libmpv 原生播放内核（mpv 子窗口） ====================
// mpv 以 wid 模式作为子窗口嵌入，WebView 只负责叠加控制层；画面区必须能透出
// 下层 mpv 子窗口，因此相关窗口一律把 WebView2 底刷成透明（alpha=0）。

/// 迷你置顶小窗的窗口 label（capabilities 里已登记，mpv 实例也按它绑定）。
const MINI_WINDOW: &str = "mini";

/// 抓取 mpv 当前帧为 PNG 并返回原始字节。
/// mpv 的 screenshot-to-file 只写磁盘，这里落临时文件后读回删除，
/// 前端拿 Blob 直接走保存/剪贴板，无需再申请一遍 fs 读权限。
#[tauri::command]
async fn mpv_screenshot(
    app: tauri::AppHandle,
    window_label: String,
    mode: Option<String>,
) -> Result<tauri::ipc::Response, String> {
    tauri::async_runtime::spawn_blocking(move || -> Result<Vec<u8>, String> {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        let path = std::env::temp_dir().join(format!("vitoice-shot-{}-{stamp}.png", std::process::id()));
        let args = vec![
            serde_json::Value::String(path.to_string_lossy().into_owned()),
            serde_json::Value::String(mode.unwrap_or_else(|| "video".to_string())),
        ];
        app.mpv()
            .command("screenshot-to-file", &args, &window_label)
            .map_err(|e| format!("mpv screenshot 失败: {e}"))?;
        // 命令同步返回，但文件落盘可能略滞后，短暂重试。
        let mut data = None;
        for _ in 0..20 {
            if let Ok(bytes) = std::fs::read(&path) {
                data = Some(bytes);
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        let _ = std::fs::remove_file(&path);
        data.ok_or_else(|| "mpv 未生成截图文件".to_string())
    })
    .await
    .map_err(|e| e.to_string())?
    .map(tauri::ipc::Response::new)
}

/// 把字幕文本写成临时文件，返回绝对路径。
/// mpv 的 `sub-add` 只接受路径/URL，而字幕内容可能来自后端端点（外挂文件、内封轨
/// 抽取），因此在 Rust 侧落盘再交给 mpv，前端无需申请 fs 写权限，也不受 fs scope 限制。
#[tauri::command]
async fn mpv_write_subtitle(text: String, ext: Option<String>) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || -> Result<String, String> {
        let dir = std::env::temp_dir().join("vitoice-subs");
        std::fs::create_dir_all(&dir).map_err(|e| format!("创建字幕临时目录失败: {e}"))?;
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        let ext = ext
            .map(|e| e.trim_start_matches('.').to_ascii_lowercase())
            .filter(|e| !e.is_empty() && e.len() <= 8)
            .unwrap_or_else(|| "srt".to_string());
        let path = dir.join(format!("sub-{}-{stamp}.{ext}", std::process::id()));
        std::fs::write(&path, text.as_bytes()).map_err(|e| format!("写入字幕失败: {e}"))?;
        Ok(path.to_string_lossy().into_owned())
    })
    .await
    .map_err(|e| e.to_string())?
}

/// 打开迷你置顶小窗（label=mini）。
///
/// 必须由 Rust 侧建窗：WebView2 的环境参数（additionalBrowserArgs）在主窗口创建时
/// 就已固定，用前端 `new WebviewWindow()` 建窗会退回 wry 默认参数，与主窗口不一致
/// 时环境创建直接失败（HRESULT 0x8007139F，且只 log::error! 不外抛，表现为窗口
/// 静默不出现）。这里复用同一套参数，并把 WebView2 底刷成透明，让下层 mpv 子窗口
/// 的画面能透出来。
#[tauri::command]
async fn open_mini_window(app: tauri::AppHandle, media_id: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
        // 已存在就先收掉：先显式销毁 mpv，否则插件自带的 CloseRequested 钩子会
        // prevent_close 再异步关窗，与随后同 label 的建窗竞态（label 重复 → 建窗失败）。
        if let Some(existing) = app.get_webview_window(MINI_WINDOW) {
            let _ = app.mpv().destroy(MINI_WINDOW);
            let _ = existing.close();
            for _ in 0..40 {
                if app.get_webview_window(MINI_WINDOW).is_none() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
        }

        let args = webview_browser_args(hw_decode_enabled(&app));
        WebviewWindowBuilder::new(
            &app,
            MINI_WINDOW,
            WebviewUrl::App(format!("mini-player?id={media_id}").into()),
        )
        .title("vitoice 迷你播放")
        .inner_size(480.0, 270.0)
        .min_inner_size(320.0, 180.0)
        .resizable(true)
        .always_on_top(true)
        .decorations(false)
        .skip_taskbar(true)
        // alpha=0：WebView 只叠控制层，画面区透出下层 mpv 子窗口。
        // 与主窗口同理，不能用 transparent(true)。
        .background_color(Color(0, 0, 0, 0))
        .additional_browser_args(&args)
        .build()
        .map_err(|e| e.to_string())?;
        Ok(())
    })
    .await
    .map_err(|e| e.to_string())?
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::new()
                .level(log::LevelFilter::Info)
                .build(),
        )
        // 单实例必须最先注册：第二次启动时回调里唤起已有窗口，新进程随即退出。
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_opener::init())
        // 原生播放内核（libmpv）：把 mpv 作为子窗口嵌进 Tauri 窗口，
        // 由 mpv 自己解码，绕开 WebView2 对 HEVC/AC3/DTS/MKV 的限制。
        .plugin(tauri_plugin_libmpv::init())
        .on_window_event(|window, event| {
            // 关闭主窗口 = 最小化到托盘常驻，不退出进程；真正退出走托盘菜单"退出"。
            // 仅拦截 main：迷你播放窗（label=mini）的"关闭小窗"必须能正常关掉。
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    // 主动回收 mpv：插件自带的 CloseRequested 钩子在实例存在时会抢先
                    // destroy 并尝试关窗，与这里的 prevent_close 互相踩踏；先销毁可让
                    // 钩子直接跳过，同时保证隐藏到托盘后音频停止。
                    let _ = window.app_handle().mpv().destroy(window.label());
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            // 按硬件解码开关动态创建主窗口（对应 tauri.conf.json 里原先的 windows[0]，
            // 字段已随窗口迁移到此处，避免 WebView2 参数在编译期写死）。
            let args = webview_browser_args(hw_decode_enabled(app.handle()));
            WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("vitoice")
                .inner_size(1440.0, 900.0)
                .min_inner_size(1024.0, 680.0)
                .resizable(true)
                .fullscreen(false)
                .center()
                .decorations(false)
                // alpha=0：只把 WebView2 默认底刷成透明，播放页舞台区才能透出下层
                // mpv 子窗口的画面；其余页面由 CSS 自带的不透明背景铺满，观感不变。
                // 不能用 transparent(true)——那会走 tao 软缓冲合成，本环境建不出 webview。
                .background_color(Color(0, 0, 0, 0))
                .visible(false)
                .additional_browser_args(&args)
                .build()?;

            #[cfg(debug_assertions)]
            if let Some(window) = app.get_webview_window("main") {
                window.open_devtools();
            }

            // 拉起后端 sidecar（若端口已被 vitoice 后端占用，sidecar 自身会幂等退出）。
            // 端口就绪后再显示主窗口（上方 visible: false），
            // 避免前端加载时后端未起导致首屏报错。
            let child = spawn_backend(app.handle());
            app.manage(BackendChild(Mutex::new(child)));

            // 托盘常驻图标：关闭窗口后仍可从托盘唤起
            build_tray(app.handle())?;

            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let ready = wait_port_ready(BACKEND_PORT, Duration::from_secs(15));
                if !ready {
                    eprintln!(
                        "[vitoice] backend not ready on port {BACKEND_PORT} after 15s — showing window anyway"
                    );
                }
                if let Some(window) = handle.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_video_hw_decode,
            set_video_hw_decode,
            mpv_screenshot,
            mpv_write_subtitle,
            open_mini_window
        ])
        .build(tauri::generate_context!())
        .expect("error while building vitoice application");

    app.run(|app_handle, event| {
        // 应用退出时回收后端进程
        if let tauri::RunEvent::Exit = event {
            if let Some(state) = app_handle.try_state::<BackendChild>() {
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(child) = guard.as_mut() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        }
    });
}