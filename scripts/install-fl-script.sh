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

# Determine FL Studio Hardware directory
if [[ "$OSTYPE" == "darwin"* ]]; then
    FL_HARDWARE_DIR="$HOME/Documents/Image-Line/FL Studio/Settings/Hardware"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    FL_HARDWARE_DIR="$USERPROFILE/Documents/Image-Line/FL Studio/Settings/Hardware"
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

# Create destination directory
mkdir -p "$DEST_DIR"

# Copy the scripts
cp "$SCRIPT_SRC" "$DEST_FILE"
cp "$HANDLERS_SRC" "$DEST_DIR/handlers_organize.py"
cp "$TRANSPORT_SRC" "$DEST_DIR/ipc_transport.py"

echo -e "${GREEN}FL Studio MIDI scripts installed to:${NC}"
echo "  $DEST_FILE"
echo "  $DEST_DIR/handlers_organize.py"
echo "  $DEST_DIR/ipc_transport.py"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Open FL Studio"
echo "  2. Go to Options → MIDI Settings"
echo "  3. Under 'Input', select any available port"
echo "  4. Under 'Controller type', select 'Studio AI'"
echo "  5. Click the green enable button"
echo ""
echo -e "${GREEN}Done!${NC}"
