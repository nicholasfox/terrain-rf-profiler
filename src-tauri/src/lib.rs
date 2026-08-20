use std::fs;
use std::path::PathBuf;

#[tauri::command]
fn get_key() -> String {
    let exe_path = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("."));
    let exe_dir = exe_path.parent().unwrap_or_else(|| std::path::Path::new("."));
    let key_path = exe_dir.join("key.txt");
    fs::read_to_string(&key_path).unwrap_or_default()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_key])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
