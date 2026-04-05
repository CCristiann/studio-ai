#!/bin/bash
# Build and deploy the Studio AI plugin + FL Studio MIDI script.
#
# Usage: ./scripts/deploy-plugin.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${GREEN}=== Studio AI Plugin Deploy ===${NC}"
echo ""

# 1. Build plugin in release mode
echo -e "${YELLOW}[1/3]${NC} Building Rust plugin (release)..."
(cd "$ROOT_DIR/plugin" && cargo build --release 2>&1 | tail -1)
echo -e "${GREEN}[OK]${NC} Plugin built"

# 2. Install VST3 binary
VST3_DIR="/Library/Audio/Plug-Ins/VST3/Studio AI.vst3"
BINARY_SRC="$ROOT_DIR/plugin/target/release/libstudio_ai_plugin.dylib"

if [ ! -f "$BINARY_SRC" ]; then
    echo -e "${RED}Binary not found: $BINARY_SRC${NC}"
    exit 1
fi

echo -e "${YELLOW}[2/3]${NC} Installing VST3 binary..."
# Update the bundle binary
sudo cp "$BINARY_SRC" "$VST3_DIR/Contents/MacOS/studio-ai"
echo -e "${GREEN}[OK]${NC} VST3 binary installed"

# 3. Install FL Studio MIDI script
echo -e "${YELLOW}[3/3]${NC} Installing FL Studio MIDI script..."
"$ROOT_DIR/scripts/install-fl-script.sh"

echo ""
echo -e "${GREEN}=== Deploy complete ===${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Restart FL Studio (or reload plugin)"
echo "  2. Make sure 'Studio AI' is enabled in Options → MIDI Settings"
echo "  3. Run ./dev.sh to start all services"
echo "  4. Open the Studio AI plugin in FL Studio"
echo "  5. Log in and try: 'set bpm to 160'"
