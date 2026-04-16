//! Unix pipe IPC backend.
//!
//! Creates two anonymous pipes via `pipe(2)` and remaps the FL-facing ends
//! onto well-known file descriptors so the embedded Python MIDI script can
//! read/write them directly through `os.read` / `os.write`:
//!
//! - fd 20: FL script reads commands from plugin (plugin writes, FL reads)
//! - fd 21: FL script writes responses to plugin (FL writes, plugin reads)
//!
//! This works because the plugin and FL's Python subinterpreter live in
//! the same process and share the same fd table. FL's Python is restricted
//! (no sockets, no threads) but inherited fds with `os.read` work reliably.
//!
//! The Windows backend uses a different transport (named pipes by name)
//! because Windows has no analogous fd-inheritance trick that survives
//! cross-CRT boundaries — see `windows.rs`.

use std::io;
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::Mutex;
use std::time::Duration;

/// File descriptors that FL Studio's MIDI script reads/writes.
const FL_READ_FD: i32 = 20;  // FL reads commands from this fd
const FL_WRITE_FD: i32 = 21; // FL writes responses to this fd

/// Max time to wait for the FL script to write a response.
///
/// Was 5s — too tight. The enhanced `get_project_state` handler iterates
/// 127 mixer tracks + 500 playlist tracks + N patterns + channels, each
/// calling 2-7 getters in FL's Python API. That's ~2000 round-trips into
/// FL's scripting runtime, which on slower machines routinely blows past
/// 5s. The FastAPI relay upstream waits 30s, so 20s here leaves ample
/// headroom without making genuine plugin hangs feel endless. Keep this
/// synced with `windows.rs`.
const PIPE_RESPONSE_TIMEOUT: Duration = Duration::from_secs(20);

/// Plugin-side file descriptors (the other ends of the pipes).
/// Using AtomicI32 for safe cross-thread access.
static PLUGIN_WRITE_FD: AtomicI32 = AtomicI32::new(-1);
static PLUGIN_READ_FD: AtomicI32 = AtomicI32::new(-1);

static PIPES_INITIALIZED: AtomicBool = AtomicBool::new(false);

/// Mutex to serialize pipe relay calls. FL script processes commands
/// sequentially in OnIdle(), so concurrent writes would cross-wire responses.
static RELAY_LOCK: Mutex<()> = Mutex::new(());

/// Set up the pipe pair. Must be called early in plugin lifecycle,
/// before FL Studio loads the MIDI script.
pub fn setup_pipes() -> io::Result<()> {
    if PIPES_INITIALIZED.swap(true, Ordering::SeqCst) {
        return Ok(()); // Already initialized
    }

    unsafe {
        // Pipe 1: Plugin → FL Script (commands)
        // plugin writes to cmd_pipe[1], FL reads from fd 20
        let mut cmd_pipe = [0i32; 2];
        if libc::pipe(cmd_pipe.as_mut_ptr()) != 0 {
            return Err(io::Error::last_os_error());
        }
        // Map the read end to fd 20 for FL script
        if libc::dup2(cmd_pipe[0], FL_READ_FD) < 0 {
            return Err(io::Error::last_os_error());
        }
        libc::close(cmd_pipe[0]); // Close original read fd, now duped to 20
        PLUGIN_WRITE_FD.store(cmd_pipe[1], Ordering::Release);

        // Pipe 2: FL Script → Plugin (responses)
        // FL writes to fd 21, plugin reads from resp_pipe[0]
        let mut resp_pipe = [0i32; 2];
        if libc::pipe(resp_pipe.as_mut_ptr()) != 0 {
            return Err(io::Error::last_os_error());
        }
        // Map the write end to fd 21 for FL script
        if libc::dup2(resp_pipe[1], FL_WRITE_FD) < 0 {
            return Err(io::Error::last_os_error());
        }
        libc::close(resp_pipe[1]); // Close original write fd, now duped to 21
        PLUGIN_READ_FD.store(resp_pipe[0], Ordering::Release);

        // Make the plugin's read fd non-blocking for async polling
        let flags = libc::fcntl(PLUGIN_READ_FD.load(Ordering::Acquire), libc::F_GETFL);
        libc::fcntl(PLUGIN_READ_FD.load(Ordering::Acquire), libc::F_SETFL, flags | libc::O_NONBLOCK);

        // Also make FL's read fd non-blocking so OnIdle doesn't block
        let flags = libc::fcntl(FL_READ_FD, libc::F_GETFL);
        libc::fcntl(FL_READ_FD, libc::F_SETFL, flags | libc::O_NONBLOCK);
    }

    log::info!(
        "Pipe IPC initialized: plugin_write={}, plugin_read={}, fl_read={}, fl_write={}",
        PLUGIN_WRITE_FD.load(Ordering::Acquire),
        PLUGIN_READ_FD.load(Ordering::Acquire),
        FL_READ_FD,
        FL_WRITE_FD,
    );

    Ok(())
}

/// Send a command to FL Studio via pipe and wait for response.
/// The command is a JSON string terminated by newline.
/// Returns the JSON response string.
///
/// Serialized by RELAY_LOCK to prevent response cross-wiring.
pub fn relay_to_fl(payload: &str) -> io::Result<String> {
    if !PIPES_INITIALIZED.load(Ordering::Acquire) {
        return Err(io::Error::new(io::ErrorKind::NotConnected, "Pipes not initialized"));
    }

    // Serialize access — FL script processes commands one at a time in OnIdle
    let _guard = RELAY_LOCK.lock().map_err(|_| {
        io::Error::new(io::ErrorKind::Other, "Relay lock poisoned")
    })?;

    let write_fd = PLUGIN_WRITE_FD.load(Ordering::Acquire);
    let read_fd = PLUGIN_READ_FD.load(Ordering::Acquire);

    // Best-effort cmd_id extraction for diagnostic logging. Not load-bearing;
    // if the caller forgot an id we still relay, we just log "?".
    let cmd_id: String = serde_json::from_str::<serde_json::Value>(payload)
        .ok()
        .and_then(|v| v.get("id").and_then(|id| id.as_str()).map(|s| s.to_string()))
        .unwrap_or_else(|| "?".to_string());

    // Write command + newline to pipe
    let data = format!("{}\n", payload);
    let bytes = data.as_bytes();
    let written = unsafe {
        libc::write(write_fd, bytes.as_ptr() as *const libc::c_void, bytes.len())
    };
    if written < 0 {
        return Err(io::Error::last_os_error());
    }
    log::info!(
        "pipe: sent cmd id={} bytes={} (wrote={})",
        cmd_id,
        bytes.len(),
        written
    );

    // Poll for response with timeout (see PIPE_RESPONSE_TIMEOUT), 10ms intervals
    let deadline = std::time::Instant::now() + PIPE_RESPONSE_TIMEOUT;
    let mut buffer = Vec::with_capacity(65536);
    let mut read_buf = [0u8; 65536];
    let mut reads_observed: u32 = 0;

    loop {
        if std::time::Instant::now() >= deadline {
            // Include accumulated buffer size in the error — a non-zero
            // figure here is a smoking gun for a bridge-side partial write
            // or a missing newline terminator.
            let preview: String = String::from_utf8_lossy(
                &buffer[..buffer.len().min(120)],
            )
            .to_string();
            log::warn!(
                "pipe: timeout id={} buffered={}B reads={} preview={:?}",
                cmd_id,
                buffer.len(),
                reads_observed,
                preview,
            );
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "FL script response timeout ({} s), id={}, buffered={}B (no '\\n' seen). \
                     A non-zero buffered count means the bridge wrote a partial response or \
                     forgot the newline terminator. Check FL Studio's Script Output for \
                     'pipe response'/'pipe write OK' lines.",
                    PIPE_RESPONSE_TIMEOUT.as_secs(),
                    cmd_id,
                    buffer.len(),
                ),
            ));
        }

        let n = unsafe {
            libc::read(read_fd, read_buf.as_mut_ptr() as *mut libc::c_void, read_buf.len())
        };

        if n > 0 {
            buffer.extend_from_slice(&read_buf[..n as usize]);
            reads_observed += 1;
            // Check for complete response (newline-delimited)
            if let Some(pos) = buffer.iter().position(|&b| b == b'\n') {
                let response = String::from_utf8_lossy(&buffer[..pos]).to_string();
                log::info!(
                    "pipe: response recv id={} bytes={} reads={}",
                    cmd_id,
                    pos,
                    reads_observed
                );
                return Ok(response);
            }
        } else if n < 0 {
            let err = io::Error::last_os_error();
            if err.kind() == io::ErrorKind::WouldBlock {
                // No data yet, sleep and retry
                std::thread::sleep(std::time::Duration::from_millis(10));
                continue;
            }
            return Err(err);
        } else {
            // n == 0: pipe closed
            log::warn!(
                "pipe: FD closed while waiting id={} buffered={}B",
                cmd_id,
                buffer.len()
            );
            return Err(io::Error::new(
                io::ErrorKind::BrokenPipe,
                format!("FL script pipe closed (buffered {}B, no newline)", buffer.len()),
            ));
        }
    }
}

/// Check if pipes are initialized.
pub fn is_initialized() -> bool {
    PIPES_INITIALIZED.load(Ordering::Acquire)
}
