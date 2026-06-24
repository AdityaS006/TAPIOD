#!/bin/bash
# TAPIOD — one-command setup for Linux / macOS / WSL
# Run once on a fresh clone; safe to re-run (skips completed steps).
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GATEWAY="$ROOT/backend"
WEB="$ROOT/frontend"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $1${RESET}"; }
step() { echo -e "\n${CYAN}[$1/6] $2${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${RESET}"; }

echo ""
echo "  ████████╗ █████╗ ██████╗ ██╗ ██████╗ ██████╗ "
echo "     ██║   ██╔══██╗██╔══██╗██║██╔═══██╗██╔══██╗"
echo "     ██║   ███████║██████╔╝██║██║   ██║██║  ██║"
echo "     ██║   ██╔══██║██╔═══╝ ██║██║   ██║██║  ██║"
echo "     ██║   ██║  ██║██║     ██║╚██████╔╝██████╔╝"
echo "     ╚═╝   ╚═╝  ╚═╝╚═╝     ╚═╝ ╚═════╝ ╚═════╝"
echo ""
echo "  Enterprise LLM Gateway — Setup"
echo "  ────────────────────────────────────────────"
echo ""

# ── .env check ────────────────────────────────────────────────────────────────
if [ ! -f "$GATEWAY/.env" ]; then
    warn "backend/.env not found — copying from .env.example"
    cp "$GATEWAY/.env.example" "$GATEWAY/.env"
    echo ""
    echo "  Open backend/.env and add your GROQ_API_KEY before continuing."
    echo "  Get a free key at https://console.groq.com"
    echo ""
    read -rp "  Press Enter once you've added your key... "
fi

# ── FERNET_SECRET ─────────────────────────────────────────────────────────────
if ! grep -q "^FERNET_SECRET=" "$GATEWAY/.env" 2>/dev/null; then
    FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null)
    if [ -n "$FERNET_KEY" ]; then
        echo "FERNET_SECRET=$FERNET_KEY" >> "$GATEWAY/.env"
        ok "FERNET_SECRET generated and added to backend/.env"
    else
        warn "Could not generate FERNET_SECRET — install cryptography: pip install cryptography"
    fi
else
    ok "FERNET_SECRET already set"
fi

# ── Step 1: Docker infrastructure ────────────────────────────────────────────
step 1 "Starting infrastructure  (Qdrant · PostgreSQL · Redis)"
docker compose -f "$ROOT/docker-compose.yml" up -d
echo "  Waiting for services to be healthy..."
until docker exec gateway-redis redis-cli ping 2>/dev/null | grep -q PONG; do sleep 1; done; ok "Redis"
until docker exec gateway-postgres pg_isready -U litellm 2>/dev/null | grep -q "accepting"; do sleep 1; done; ok "PostgreSQL"
until curl -sf http://localhost:6333/readyz 2>/dev/null | grep -q "ready"; do sleep 1; done; ok "Qdrant"

# ── Step 2: Python environment ───────────────────────────────────────────────
step 2 "Python environment"
if [ ! -d "$GATEWAY/venv" ]; then
    python3 -m venv "$GATEWAY/venv"
    ok "Virtualenv created"
fi
source "$GATEWAY/venv/bin/activate"
pip install -r "$GATEWAY/requirements.txt" -q --disable-pip-version-check
ok "Dependencies installed"

# ── Step 3: Seed Qdrant ──────────────────────────────────────────────────────
step 3 "Seeding routing brain  (5,000 training examples)"
POINT_COUNT=$(curl -s http://localhost:6333/collections/routing_examples 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['points_count'])" 2>/dev/null || echo "0")

if [ "$POINT_COUNT" -ge 5000 ] 2>/dev/null; then
    ok "routing_examples already seeded ($POINT_COUNT points) — skipping"
else
    warn "First run: downloads embedding model (~130 MB) — takes ~3 min"
    cd "$GATEWAY" && python seeds/seed_all.py
    ok "Qdrant seeded"
fi

# ── Step 4: Next.js build ────────────────────────────────────────────────────
step 4 "Building dashboard"
cd "$WEB"
if [ ! -d "node_modules" ]; then
    npm install -q
    ok "npm packages installed"
fi
npm run build -q
ok "Production build ready"

# ── Step 5: Launch all three services ────────────────────────────────────────
step 5 "Launching services"
source "$GATEWAY/venv/bin/activate"

PYTHONPATH="$GATEWAY" nohup litellm --config "$GATEWAY/litellm_config.yaml" --port 4000 > /tmp/tapiod-litellm.log 2>&1 &
LITELLM_PID=$!; ok "LiteLLM proxy  :4000  (PID $LITELLM_PID)"

PYTHONPATH="$GATEWAY" nohup uvicorn main:app --app-dir "$GATEWAY" --port 4001 > /tmp/tapiod-fastapi.log 2>&1 &
FASTAPI_PID=$!; ok "FastAPI gateway :4001  (PID $FASTAPI_PID)"

nohup npm start --prefix "$WEB" > /tmp/tapiod-nextjs.log 2>&1 &
NEXTJS_PID=$!; ok "Dashboard       :3000  (PID $NEXTJS_PID)"

echo "$LITELLM_PID $FASTAPI_PID $NEXTJS_PID" > /tmp/tapiod.pids

# ── Step 6: Health check ─────────────────────────────────────────────────────
step 6 "Health check"
echo "  Waiting for services to be ready..."
sleep 8

FA=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4001/api/metrics 2>/dev/null || echo "000")
LL=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4000/health 2>/dev/null || echo "000")
NJ=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")

[ "$FA" = "200" ] && ok "FastAPI  :4001" || warn "FastAPI not ready yet — check /tmp/tapiod-fastapi.log"
[ "$LL" = "200" ] && ok "LiteLLM  :4000" || warn "LiteLLM not ready yet — check /tmp/tapiod-litellm.log"
[ "$NJ" = "200" ] && ok "Dashboard :3000" || warn "Dashboard not ready yet — check /tmp/tapiod-nextjs.log"

echo ""
echo "  ────────────────────────────────────────────"
echo -e "  ${GREEN}TAPIOD is running!${RESET}"
echo ""
echo "  Dashboard  →  http://localhost:3000"
echo "  Playground →  http://localhost:3000/playground"
echo "  API        →  http://localhost:4001/api/agent/chat/completions"
echo ""
echo "  Logs:"
echo "    LiteLLM : tail -f /tmp/tapiod-litellm.log"
echo "    FastAPI : tail -f /tmp/tapiod-fastapi.log"
echo "    Next.js : tail -f /tmp/tapiod-nextjs.log"
echo ""
echo "  To stop all services:"
echo "    kill \$(cat /tmp/tapiod.pids)"
echo ""
