//! Windows named-pipe IPC backend.
//!
//! Mirrors the Unix backend's public API ([`setup_pipes`], [`relay_to_fl`],
//! [`is_initialized`]) but uses a different transport because Windows has no
//! reliable equivalent of the Unix `dup2`-onto-fd-20/21 trick across the
//! Rust/embedded-Python CRT boundary.
//!
//! ## Transport
//!
//! Two byte-mode named pipes are created by the plugin (the *server*) and
//! connected to by FL Studio's MIDI script (the *client*) running in the
//! same process:
//!
//! - `\\.\pipe\studio-ai-<pid>-cmd`  — plugin → FL (commands)
//! - `\\.\pipe\studio-ai-<pid>-resp` — FL → plugin (responses)
//!
//! `<pid>` is `GetCurrentProcessId()` so multiple FL Studio instances on the
//! same machine never collide. Both pipes are `PIPE_TYPE_BYTE |
//! PIPE_READMODE_BYTE` with 64 KiB buffers and `nMaxInstances = 1`. The
//! `FILE_FLAG_FIRST_PIPE_INSTANCE` flag guarantees we fail loudly if a stale
//! pipe with the same name already exists.
//!
//! ## Discovery
//!
//! The plugin writes a small rendezvous file at
//! `%LOCALAPPDATA%\Studio AI\ipc.json` containing the pipe names and PID.
//! The Python script polls for this file in `OnIdle` until it appears, then
//! opens the two pipes via `CreateFileW`. This is the Windows analogue of
//! the Unix `os.fstat(20)` readiness probe.
//!
//! ## Concurrency
//!
//! - A dedicated background thread runs `ConnectNamedPipe` for both pipes
//!   and stores the connected handles in [`PipeServer::handles`] (an
//!   `OnceLock`-flavoured `Mutex<Option<…>>`). [`is_initialized`] returns
//!   `true` once both sides are connected.
//! - [`relay_to_fl`] is serialised by [`RELAY_LOCK`] to match the Unix
//!   backend — FL's script processes commands one at a time in `OnIdle`,
//!   so concurrent writes would cross-wire responses.
//! - Reads use `PeekNamedPipe` for non-blocking polling with the same
//!   10 ms / 5 s deadline shape as the Unix backend.

use std::ffi::OsString;
use std::fs;
use std::io;
use std::os::windows::ffi::OsStrExt;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use windows_sys::Win32::Foundation::{
    CloseHandle, GetLastError, ERROR_BROKEN_PIPE, ERROR_PIPE_CONNECTED, HANDLE,
    INVALID_HANDLE_VALUE,
};
use windows_sys::Win32::Storage::FileSystem::{
    ReadFile, WriteFile, FILE_FLAG_FIRST_PIPE_INSTANCE, PIPE_ACCESS_DUPLEX,
};
use windows_sys::Win32::System::Pipes::{
    ConnectNamedPipe, CreateNamedPipeW, PeekNamedPipe, PIPE_READMODE_BYTE, PIPE_TYPE_BYTE,
    PIPE_WAIT,
};
use windows_sys::Win32::System::Threading::GetCurrentProcessId;

const PIPE_BUFFER_SIZE: u32 = 65_536;
const RELAY_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(5);
const POLL_INTERVAL: std::time::Duration = std::time::Duration::from_millis(10);

/// `HANDLE` is `*mut c_void` and therefore not `Send` by default. Wrap it in
/// a newtype with a deliberate `Send` impl so we can move handles into the
/// accept thread without sprinkling `unsafe impl` blocks around the module.
///
/// SAFETY: All Win32 syscalls we use on these handles
/// (`ReadFile`/`WriteFile`/`PeekNamedPipe`/`CloseHandle`) are documented as
/// thread-safe, and concurrent relays are serialised by [`RELAY_LOCK`].
struct SendHandle(HANDLE);
unsafe impl Send for SendHandle {}

impl SendHandle {
    /// Consume the wrapper and return the raw handle.
    ///
    /// Taking `self` by value forces closures to capture the whole
    /// `SendHandle` (which is `Send`) instead of using disjoint-capture
    /// to grab the bare non-`Send` `HANDLE` field.
    fn into_raw(self) -> HANDLE {
        self.0
    }
}

/// Connected pipe pair, owned by the server thread once both sides hand-shake.
struct ConnectedPipes {
    cmd: HANDLE,
    resp: HANDLE,
}

// SAFETY: see `SendHandle` above — same justification.
unsafe impl Send for ConnectedPipes {}

impl Drop for ConnectedPipes {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.cmd);
            CloseHandle(self.resp);
        }
    }
}

static PIPES: Mutex<Option<ConnectedPipes>> = Mutex::new(None);
static SERVER_STARTED: AtomicBool = AtomicBool::new(false);
static RELAY_LOCK: Mutex<()> = Mutex::new(());

/// Set up the named-pipe server. Must be called early in the plugin
/// lifecycle, before FL Studio loads the MIDI script.
///
/// Idempotent: subsequent calls after a successful first call are no-ops.
pub fn setup_pipes() -> io::Result<()> {
    if SERVER_STARTED.swap(true, Ordering::SeqCst) {
        return Ok(());
    }

    let pid = unsafe { GetCurrentProcessId() };
    let cmd_name = format!(r"\\.\pipe\studio-ai-{}-cmd", pid);
    let resp_name = format!(r"\\.\pipe\studio-ai-{}-resp", pid);

    let cmd_handle = SendHandle(create_server_pipe(&cmd_name)?);
    let resp_handle = match create_server_pipe(&resp_name) {
        Ok(h) => SendHandle(h),
        Err(e) => {
            unsafe { CloseHandle(cmd_handle.0) };
            return Err(e);
        }
    };

    write_rendezvous(pid, &cmd_name, &resp_name)?;

    // Spawn a thread that blocks on ConnectNamedPipe for both pipes.
    // FL Studio's Python script will open them via CreateFileW once it
    // sees the rendezvous file. This mirrors the "wait for the other side"
    // handshake the Unix backend gets for free from fd inheritance.
    std::thread::Builder::new()
        .name("studio-ai-pipe-accept".into())
        .spawn(move || {
            let cmd = cmd_handle.into_raw();
            let resp = resp_handle.into_raw();
            if let Err(e) = accept_connections(cmd, resp) {
                log::error!("Studio AI pipe accept failed: {}", e);
                unsafe {
                    CloseHandle(cmd);
                    CloseHandle(resp);
                }
            }
        })
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;

    log::info!(
        "Studio AI named-pipe server listening: cmd={} resp={}",
        cmd_name,
        resp_name
    );
    Ok(())
}

/// Send a command to FL Studio and wait for the matching response.
/// Newline-delimited JSON, 5 s deadline.
pub fn relay_to_fl(payload: &str) -> io::Result<String> {
    let _guard = RELAY_LOCK
        .lock()
        .map_err(|_| io::Error::new(io::ErrorKind::Other, "Relay lock poisoned"))?;

    // Snapshot the connected handles. We hold the PIPES lock only briefly;
    // RELAY_LOCK above already prevents concurrent relays from racing.
    let (cmd, resp) = {
        let guard = PIPES
            .lock()
            .map_err(|_| io::Error::new(io::ErrorKind::Other, "Pipes lock poisoned"))?;
        let pipes = guard
            .as_ref()
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotConnected, "Pipes not connected"))?;
        (pipes.cmd, pipes.resp)
    };

    write_all(cmd, format!("{}\n", payload).as_bytes())?;
    read_line_with_timeout(resp, RELAY_TIMEOUT)
}

/// True once FL Studio's script has connected to both pipes.
pub fn is_initialized() -> bool {
    PIPES
        .lock()
        .map(|g| g.is_some())
        .unwrap_or(false)
}

// ─────────────────────── server-side helpers ───────────────────────

fn create_server_pipe(name: &str) -> io::Result<HANDLE> {
    let wide = to_wide(name);
    let handle = unsafe {
        CreateNamedPipeW(
            wide.as_ptr(),
            PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            1, // nMaxInstances — single client (FL Studio)
            PIPE_BUFFER_SIZE,
            PIPE_BUFFER_SIZE,
            0, // default 50 ms timeout (unused with PIPE_WAIT clients)
            std::ptr::null(),
        )
    };
    if handle == INVALID_HANDLE_VALUE {
        return Err(last_os_error("CreateNamedPipeW"));
    }
    Ok(handle)
}

fn accept_connections(cmd: HANDLE, resp: HANDLE) -> io::Result<()> {
    // ConnectNamedPipe blocks until a client opens the pipe. Order matters:
    // the Python client opens cmd first, then resp, so we accept in the same
    // order to avoid spurious deadlocks if either side races.
    accept_one(cmd, "cmd")?;
    accept_one(resp, "resp")?;

    let pipes = ConnectedPipes { cmd, resp };
    let mut guard = PIPES
        .lock()
        .map_err(|_| io::Error::new(io::ErrorKind::Other, "Pipes lock poisoned"))?;
    *guard = Some(pipes);
    log::info!("Studio AI pipes connected — bridge ready");
    Ok(())
}

fn accept_one(handle: HANDLE, label: &str) -> io::Result<()> {
    let ok = unsafe { ConnectNamedPipe(handle, std::ptr::null_mut()) };
    if ok == 0 {
        // ERROR_PIPE_CONNECTED means the client connected between
        // CreateNamedPipeW and ConnectNamedPipe — that's success, not failure.
        let err = unsafe { GetLastError() };
        if err != ERROR_PIPE_CONNECTED {
            return Err(io::Error::from_raw_os_error(err as i32));
        }
    }
    log::info!("Studio AI {} pipe connected", label);
    Ok(())
}

// ─────────────────────── I/O helpers ───────────────────────

fn write_all(handle: HANDLE, mut buf: &[u8]) -> io::Result<()> {
    while !buf.is_empty() {
        let mut written: u32 = 0;
        let ok = unsafe {
            WriteFile(
                handle,
                buf.as_ptr(),
                buf.len() as u32,
                &mut written,
                std::ptr::null_mut(),
            )
        };
        if ok == 0 {
            return Err(last_os_error("WriteFile"));
        }
        if written == 0 {
            return Err(io::Error::new(io::ErrorKind::WriteZero, "WriteFile wrote 0"));
        }
        buf = &buf[written as usize..];
    }
    Ok(())
}

/// Poll `PeekNamedPipe` until a newline arrives or the deadline elapses.
fn read_line_with_timeout(handle: HANDLE, timeout: std::time::Duration) -> io::Result<String> {
    let deadline = std::time::Instant::now() + timeout;
    let mut buffer: Vec<u8> = Vec::with_capacity(1024);
    let mut chunk = [0u8; 4096];

    loop {
        if std::time::Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "FL script response timeout",
            ));
        }

        let mut available: u32 = 0;
        let ok = unsafe {
            PeekNamedPipe(
                handle,
                std::ptr::null_mut(),
                0,
                std::ptr::null_mut(),
                &mut available,
                std::ptr::null_mut(),
            )
        };
        if ok == 0 {
            let err = unsafe { GetLastError() };
            if err == ERROR_BROKEN_PIPE {
                return Err(io::Error::new(
                    io::ErrorKind::BrokenPipe,
                    "FL script pipe closed",
                ));
            }
            return Err(io::Error::from_raw_os_error(err as i32));
        }

        if available == 0 {
            std::thread::sleep(POLL_INTERVAL);
            continue;
        }

        let to_read = available.min(chunk.len() as u32);
        let mut read: u32 = 0;
        let ok = unsafe {
            ReadFile(
                handle,
                chunk.as_mut_ptr(),
                to_read,
                &mut read,
                std::ptr::null_mut(),
            )
        };
        if ok == 0 {
            return Err(last_os_error("ReadFile"));
        }
        if read == 0 {
            return Err(io::Error::new(
                io::ErrorKind::BrokenPipe,
                "FL script pipe closed",
            ));
        }

        buffer.extend_from_slice(&chunk[..read as usize]);
        if let Some(pos) = buffer.iter().position(|&b| b == b'\n') {
            return Ok(String::from_utf8_lossy(&buffer[..pos]).into_owned());
        }
    }
}

// ─────────────────────── rendezvous ───────────────────────

fn rendezvous_path() -> io::Result<PathBuf> {
    // dirs::data_local_dir() resolves to %LOCALAPPDATA% on Windows.
    let mut p = dirs::data_local_dir().ok_or_else(|| {
        io::Error::new(io::ErrorKind::NotFound, "LOCALAPPDATA not available")
    })?;
    p.push("Studio AI");
    fs::create_dir_all(&p)?;
    p.push("ipc.json");
    Ok(p)
}

fn write_rendezvous(pid: u32, cmd: &str, resp: &str) -> io::Result<()> {
    let path = rendezvous_path()?;
    // JSON-escape backslashes (Windows pipe names are \\.\pipe\…).
    let escape = |s: &str| s.replace('\\', "\\\\");
    let body = format!(
        "{{\"version\":1,\"pid\":{},\"cmd_pipe\":\"{}\",\"resp_pipe\":\"{}\"}}\n",
        pid,
        escape(cmd),
        escape(resp),
    );
    // Atomic-ish: write to a temp file then rename over the destination.
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, body)?;
    fs::rename(&tmp, &path)?;
    log::info!("Studio AI rendezvous written: {}", path.display());
    Ok(())
}

// ─────────────────────── misc ───────────────────────

fn to_wide(s: &str) -> Vec<u16> {
    OsString::from(s).encode_wide().chain(std::iter::once(0)).collect()
}

fn last_os_error(ctx: &'static str) -> io::Error {
    let code = unsafe { GetLastError() } as i32;
    io::Error::new(
        io::Error::from_raw_os_error(code).kind(),
        format!("{} failed (os error {})", ctx, code),
    )
}
