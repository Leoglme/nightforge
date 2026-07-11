// NightForge desktop shell.
//
// On startup the app launches the bundled NightForge agent as a Tauri "sidecar" so that
// simply opening the executable starts everything needed (UI + local agent). The sidecar
// is a PyInstaller build of `agent/` placed in `src-tauri/binaries/` (see externalBin in
// tauri.conf.json). In debug/dev builds the sidecar may be absent — spawning is best-effort.

use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde::Serialize;
use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the spawned agent child and the last spawn error for diagnostics.
struct AgentProcess {
    child: Mutex<Option<CommandChild>>,
    last_error: Mutex<Option<String>>,
    /// When true, a sidecar exit must not trigger an automatic respawn (updates, manual stop).
    intentional_stop: Mutex<bool>,
}

impl AgentProcess {
    fn new() -> Self {
        Self {
            child: Mutex::new(None),
            last_error: Mutex::new(None),
            intentional_stop: Mutex::new(false),
        }
    }

    fn set_error(&self, message: Option<String>) {
        *self.last_error.lock().unwrap() = message;
    }

    fn is_running(&self) -> bool {
        self.child.lock().unwrap().is_some()
    }

    fn set_intentional_stop(&self, value: bool) {
        *self.intentional_stop.lock().unwrap() = value;
    }

    fn intentional_stop(&self) -> bool {
        *self.intentional_stop.lock().unwrap()
    }
}

/// Spawn the bundled agent sidecar.
fn spawn_agent(app: &tauri::AppHandle) -> Result<(), String> {
    let state = app
        .try_state::<AgentProcess>()
        .ok_or_else(|| "Agent runtime not initialized".to_string())?;

    match app.shell().sidecar("nightforge-agent") {
        Ok(command) => match command
            // Ignore stale machine tokens from the parent OS environment.
            .env("NF_AGENT_TOKEN", "")
            .env("NF_API_BASE", "")
            .spawn()
        {
            Ok((mut rx, child)) => {
                *state.child.lock().unwrap() = Some(child);
                state.set_error(None);
                println!("NightForge agent sidecar started");
                let app_handle = app.clone();
                thread::spawn(move || {
                    while let Ok(event) = rx.blocking_recv() {
                        if let CommandEvent::Terminated(payload) = event {
                            eprintln!("Agent sidecar exited: {payload:?}");
                            if let Some(state) = app_handle.try_state::<AgentProcess>() {
                                state.child.lock().unwrap().take();
                                if state.intentional_stop() {
                                    return;
                                }
                                thread::sleep(Duration::from_millis(800));
                                if let Err(err) = spawn_agent(&app_handle) {
                                    eprintln!("Agent sidecar respawn failed: {err}");
                                }
                            }
                            return;
                        }
                    }
                });
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

/// Stop the sidecar and wait until Windows releases the executable (required before updates).
fn stop_agent_sidecar_sync(state: &AgentProcess) {
    state.set_intentional_stop(true);
    let child = state.child.lock().unwrap().take();
    if let Some(child) = child {
        let _ = child.kill();
        // NSIS cannot overwrite nightforge-agent.exe while the process is still exiting.
        thread::sleep(Duration::from_millis(1200));
    }
    state.set_error(None);
    state.set_intentional_stop(false);
}

/// Stop the bundled agent so installers can replace `nightforge-agent.exe`.
#[tauri::command]
fn stop_agent_sidecar(app: tauri::AppHandle) -> Result<(), String> {
    let state = app
        .try_state::<AgentProcess>()
        .ok_or_else(|| "Agent runtime not initialized".to_string())?;
    stop_agent_sidecar_sync(&state);
    Ok(())
}

/// Kill the running sidecar (if any) and start a fresh agent process.
#[tauri::command]
fn restart_agent(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(state) = app.try_state::<AgentProcess>() {
        stop_agent_sidecar_sync(&state);
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

/// Return the last lines of ~/.nightforge/agent.log for in-app diagnostics.
#[tauri::command]
fn agent_log_tail(lines: Option<usize>) -> Result<String, String> {
    let keep = lines.unwrap_or(15).clamp(5, 80);
    let path = agent_log_path();
    if !path.exists() {
        return Ok("Aucun journal agent pour l'instant.".to_string());
    }

    let content = fs::read_to_string(&path).map_err(|err| format!("Impossible de lire agent.log: {err}"))?;
    let tail: Vec<&str> = content.lines().rev().take(keep).collect::<Vec<_>>().into_iter().rev().collect();
    Ok(tail.join("\n"))
}

fn agent_log_path() -> PathBuf {
    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .unwrap_or_else(|_| ".".to_string());
    PathBuf::from(home).join(".nightforge").join("agent.log")
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
        .invoke_handler(tauri::generate_handler![
            restart_agent,
            stop_agent_sidecar,
            agent_status,
            agent_log_tail
        ])
        .setup(|app| {
            if let Err(err) = spawn_agent(app.handle()) {
                eprintln!("Initial agent spawn failed: {err}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<AgentProcess>() {
                    stop_agent_sidecar_sync(&state);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
