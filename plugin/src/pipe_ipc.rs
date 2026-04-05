//! Pipe IPC for communicating with FL Studio's MIDI script.
//!
//! Creates two anonymous pipes and maps them to well-known file descriptors:
//! - fd 20: FL script reads commands from plugin (plugin writes, FL reads)
//! - fd 21: FL script writes responses to plugin (FL writes, plugin reads)
//!
//! This approach is proven from the fl-bridge project. FL Studio's Python
//! subinterpreter blocks socket/threading but os.read/os.write on inherited
//! fds works reliably.
//!
//! Platform: macOS/Linux only. Windows requires a separate implementation
//! using CreateNamedPipe / PeekNamedPipe.

#[cfg(not(unix))]
compile_error!("pipe_ipc.rs requires a Unix platform (macOS/Linux). Windows support requires a separate implementation.");

use std::io;
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::Mutex;

/// File descriptors that FL Studio's MIDI script reads/writes.
const FL_READ_FD: i32 = 20;  // FL reads commands from this fd
const FL_WRITE_FD: i32 = 21; // FL writes responses to this fd

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

    // Write command + newline to pipe
    let data = format!("{}\n", payload);
    let bytes = data.as_bytes();
    let written = unsafe {
        libc::write(write_fd, bytes.as_ptr() as *const libc::c_void, bytes.len())
    };
    if written < 0 {
        return Err(io::Error::last_os_error());
    }

    // Poll for response with timeout (5 seconds, 10ms intervals)
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
    let mut buffer = Vec::with_capacity(65536);
    let mut read_buf = [0u8; 65536];

    loop {
        if std::time::Instant::now() >= deadline {
            return Err(io::Error::new(io::ErrorKind::TimedOut, "FL script response timeout"));
        }

        let n = unsafe {
            libc::read(read_fd, read_buf.as_mut_ptr() as *mut libc::c_void, read_buf.len())
        };

        if n > 0 {
            buffer.extend_from_slice(&read_buf[..n as usize]);
            // Check for complete response (newline-delimited)
            if let Some(pos) = buffer.iter().position(|&b| b == b'\n') {
                let response = String::from_utf8_lossy(&buffer[..pos]).to_string();
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
            return Err(io::Error::new(io::ErrorKind::BrokenPipe, "FL script pipe closed"));
        }
    }
}

/// Async wrapper for relay_to_fl, safe to call from tokio tasks.
pub async fn relay_to_fl_async(payload: String) -> io::Result<String> {
    tokio::task::spawn_blocking(move || relay_to_fl(&payload))
        .await
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?
}

/// Check if pipes are initialized.
pub fn is_initialized() -> bool {
    PIPES_INITIALIZED.load(Ordering::Acquire)
}
