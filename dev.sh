#!/bin/bash
# Start all Studio AI services for local development
# Usage: ./dev.sh

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down all services...${NC}"
  kill 0 2>/dev/null
  wait 2>/dev/null
  echo -e "${GREEN}All services stopped.${NC}"
}
trap cleanup EXIT INT TERM

echo -e "${GREEN}=== Studio AI Dev Environment ===${NC}"
echo ""

# 1. Redis
if command -v redis-cli &>/dev/null && redis-cli ping &>/dev/null 2>&1; then
  echo -e "${GREEN}[OK]${NC} Redis already running"
else
  echo -e "${YELLOW}[..]${NC} Starting Redis..."
  redis-server --daemonize yes 2>/dev/null || {
    echo -e "${RED}[!!] Redis not installed or failed to start. Install with: brew install redis${NC}"
    exit 1
  }
  echo -e "${GREEN}[OK]${NC} Redis started"
fi

# 2. FastAPI relay (apps/api)
echo -e "${YELLOW}[..]${NC} Starting FastAPI relay on :8000..."
(
  cd "$ROOT_DIR/apps/api"
  source .venv/bin/activate 2>/dev/null || true
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
) &

# 3. Next.js web (apps/web)
echo -e "${YELLOW}[..]${NC} Starting Next.js on :3000..."
(
  cd "$ROOT_DIR/apps/web"
  pnpm dev
) &

echo ""
echo -e "${GREEN}All services started:${NC}"
echo "  Next.js   → http://localhost:3000"
echo "  FastAPI   → http://localhost:8000"
echo "  Redis     → localhost:6379"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

wait
