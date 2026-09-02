// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::Manager;

/// 后端 sidecar 子进程句柄——退出时 kill，避免遗留 uvicorn 进程。
struct BackendChild(Mutex<Option<Child>>);

// 端口分离：开发态 8765（start-backend.ps1 / dev.ps1），生产打包 41011，
// 二者可同时运行互不冲突。前端生产构建经 .env.production 注入 41011。
#[cfg(debug_assertions)]
const BACKEND_PORT: u16 = 8765;
#[cfg(not(debug_assertions))]
const BACKEND_PORT: u16 = 41011;

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

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            #[cfg(debug_assertions)]
            if let Some(window) = app.get_webview_window("main") {
                window.open_devtools();
            }

            // 拉起后端 sidecar（若端口已被 vitoice 后端占用，sidecar 自身会幂等退出）。
            // 端口就绪后再显示主窗口（tauri.conf.json 里 visible: false），
            // 避免前端加载时后端未起导致首屏报错。
            let child = spawn_backend(app.handle());
            app.manage(BackendChild(Mutex::new(child)));

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
