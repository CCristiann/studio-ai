//! Studio AI VST3 Plugin

use nih_plug::prelude::*;
use std::sync::Arc;

mod state;
mod ipc;
mod websocket_cloud;
mod websocket_bridge;

use state::{create_shared_state, SharedState};

struct StudioAiPlugin {
    params: Arc<StudioAiParams>,
    shared_state: SharedState,
}

#[derive(Params)]
struct StudioAiParams {}

impl Default for StudioAiPlugin {
    fn default() -> Self {
        Self {
            params: Arc::new(StudioAiParams {}),
            shared_state: create_shared_state(),
        }
    }
}

impl Plugin for StudioAiPlugin {
    const NAME: &'static str = "Studio AI";
    const VENDOR: &'static str = "Studio AI";
    const URL: &'static str = "https://studioai.app";
    const EMAIL: &'static str = "support@studioai.app";
    const VERSION: &'static str = env!("CARGO_PKG_VERSION");
    const AUDIO_IO_LAYOUTS: &'static [AudioIOLayout] = &[];
    type SysExMessage = ();
    type BackgroundTask = ();

    fn params(&self) -> Arc<dyn Params> {
        self.params.clone()
    }

    fn initialize(
        &mut self,
        _audio_io_layout: &AudioIOLayout,
        _buffer_config: &BufferConfig,
        _context: &mut impl InitContext<Self>,
    ) -> bool {
        let state = self.shared_state.clone();

        std::thread::spawn(move || {
            let rt = tokio::runtime::Runtime::new()
                .expect("Failed to create Tokio runtime");

            let cloud_state = state.clone();
            let bridge_state = state.clone();

            rt.block_on(async {
                let cloud_handle = tokio::spawn(async move {
                    websocket_cloud::run(cloud_state).await;
                });

                let bridge_handle = tokio::spawn(async move {
                    websocket_bridge::run(bridge_state).await;
                });

                let _ = tokio::join!(cloud_handle, bridge_handle);
            });
        });

        true
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
