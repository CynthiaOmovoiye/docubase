#!/bin/bash
# Scan the repo for accidentally committed secrets.
# Run this before committing or as part of CI.

set -e

echo "Scanning for secrets..."

ERRORS=0

# Check for .env files that should never be committed
if git ls-files | grep -qE '(^|/)\.env($|\.)'; then
  echo "ERROR: .env file found in git index. Remove it immediately."
  ERRORS=$((ERRORS + 1))
fi

# Check for common secret patterns in tracked files
PATTERNS=(
  'sk-[a-zA-Z0-9]{20,}'
  'ghp_[a-zA-Z0-9]{36}'
  'glpat-[a-zA-Z0-9-]{20,}'
  'AKIA[0-9A-Z]{16}'
  '-----BEGIN (RSA |EC )?PRIVATE KEY-----'
  'api_key\s*[=:]\s*["\x27][a-zA-Z0-9_-]{20,}'
  'password\s*[=:]\s*["\x27][^\s"\x27]{8,}'
)

for pattern in "${PATTERNS[@]}"; do
  matches=$(git grep -l -P "$pattern" -- ':!*.sh' ':!check-secrets.sh' 2>/dev/null || true)
  if [ -n "$matches" ]; then
    echo "WARNING: Possible secret pattern found in: $matches"
    ERRORS=$((ERRORS + 1))
  fi
done

if [ $ERRORS -eq 0 ]; then
  echo "No secrets found. Clean."
  exit 0
else
  echo "$ERRORS issue(s) found. Review before committing."
  exit 1
fi
