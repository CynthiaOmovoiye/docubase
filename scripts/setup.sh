#!/bin/bash
# First-time local setup.
# Run once after cloning the repo.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "Setting up Digital Twin Platform for local development..."

# 1. Copy env template
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — fill in your values."
else
  echo ".env already exists, skipping copy."
fi

# 2. Ensure API can load Settings (placeholder secrets are rejected at import time)
python3 scripts/ensure_dev_secrets.py

# 3. Check Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "ERROR: Docker is not running. Start Docker and try again."
  exit 1
fi

# 4. Start the stack
echo "Starting local stack..."
docker compose up --build -d

# 5. Wait for DB to be healthy
echo "Waiting for database..."
sleep 5

# 6. Run migrations
echo "Running migrations..."
docker compose exec backend alembic upgrade head

echo ""
echo "Setup complete."
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  API docs: http://localhost:8000/api/docs"
echo ""
echo "If register still fails, check: docker compose logs backend --tail 50"
echo ""
