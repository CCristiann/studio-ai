#!/bin/bash
# Build and deploy the Studio AI plugin + FL Studio MIDI script on Windows.
#
# Run from Git Bash: ./scripts/deploy-plugin-windows.sh
# Requires: Rust toolchain, Git Bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${GREEN}=== Studio AI Plugin Deploy (Windows) ===${NC}"
echo ""

# ── 1. Build ────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[1/3]${NC} Building Rust plugin (release)..."
(cd "$ROOT_DIR/plugin" && cargo build --release 2>&1 | tail -3)

BINARY_SRC="$ROOT_DIR/plugin/target/release/studio_ai_plugin.dll"
if [ ! -f "$BINARY_SRC" ]; then
    echo -e "${RED}Build failed — DLL not found: $BINARY_SRC${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Plugin built"

# ── 2. Install VST3 bundle ───────────────────────────────────────────────────
# VST3 spec: <name>.vst3/Contents/x86_64-win/<name>.dll
VST3_ROOT="/c/Program Files/Common Files/VST3"
VST3_BUNDLE="$VST3_ROOT/Studio AI.vst3"
VST3_CONTENTS="$VST3_BUNDLE/Contents/x86_64-win"
VST3_DEST="$VST3_CONTENTS/studio_ai_plugin.dll"

echo -e "${YELLOW}[2/3]${NC} Installing VST3 bundle to:"
echo "  $VST3_DEST"

if [ ! -d "$VST3_ROOT" ]; then
    echo -e "${RED}VST3 directory not found: $VST3_ROOT${NC}"
    echo "  Is FL Studio installed? Create the directory and re-run."
    exit 1
fi

mkdir -p "$VST3_CONTENTS"
cp "$BINARY_SRC" "$VST3_DEST"
echo -e "${GREEN}[OK]${NC} VST3 installed"

# ── 3. Install FL Studio MIDI script ────────────────────────────────────────
echo -e "${YELLOW}[3/3]${NC} Installing FL Studio MIDI script..."
"$ROOT_DIR/scripts/install-fl-script.sh"

echo ""
echo -e "${GREEN}=== Deploy complete ===${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Restart FL Studio (or rescan plugins: Options → Manage plugins → Find more)"
echo "  2. Make sure 'Studio AI' is enabled in Options → MIDI Settings"
echo "  3. Run ./dev.sh to start all services"
echo "  4. Open the Studio AI plugin in FL Studio"
echo "  5. Log in and try: 'set bpm to 140'"
echo ""
echo -e "${YELLOW}Verify IPC is working:${NC}"
echo "  Check for rendezvous file: %LOCALAPPDATA%\\Studio AI\\ipc.json"
