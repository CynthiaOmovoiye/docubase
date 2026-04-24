#!/usr/bin/env bash
# Expose the local FastAPI port (default 8000) as a public HTTPS URL so CloudFront-hosted
# UI can call it via DOCBASE_VITE_API_URL. Uses Cloudflare quick tunnel (preferred) or ngrok.
set -euo pipefail

PORT="${1:-8000}"
TARGET="http://127.0.0.1:${PORT}"

echo "docbase — public API tunnel"
echo "=========================="
echo "Target: ${TARGET}"
echo ""
echo "1. Start the stack first (from repo root), e.g.:"
echo "   docker compose up -d db redis && docker compose up backend"
echo ""
echo "2. Copy the https://.... URL printed below (origin only, no path)."
echo "3. GitHub → Settings → Variables → DOCBASE_VITE_API_URL = that origin"
echo "4. In backend .env set CORS_ALLOWED_ORIGINS to your CloudFront URL, e.g.:"
echo "   CORS_ALLOWED_ORIGINS=https://dxxxx.cloudfront.net"
echo "5. Re-run the Deploy workflow (or ./scripts/deploy.sh dev with DOCBASE_VITE_API_URL set)."
echo ""
echo "Note: Quick tunnel URLs change each run. For a stable URL use AWS (e.g. Lightsail)"
echo "      or a named Cloudflare tunnel — see docs/BACKEND_QUICK_CONNECT.md"
echo ""

if command -v cloudflared >/dev/null 2>&1; then
  exec cloudflared tunnel --url "${TARGET}"
fi

if command -v ngrok >/dev/null 2>&1; then
  exec ngrok http "${PORT}"
fi

echo "Neither cloudflared nor ngrok is installed."
echo ""
echo "  brew install cloudflared   # recommended"
echo "  # or: https://ngrok.com/download"
exit 1
