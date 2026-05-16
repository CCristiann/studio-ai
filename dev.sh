#!/bin/bash
# Start all Studio AI services for local development
# Usage: ./dev.sh
#
# Per-service logs land in .dev-logs/ (gitignored). On startup failure,
# the script prints the offending log's last lines and exits.

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/.dev-logs"
mkdir -p "$LOG_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() {
  trap - EXIT INT TERM  # prevent recursion when kill 0 hits this shell
  echo ""
  echo -e "${YELLOW}Shutting down all services...${NC}"
  kill 0 2>/dev/null
  wait 2>/dev/null
  echo -e "${GREEN}All services stopped.${NC}"
}

# Wait up to $3 seconds for a check command to succeed.
wait_for() {
  local label="$1"
  local check="$2"
  local timeout="${3:-15}"
  local elapsed=0
  while (( elapsed < timeout * 2 )); do
    if eval "$check"; then
      return 0
    fi
    sleep 0.5
    elapsed=$((elapsed + 1))
  done
  return 1
}

fail_with_log() {
  local label="$1"
  local log="$2"
  echo -e "${RED}[!!] $label failed to start. Last 30 lines of $log:${NC}"
  tail -30 "$log" 2>/dev/null || echo "(log file missing)"
  exit 1
}

echo -e "${GREEN}=== Studio AI Dev Environment ===${NC}"
echo ""

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if ! command -v redis-cli &>/dev/null; then
  echo -e "${RED}[!!] redis-cli not found. Install with: brew install redis${NC}"
  exit 1
fi

if ! command -v pnpm &>/dev/null; then
  echo -e "${RED}[!!] pnpm not found. Install with: npm i -g pnpm${NC}"
  exit 1
fi

if [[ ! -f "$ROOT_DIR/apps/api/.venv/bin/activate" ]]; then
  echo -e "${RED}[!!] FastAPI venv missing at apps/api/.venv${NC}"
  echo "    Set up with:"
  echo "      cd apps/api"
  echo "      python -m venv .venv"
  echo "      source .venv/bin/activate"
  echo "      pip install -r requirements.txt"
  exit 1
fi

# Register cleanup only now that pre-flight has passed and we're about to
# spawn background services. Pre-flight failures exit cleanly without it.
trap cleanup EXIT INT TERM

# ── 1. Redis ──────────────────────────────────────────────────────────────────
if redis-cli ping &>/dev/null; then
  echo -e "${GREEN}[OK]${NC} Redis already running"
else
  echo -e "${YELLOW}[..]${NC} Starting Redis..."
  redis-server --daemonize yes 2>/dev/null || {
    echo -e "${RED}[!!] Redis failed to start${NC}"
    exit 1
  }
  echo -e "${GREEN}[OK]${NC} Redis started"
fi

# ── 2. FastAPI relay (apps/api) ───────────────────────────────────────────────
FASTAPI_LOG="$LOG_DIR/fastapi.log"
: > "$FASTAPI_LOG"
echo -e "${YELLOW}[..]${NC} Starting FastAPI relay on :8000 (logs → $FASTAPI_LOG)..."
(
  cd "$ROOT_DIR/apps/api"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  exec uvicorn main:app --reload --host 0.0.0.0 --port 8000
) > "$FASTAPI_LOG" 2>&1 &

if ! wait_for "FastAPI" "curl -sf http://localhost:8000/health > /dev/null 2>&1" 15; then
  fail_with_log "FastAPI" "$FASTAPI_LOG"
fi
echo -e "${GREEN}[OK]${NC} FastAPI healthy on :8000"

# ── 3. Next.js web (apps/web) ─────────────────────────────────────────────────
WEB_LOG="$LOG_DIR/web.log"
: > "$WEB_LOG"
echo -e "${YELLOW}[..]${NC} Starting Next.js on :3000 (logs → $WEB_LOG)..."
(
  cd "$ROOT_DIR/apps/web"
  exec pnpm dev
) > "$WEB_LOG" 2>&1 &

if ! wait_for "Next.js" "nc -z localhost 3000 2>/dev/null" 30; then
  fail_with_log "Next.js" "$WEB_LOG"
fi
echo -e "${GREEN}[OK]${NC} Next.js listening on :3000"

echo ""
echo -e "${GREEN}All services started:${NC}"
echo "  Next.js   → http://localhost:3000   (tail -f $WEB_LOG)"
echo "  FastAPI   → http://localhost:8000   (tail -f $FASTAPI_LOG)"
echo "  Redis     → localhost:6379"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

wait
