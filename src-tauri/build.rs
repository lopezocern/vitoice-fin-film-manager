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
    tauri_build::build()
}
