// NightForge desktop shell.
//
// On startup the app launches the bundled NightForge agent as a Tauri "sidecar" so that
// simply opening the executable starts everything needed (UI + local agent). The sidecar
// is a PyInstaller build of `agent/` placed in `src-tauri/binaries/` (see externalBin in
// tauri.conf.json). In debug/dev builds the sidecar may be absent — spawning is best-effort.

use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Holds the spawned agent child so it can be killed when the app exits.
struct AgentProcess(std::sync::Mutex<Option<CommandChild>>);

/// Spawn the bundled agent sidecar. Best-effort: logs and continues on failure.
fn spawn_agent(app: &tauri::AppHandle) {
    match app.shell().sidecar("nightforge-agent") {
        Ok(command) => match command.spawn() {
            Ok((_rx, child)) => {
                if let Some(state) = app.try_state::<AgentProcess>() {
                    *state.0.lock().unwrap() = Some(child);
                }
                println!("NightForge agent sidecar started");
            }
            Err(err) => eprintln!("Failed to spawn agent sidecar: {err}"),
        },
        Err(err) => eprintln!("Agent sidecar not available: {err}"),
    }
}

/// Kill the running sidecar (if any) and start a fresh agent process.
#[tauri::command]
fn restart_agent(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(state) = app.try_state::<AgentProcess>() {
        if let Some(child) = state.0.lock().unwrap().take() {
            child
                .kill()
                .map_err(|err| format!("Failed to stop agent sidecar: {err}"))?;
        }
    }
    spawn_agent(&app);
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_os::init())
        .manage(AgentProcess(std::sync::Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![restart_agent])
        .setup(|app| {
            spawn_agent(app.handle());
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<AgentProcess>() {
                    if let Some(child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
