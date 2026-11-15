use std::path::PathBuf;

/// libmpv 运行时 DLL 清单（随 exe 分发，缺一个播放内核就起不来）。
const MPV_DLLS: [&str; 2] = ["libmpv-wrapper.dll", "libmpv-2.dll"];

/// 把 lib/ 下的 mpv DLL 复制到目标 profile 目录（exe 同级）。
///
/// tauri-plugin-libmpv 在运行期按 `exe 同级` → `exe/lib` 的顺序查找
/// libmpv-wrapper.dll，而 libmpv-wrapper 又要能加载同目录的 libmpv-2.dll。
/// 开发态（target/debug）与 release 都需要这一步，否则要么插件加载失败、
/// 要么依赖解析不到 libmpv-2.dll。
fn copy_mpv_dlls() {
    let manifest_dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap());
    // OUT_DIR = <target>/<profile>/build/<pkg>-<hash>/out → 上溯三级得到 <target>/<profile>
    let out_dir = PathBuf::from(std::env::var("OUT_DIR").unwrap());
    let Some(profile_dir) = out_dir.ancestors().nth(3) else {
        return;
    };

    for dll in MPV_DLLS {
        let src = manifest_dir.join("lib").join(dll);
        println!("cargo:rerun-if-changed=lib/{dll}");
        if !src.is_file() {
            println!("cargo:warning=缺少 {dll}（应位于 src-tauri/lib/），播放内核将不可用");
            continue;
        }
        let dst = profile_dir.join(dll);
        // 已是最新就不重写：避免占用中的 DLL 触发 "os error 32"（文件被占用）。
        if let (Ok(s), Ok(d)) = (src.metadata(), dst.metadata()) {
            if d.len() == s.len() {
                continue;
            }
        }
        if let Err(e) = std::fs::copy(&src, &dst) {
            println!("cargo:warning=复制 {dll} 到 {} 失败: {e}", dst.display());
        }
    }
}

fn main() {
    // Tauri embeds the Windows icon during resource compilation. Explicitly
    // track every bundled icon so changing artwork relinks the executable.
    for icon in [
        "icons/32x32.png",
        "icons/128x128.png",
        "icons/128x128@2x.png",
        "icons/icon.ico",
    ] {
        println!("cargo:rerun-if-changed={icon}");
    }
    copy_mpv_dlls();
    tauri_build::build()
}