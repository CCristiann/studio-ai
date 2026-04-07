interface PluginConnectionStatus {
  cloud: { connected: boolean; latency_ms?: number };
  bridge: { connected: boolean; daw?: string; project?: string };
}

interface PluginMessage {
  type: string;
  [key: string]: unknown;
}

interface Window {
  ipc?: {
    postMessage(message: string): void;
  };
  sendToPlugin?: (msg: PluginMessage) => void;
  onPluginMessage?: (msg: PluginMessage) => void;
}
