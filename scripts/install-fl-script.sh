#!/bin/bash
# Install the FL Studio MIDI script for Studio AI.
#
# Copies the bridge script to FL Studio's Hardware directory so it
# appears in Options → MIDI Settings as "Studio AI".
#
# Usage: ./scripts/install-fl-script.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_SRC="$ROOT_DIR/bridge/fl_studio/device_studio_ai.py"
HANDLERS_SRC="$ROOT_DIR/bridge/fl_studio/handlers_organize.py"
TRANSPORT_SRC="$ROOT_DIR/bridge/fl_studio/ipc_transport.py"
PROTOCOL_SRC="$ROOT_DIR/bridge/fl_studio/_protocol.py"

# Determine FL Studio Hardware directory
if [[ "$OSTYPE" == "darwin"* ]]; then
    FL_HARDWARE_DIR="$HOME/Documents/Image-Line/FL Studio/Settings/Hardware"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    # FL Studio on Windows uses the OneDrive-synced Documents folder.
    # Try OneDrive paths first (Italian "Documenti" and English "Documents"),
    # then fall back to the local Documents folder.
    if [ -d "$USERPROFILE/OneDrive/Documenti/Image-Line" ]; then
        FL_HARDWARE_DIR="$USERPROFILE/OneDrive/Documenti/Image-Line/FL Studio/Settings/Hardware"
    elif [ -d "$USERPROFILE/OneDrive/Documents/Image-Line" ]; then
        FL_HARDWARE_DIR="$USERPROFILE/OneDrive/Documents/Image-Line/FL Studio/Settings/Hardware"
    else
        FL_HARDWARE_DIR="$USERPROFILE/Documents/Image-Line/FL Studio/Settings/Hardware"
    fi
else
    echo -e "${RED}Unsupported platform: $OSTYPE${NC}"
    exit 1
fi

DEST_DIR="$FL_HARDWARE_DIR/Studio AI"
DEST_FILE="$DEST_DIR/device_studio_ai.py"

# Verify sources exist
if [ ! -f "$SCRIPT_SRC" ]; then
    echo -e "${RED}Source script not found: $SCRIPT_SRC${NC}"
    exit 1
fi
if [ ! -f "$HANDLERS_SRC" ]; then
    echo -e "${RED}Handlers script not found: $HANDLERS_SRC${NC}"
    exit 1
fi
if [ ! -f "$TRANSPORT_SRC" ]; then
    echo -e "${RED}Transport module not found: $TRANSPORT_SRC${NC}"
    exit 1
fi
if [ ! -f "$PROTOCOL_SRC" ]; then
    echo -e "${RED}Protocol module not found: $PROTOCOL_SRC${NC}"
    exit 1
fi
# Create destination directory
mkdir -p "$DEST_DIR"

# Copy the scripts
cp "$SCRIPT_SRC" "$DEST_FILE"
cp "$HANDLERS_SRC" "$DEST_DIR/handlers_organize.py"
cp "$TRANSPORT_SRC" "$DEST_DIR/ipc_transport.py"
cp "$PROTOCOL_SRC" "$DEST_DIR/_protocol.py"

# Clean up legacy two-script install artifacts from previous versions.
rm -f "$DEST_DIR/device_studio_ai_receive.py" "$DEST_DIR/device_studio_ai_respond.py"

echo -e "${GREEN}FL Studio MIDI scripts installed to:${NC}"
echo "  $DEST_DIR/"
echo ""

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}macOS setup:${NC}"
    echo "  1. Open FL Studio"
    echo "  2. Options -> MIDI Settings"
    echo "  3. Add one controller entry:"
    echo "     Input:           any IAC Driver bus"
    echo "     Output:          any IAC Driver bus"
    echo "     Port:            1"
    echo "     Controller type: Studio AI"
    echo "  4. Enable (green button)"
    echo ""
    echo "  Data flows over anonymous pipes (no MIDI required for IPC)."
else
    echo -e "${YELLOW}Windows setup (LoopMIDI required):${NC}"
    echo "  1. Install LoopMIDI: https://www.tobias-erichsen.de/software/loopmidi.html"
    echo "  2. Create two virtual ports named exactly:"
    echo "       Studio AI Cmd"
    echo "       Studio AI Resp"
    echo "  3. Open FL Studio -> Options -> MIDI Settings"
    echo "  4. Configure ONE controller (single script, two cables, one Port):"
    echo ""
    echo "     Input row:"
    echo "       Device:          Studio AI Cmd"
    echo "       Controller type: Studio AI"
    echo "       Port:            1"
    echo "       Enabled:         yes"
    echo ""
    echo "     Output row:"
    echo "       Device:          Studio AI Resp"
    echo "       Port:            1   <- MUST match the Input Port number"
    echo "       Enabled:         yes"
    echo ""
    echo "  FL routes device.midiOutSysex() from the script to 'Studio AI Resp'"
    echo "  because both cables share Port number 1. The Output row has no"
    echo "  controller-type field — that's expected."
    echo ""
    echo "  5. Options -> General settings -> enable 'Run in background'."
fi

echo -e "${GREEN}Done!${NC}"
