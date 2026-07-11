// NightForge desktop shell.
//
// On startup the app launches the bundled NightForge agent as a Tauri "sidecar" so that
// simply opening the executable starts everything needed (UI + local agent). The sidecar
// is a PyInstaller build of `agent/` placed in `src-tauri/binaries/` (see externalBin in
// tauri.conf.json). In debug/dev builds the sidecar may be absent — spawning is best-effort.

use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde::Serialize;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Holds the spawned agent child and the last spawn error for diagnostics.
struct AgentProcess {
    child: Mutex<Option<CommandChild>>,
    last_error: Mutex<Option<String>>,
}

impl AgentProcess {
    fn new() -> Self {
        Self {
            child: Mutex::new(None),
            last_error: Mutex::new(None),
        }
    }

    fn set_error(&self, message: Option<String>) {
        *self.last_error.lock().unwrap() = message;
    }

    fn is_running(&self) -> bool {
        self.child.lock().unwrap().is_some()
    }
}

/// Spawn the bundled agent sidecar.
fn spawn_agent(app: &tauri::AppHandle) -> Result<(), String> {
    let state = app
        .try_state::<AgentProcess>()
        .ok_or_else(|| "Agent runtime not initialized".to_string())?;

    match app.shell().sidecar("nightforge-agent") {
        Ok(command) => match command.spawn() {
            Ok((_rx, child)) => {
                *state.child.lock().unwrap() = Some(child);
                state.set_error(None);
                println!("NightForge agent sidecar started");
                Ok(())
            }
            Err(err) => {
                let message = format!("Failed to spawn agent sidecar: {err}");
                state.set_error(Some(message.clone()));
                eprintln!("{message}");
                Err(message)
            }
        },
        Err(err) => {
            let message = format!("Agent sidecar not available: {err}");
            state.set_error(Some(message.clone()));
            eprintln!("{message}");
            Err(message)
        }
    }
}

/// Kill the running sidecar without blocking the UI thread (Windows kill can hang).
fn kill_agent_async(state: &AgentProcess) {
    let child = state.child.lock().unwrap().take();
    if let Some(child) = child {
        thread::spawn(move || {
            let _ = child.kill();
        });
    }
}

/// Kill the running sidecar (if any) and start a fresh agent process.
#[tauri::command]
fn restart_agent(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(state) = app.try_state::<AgentProcess>() {
        kill_agent_async(&state);
        thread::sleep(Duration::from_millis(400));
    }
    spawn_agent(&app)
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AgentStatus {
    sidecar_running: bool,
    last_error: Option<String>,
}

/// Expose local agent sidecar status for the Machines screen.
#[tauri::command]
fn agent_status(app: tauri::AppHandle) -> AgentStatus {
    if let Some(state) = app.try_state::<AgentProcess>() {
        AgentStatus {
            sidecar_running: state.is_running(),
            last_error: state.last_error.lock().unwrap().clone(),
        }
    } else {
        AgentStatus {
            sidecar_running: false,
            last_error: Some("Agent runtime not initialized".to_string()),
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_os::init())
        .manage(AgentProcess::new())
        .invoke_handler(tauri::generate_handler![restart_agent, agent_status])
        .setup(|app| {
            if let Err(err) = spawn_agent(app.handle()) {
                eprintln!("Initial agent spawn failed: {err}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<AgentProcess>() {
                    kill_agent_async(&state);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
