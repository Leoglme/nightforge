// NightForge desktop shell.
//
// On startup the app launches the bundled NightForge agent as a Tauri "sidecar" so that
// simply opening the executable starts everything needed (UI + local agent). The sidecar
// is a PyInstaller build of `agent/` placed in `src-tauri/binaries/` (see externalBin in
// tauri.conf.json). In debug/dev builds the sidecar may be absent — spawning is best-effort.

use std::fs;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde::Serialize;
use tauri::Manager;
#[cfg(desktop)]
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Windows: hide console windows spawned for taskkill/tasklist.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Holds the spawned agent child and the last spawn error for diagnostics.
struct AgentProcess {
    child: Mutex<Option<CommandChild>>,
    /// Incremented on every spawn/stop so a stale watchdog cannot clear a newer child
    /// or respawn a second agent after a restart.
    generation: AtomicU64,
    last_error: Mutex<Option<String>>,
    /// When true, a sidecar exit must not trigger an automatic respawn (updates, manual stop).
    intentional_stop: Mutex<bool>,
    /// Blocks the watchdog respawn during desktop updates (even if intentional_stop races).
    block_respawn: Mutex<bool>,
    /// App is quitting — never respawn the agent after this is set.
    shutting_down: Mutex<bool>,
}

impl AgentProcess {
    fn new() -> Self {
        Self {
            child: Mutex::new(None),
            generation: AtomicU64::new(0),
            last_error: Mutex::new(None),
            intentional_stop: Mutex::new(false),
            block_respawn: Mutex::new(false),
            shutting_down: Mutex::new(false),
        }
    }

    fn bump_generation(&self) -> u64 {
        self.generation.fetch_add(1, Ordering::SeqCst) + 1
    }

    fn current_generation(&self) -> u64 {
        self.generation.load(Ordering::SeqCst)
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

    fn set_block_respawn(&self, value: bool) {
        *self.block_respawn.lock().unwrap() = value;
    }

    fn block_respawn(&self) -> bool {
        *self.block_respawn.lock().unwrap()
    }

    fn set_shutting_down(&self, value: bool) {
        *self.shutting_down.lock().unwrap() = value;
    }

    fn shutting_down(&self) -> bool {
        *self.shutting_down.lock().unwrap()
    }
}

/// Spawn the bundled agent sidecar.
///
/// In `tauri:dev` (`cfg(dev)`), the Python agent is already started by
/// `scripts/dev-desktop.mjs` — skip the sidecar to avoid a double agent / stub spawn.
fn spawn_agent(app: &tauri::AppHandle) -> Result<(), String> {
    if cfg!(dev) {
        println!("NightForge agent sidecar skipped in tauri:dev (Python agent via concurrently)");
        return Ok(());
    }

    let state = app
        .try_state::<AgentProcess>()
        .ok_or_else(|| "Agent runtime not initialized".to_string())?;

    if state.block_respawn() || state.shutting_down() {
        return Ok(());
    }

    // Never stack a second sidecar on top of a tracked one (leaks orphans + races online).
    if state.is_running() {
        println!("NightForge agent sidecar already running — skip spawn");
        return Ok(());
    }

    if agent_processes_running() {
        kill_all_agent_processes();
    }

    match app.shell().sidecar("nightforge-agent") {
        Ok(command) => match command
            // Ignore stale machine tokens from the parent OS environment.
            .env("NF_AGENT_TOKEN", "")
            .env("NF_API_BASE", "")
            .spawn()
        {
            Ok((mut rx, child)) => {
                let generation = state.bump_generation();
                *state.child.lock().unwrap() = Some(child);
                state.set_error(None);
                println!("NightForge agent sidecar started (generation {generation})");
                let app_handle = app.clone();
                thread::spawn(move || {
                    while let Some(event) = rx.blocking_recv() {
                        if let CommandEvent::Terminated(payload) = event {
                            eprintln!("Agent sidecar exited: {payload:?}");
                            if let Some(state) = app_handle.try_state::<AgentProcess>() {
                                // Stale watchdog after restart: do not touch the newer child.
                                if state.current_generation() != generation {
                                    return;
                                }
                                state.child.lock().unwrap().take();
                                if state.intentional_stop()
                                    || state.block_respawn()
                                    || state.shutting_down()
                                {
                                    return;
                                }
                                thread::sleep(Duration::from_millis(800));
                                if state.current_generation() != generation
                                    || state.intentional_stop()
                                    || state.block_respawn()
                                    || state.shutting_down()
                                {
                                    return;
                                }
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

/// Whether any nightforge-agent.exe process is still running (Windows only).
fn agent_processes_running() -> bool {
    #[cfg(target_os = "windows")]
    {
        let output = Command::new("tasklist")
            .args(["/FI", "IMAGENAME eq nightforge-agent.exe", "/NH"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
        if let Ok(out) = output {
            let stdout = String::from_utf8_lossy(&out.stdout);
            return stdout.to_ascii_lowercase().contains("nightforge-agent.exe");
        }
        return false;
    }
    #[cfg(not(target_os = "windows"))]
    {
        false
    }
}

/// Force-kill every nightforge-agent.exe process tree (/T).
fn taskkill_agents_once() {
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("taskkill")
            .args(["/F", "/T", "/IM", "nightforge-agent.exe"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }
}

/// Kill all agent processes and poll until Windows releases nightforge-agent.exe.
fn kill_all_agent_processes() {
    for attempt in 0..10 {
        if attempt > 0 {
            thread::sleep(Duration::from_millis(500));
        }
        taskkill_agents_once();
        if !agent_processes_running() {
            break;
        }
    }
    thread::sleep(Duration::from_millis(1000));
}

/// How to stop the agent sidecar.
#[derive(Clone, Copy, PartialEq, Eq)]
enum StopMode {
    /// Temporary stop (restart will clear flags).
    Soft,
    /// Desktop update — block respawn until restart clears it.
    Update,
    /// App quitting — kill process tree and never respawn.
    Shutdown,
}

/// Stop the sidecar. On Update/Shutdown, force-kill the process tree with taskkill /T.
/// Soft / Restart also reap orphan ``nightforge-agent.exe`` processes: a soft kill of
/// only the tracked child left duplicates holding the singleton mutex, so the freshly
/// spawned sidecar exited immediately while the stale orphan kept the machine flaky.
fn stop_agent_sidecar_sync(state: &AgentProcess, mode: StopMode) {
    state.set_intentional_stop(true);
    // Invalidate every watchdog so a Terminated event from the process we are about
    // to kill cannot clear a child spawned by a concurrent restart.
    state.bump_generation();
    if mode == StopMode::Update || mode == StopMode::Shutdown {
        state.set_block_respawn(true);
    }
    if mode == StopMode::Shutdown {
        state.set_shutting_down(true);
    }

    let child = state.child.lock().unwrap().take();
    if let Some(child) = child {
        // Soft kill first so the agent can flush quotas (SIGTERM / kill without /F).
        let _ = child.kill();
        let grace = if mode == StopMode::Shutdown {
            Duration::from_millis(2000)
        } else {
            Duration::from_millis(800)
        };
        thread::sleep(grace);
    }

    // Always reap orphans. Duplicate agents share one log file, hammer Claude OAuth
    // (429 storms), and race the control-plane online flag.
    kill_all_agent_processes();

    state.set_error(None);
    // Soft stop only: allow a later restart/spawn. Never clear flags on shutdown.
    if mode == StopMode::Soft {
        state.set_intentional_stop(false);
    }
}

/// Stop the bundled agent so installers can replace `nightforge-agent.exe`.
#[tauri::command]
fn stop_agent_sidecar(app: tauri::AppHandle) -> Result<(), String> {
    let state = app
        .try_state::<AgentProcess>()
        .ok_or_else(|| "Agent runtime not initialized".to_string())?;
    stop_agent_sidecar_sync(&state, StopMode::Soft);
    Ok(())
}

/// Prepare for a desktop update: block respawn, kill all agent processes, verify they exited.
#[tauri::command]
fn prepare_desktop_update(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(state) = app.try_state::<AgentProcess>() {
        stop_agent_sidecar_sync(&state, StopMode::Update);
    } else {
        kill_all_agent_processes();
    }

    if agent_processes_running() {
        return Err(
            "nightforge-agent.exe est encore actif. Ferme-le dans le Gestionnaire des taches puis reessaie."
                .to_string(),
        );
    }
    Ok(())
}

/// Kill the running sidecar (if any) and start a fresh agent process.
#[tauri::command]
fn restart_agent(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(state) = app.try_state::<AgentProcess>() {
        if state.shutting_down() {
            return Err("Application is shutting down".to_string());
        }
        state.set_block_respawn(false);
        state.set_intentional_stop(false);
        stop_agent_sidecar_sync(&state, StopMode::Soft);
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
            sidecar_running: state.is_running() || agent_processes_running(),
            last_error: state.last_error.lock().unwrap().clone(),
        }
    } else {
        AgentStatus {
            sidecar_running: agent_processes_running(),
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

/// Open a native folder picker and return the absolute path (or null if cancelled).
#[tauri::command]
async fn pick_project_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;

    tauri::async_runtime::spawn_blocking(move || {
        let folder = app
            .dialog()
            .file()
            .set_title("Choisir le dossier du projet")
            .blocking_pick_folder();
        folder
            .and_then(|path| path.into_path().ok())
            .map(|path| path.to_string_lossy().into_owned())
    })
    .await
    .map_err(|err| err.to_string())
}

/// Show and focus the main desktop window (used by tray click / menu).
#[cfg(desktop)]
fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

/// System tray: left-click opens the window; right-click menu has Quit for a real exit.
#[cfg(desktop)]
fn setup_system_tray(app: &tauri::App) -> tauri::Result<()> {
    let show_item = MenuItem::with_id(app, "show", "Ouvrir", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "Quitter", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show_item, &quit_item])?;

    let mut builder = TrayIconBuilder::with_id("nightforge-tray")
        .menu(&menu)
        .tooltip("NightForge")
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_main_window(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            match event {
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
                | TrayIconEvent::DoubleClick {
                    button: MouseButton::Left,
                    ..
                } => {
                    show_main_window(tray.app_handle());
                }
                _ => {}
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    // Kept alive by the app resource table after build.
    let _tray = builder.build(app)?;
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
        .plugin(tauri_plugin_dialog::init())
        .manage(AgentProcess::new())
        .invoke_handler(tauri::generate_handler![
            restart_agent,
            stop_agent_sidecar,
            prepare_desktop_update,
            agent_status,
            agent_log_tail,
            pick_project_folder
        ])
        .setup(|app| {
            #[cfg(desktop)]
            setup_system_tray(app)?;

            if let Err(err) = spawn_agent(app.handle()) {
                eprintln!("Initial agent spawn failed: {err}");
            }
            Ok(())
        })
        .on_window_event(|window, event| match event {
            // Close button hides to tray instead of quitting; agent keeps running.
            #[cfg(desktop)]
            tauri::WindowEvent::CloseRequested { api, .. } => {
                api.prevent_close();
                let _ = window.hide();
            }
            // Real quit (tray → Quitter / app.exit) destroys the window and stops the agent.
            tauri::WindowEvent::Destroyed => {
                if let Some(state) = window.app_handle().try_state::<AgentProcess>() {
                    stop_agent_sidecar_sync(&state, StopMode::Shutdown);
                }
            }
            _ => {}
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            match event {
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
                    if let Some(state) = app_handle.try_state::<AgentProcess>() {
                        stop_agent_sidecar_sync(&state, StopMode::Shutdown);
                    }
                }
                _ => {}
            }
        });
}
