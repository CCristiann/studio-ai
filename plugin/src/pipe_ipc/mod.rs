//! Cross-platform IPC transport between the Studio AI plugin and FL Studio's
//! embedded Python MIDI script.
//!
//! Both backends expose the same surface:
//!
//! - [`setup_pipes`] — initialise the transport once during plugin construction.
//! - [`is_initialized`] — cheap readiness probe used by the WebSocket layer.
//! - [`relay_to_fl`] / [`relay_to_fl_async`] — send a JSON command and await
//!   the matching JSON response (newline-delimited, 5 s deadline).
//!
//! The two implementations differ only in how the bytes get from one side of
//! the process boundary to the other:
//!
//! | Platform | Transport                                            |
//! |----------|------------------------------------------------------|
//! | Unix     | anonymous `pipe(2)` + `dup2` onto fds 20 / 21        |
//! | Windows  | `CreateNamedPipeW` server, discovery via rendezvous  |
//!
//! See the per-backend module docs for the rationale behind each choice.

#[cfg(unix)]
mod unix;
#[cfg(unix)]
pub use unix::{is_initialized, relay_to_fl, setup_pipes};

#[cfg(windows)]
mod windows;
#[cfg(windows)]
pub use windows::{is_initialized, relay_to_fl, setup_pipes};

use std::io;

/// Async wrapper around the blocking [`relay_to_fl`] call.
///
/// Lives in the shared module so both backends inherit the same Tokio
/// integration without duplicating the `spawn_blocking` boilerplate.
pub async fn relay_to_fl_async(payload: String) -> io::Result<String> {
    tokio::task::spawn_blocking(move || relay_to_fl(&payload))
        .await
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?
}
