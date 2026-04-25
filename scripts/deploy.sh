#!/bin/bash
# Emergency / local manual frontend deploy to S3 + CloudFront.
#
# Normal deployments are fully automated via GitHub Actions (.github/workflows/deploy.yml).
# Push to main → Actions runs Terraform + frontend + backend (SSM) automatically.
#
# Only use this script when you need to force a frontend-only re-deploy locally
# without triggering a full CI run (e.g. debugging a CloudFront config issue).
#
# Usage:
#   ./scripts/deploy.sh [environment] [project_name]
#   ./scripts/deploy.sh dev docbase
set -e

ENVIRONMENT=${1:-dev}
PROJECT_NAME=${2:-docbase}

echo "Manual frontend-only deploy: ${PROJECT_NAME} → ${ENVIRONMENT}"
echo "Note: Backend is deployed automatically via GitHub Actions on push to main."
echo ""

cd "$(dirname "$0")/.."

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${DEFAULT_AWS_REGION:-us-east-1}

cd terraform
terraform init -input=false \
  -backend-config="bucket=docbase-terraform-state-${AWS_ACCOUNT_ID}" \
  -backend-config="key=${ENVIRONMENT}/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=docbase-terraform-locks" \
  -backend-config="encrypt=true"

if ! terraform workspace list | grep -q "$ENVIRONMENT"; then
  terraform workspace new "$ENVIRONMENT"
else
  terraform workspace select "$ENVIRONMENT"
fi

FRONTEND_BUCKET=$(terraform output -raw s3_frontend_bucket)
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id)

cd ../frontend

echo "Building Vite app..."
if [ -n "${DOCBASE_VITE_API_URL:-}" ]; then
  echo "VITE_API_URL=$DOCBASE_VITE_API_URL" > .env.production
fi

npm ci
npm run build

aws s3 sync ./dist "s3://$FRONTEND_BUCKET/" --delete

if [ -n "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "null" ]; then
  aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" >/dev/null
  echo "CloudFront cache invalidated."
fi

cd ..

echo ""
echo "Frontend deploy complete."
echo "CloudFront: $(terraform -chdir=terraform output -raw cloudfront_url)"
