
#!/bin/bash
set -e

GATEWAY_DIR="$(cd "$(dirname "$0")/backend" && pwd)"
WEB_DIR="$(cd "$(dirname "$0")/frontend" && pwd)"

echo "Starting TAPIOD v2 stack..."

# Ensure Docker containers are up first
echo "Starting Docker containers..."
docker compose -f "$(dirname "$0")/docker-compose.yml" up -d
echo "Waiting for Redis, Qdrant, PostgreSQL to be ready..."
until docker exec gateway-redis redis-cli ping 2>/dev/null | grep -q PONG; do sleep 1; done
echo "  Redis: ready"
until docker exec gateway-postgres pg_isready -U litellm 2>/dev/null | grep -q "accepting"; do sleep 1; done
echo "  PostgreSQL: ready"
until curl -sf http://localhost:6333/readyz 2>/dev/null | grep -q "ok"; do sleep 1; done
echo "  Qdrant: ready"

cd "$GATEWAY_DIR"
source venv/bin/activate

nohup litellm --config litellm_config.yaml --port 4000 > /tmp/litellm.log 2>&1 &
echo "LiteLLM proxy starting on port 4000 (PID $!)"

nohup uvicorn main:app --port 4001 --host 0.0.0.0 > /tmp/fastapi.log 2>&1 &
echo "FastAPI gateway starting on port 4001 (PID $!)"

nohup node "$WEB_DIR/node_modules/next/dist/bin/next" start "$WEB_DIR" --port 3000 --hostname "::" > /tmp/nextjs.log 2>&1 &
echo "Next.js frontend starting on port 3000 (PID $!)"

echo ""
echo "Waiting for services to initialize..."
sleep 15

echo ""
echo "Status:"
curl -s http://localhost:4001/api/config > /dev/null && echo "  FastAPI:  OK" || echo "  FastAPI:  FAILED"
curl -s http://localhost:4000/health > /dev/null && echo "  LiteLLM:  OK" || echo "  LiteLLM:  FAILED"
curl -s -o /dev/null -w "" http://localhost:3000 && echo "  Next.js:  OK" || echo "  Next.js:  FAILED"
echo ""
echo "Open http://localhost:3000 in your browser."
