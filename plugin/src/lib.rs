//! Studio AI VST3 Plugin

use nih_plug::prelude::*;
use nih_plug_webview::*;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

mod ipc;
mod state;
mod websocket_bridge;
mod websocket_cloud;

use state::{create_shared_state, SharedState};

struct StudioAiPlugin {
    params: Arc<StudioAiParams>,
    shared_state: SharedState,
    ws_started: Arc<AtomicBool>,
}

#[derive(Params)]
struct StudioAiParams {}

impl Default for StudioAiPlugin {
    fn default() -> Self {
        Self {
            params: Arc::new(StudioAiParams {}),
            shared_state: create_shared_state(),
            ws_started: Arc::new(AtomicBool::new(false)),
        }
    }
}

fn start_websockets(shared_state: SharedState) {
    std::thread::Builder::new()
        .name("studio-ai-ws".into())
        .spawn(move || {
            let rt = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .expect("Failed to create Tokio runtime");

            rt.block_on(async {
                let cloud_state = shared_state.clone();
                let bridge_state = shared_state.clone();

                tokio::join!(
                    websocket_cloud::run(cloud_state),
                    websocket_bridge::run(bridge_state),
                );
            });
        })
        .ok();
}

impl Plugin for StudioAiPlugin {
    const NAME: &'static str = "Studio AI";
    const VENDOR: &'static str = "Studio AI";
    const URL: &'static str = "https://studioai.app";
    const EMAIL: &'static str = "support@studioai.app";
    const VERSION: &'static str = env!("CARGO_PKG_VERSION");

    const AUDIO_IO_LAYOUTS: &'static [AudioIOLayout] = &[AudioIOLayout {
        main_input_channels: NonZeroU32::new(2),
        main_output_channels: NonZeroU32::new(2),
        aux_input_ports: &[],
        aux_output_ports: &[],
        names: PortNames::const_default(),
    }];

    type SysExMessage = ();
    type BackgroundTask = ();

    fn params(&self) -> Arc<dyn Params> {
        self.params.clone()
    }

    fn editor(&mut self, _async_executor: AsyncExecutor<Self>) -> Option<Box<dyn Editor>> {
        let shared_state = self.shared_state.clone();
        let ws_started = self.ws_started.clone();

        let editor = WebViewEditor::new(
            HTMLSource::URL("http://localhost:3000?context=plugin"),
            (900, 700),
        )
        .with_background_color((18, 18, 18, 255))
        .with_developer_mode(true)
        .with_event_loop(move |ctx, _setter, _window| {
            while let Ok(value) = ctx.next_event() {
                if let Some(msg_type) = value.get("type").and_then(|t| t.as_str()) {
                    match msg_type {
                        "sendToken" => {
                            if let Some(token) = value
                                .get("payload")
                                .and_then(|p| p.get("token"))
                                .and_then(|t| t.as_str())
                            {
                                if let Ok(mut state) = shared_state.try_lock() {
                                    state.set_token(token.to_string());
                                }
                                // Start WS threads on first token, once
                                if !ws_started.swap(true, Ordering::SeqCst) {
                                    start_websockets(shared_state.clone());
                                }
                            }
                        }
                        _ => {}
                    }
                }
            }
        });

        Some(Box::new(editor))
    }

    fn process(
        &mut self,
        _buffer: &mut Buffer,
        _aux: &mut AuxiliaryBuffers,
        _context: &mut impl ProcessContext<Self>,
    ) -> ProcessStatus {
        ProcessStatus::Normal
    }
}

impl ClapPlugin for StudioAiPlugin {
    const CLAP_ID: &'static str = "app.studioai.plugin";
    const CLAP_DESCRIPTION: Option<&'static str> =
        Some("AI-powered DAW control through natural language");
    const CLAP_MANUAL_URL: Option<&'static str> = None;
    const CLAP_SUPPORT_URL: Option<&'static str> = None;
    const CLAP_FEATURES: &'static [ClapFeature] = &[ClapFeature::Utility];
}

impl Vst3Plugin for StudioAiPlugin {
    const VST3_CLASS_ID: [u8; 16] = *b"StudioAIPlugin01";
    const VST3_SUBCATEGORIES: &'static [Vst3SubCategory] = &[Vst3SubCategory::Tools];
}

nih_export_clap!(StudioAiPlugin);
nih_export_vst3!(StudioAiPlugin);
