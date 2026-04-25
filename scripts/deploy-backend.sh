#!/bin/bash
# Backend deploy script — runs on EC2 via SSM RunCommand after git pull.
#
# Called by .github/workflows/deploy.yml after the code is updated.
# Also safe to run manually on the EC2 instance for debugging:
#   bash scripts/deploy-backend.sh dev us-east-1
#
# What it does:
#   1. Fetches the latest .env from SSM Parameter Store
#   2. Appends CloudWatch log driver config
#   3. Rebuilds and restarts backend + worker containers
set -euo pipefail

ENVIRONMENT=${1:-dev}
REGION=${2:-us-east-1}

echo "[deploy-backend] environment=$ENVIRONMENT region=$REGION commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

# ─── Refresh .env from SSM ────────────────────────────────────────────────────
echo "[deploy-backend] Fetching .env from SSM..."
aws ssm get-parameter \
  --name "/docbase/${ENVIRONMENT}/app-env" \
  --with-decryption \
  --query "Parameter.Value" \
  --output text \
  --region "$REGION" > .env

# Append Docker log driver config so containers ship logs to CloudWatch
cat >> .env <<APPEND

# Injected by deploy-backend.sh
DOCKER_LOG_DRIVER=awslogs
AWS_DEFAULT_REGION=${REGION}
ENVIRONMENT=${ENVIRONMENT}
APPEND

# ─── Rebuild and restart ──────────────────────────────────────────────────────
echo "[deploy-backend] Rebuilding backend + worker..."
docker compose up -d --build backend worker

echo "[deploy-backend] Running containers:"
docker compose ps backend worker

echo "[deploy-backend] Done at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
