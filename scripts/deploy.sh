#!/bin/bash
# Static frontend to S3/CloudFront. API is separate (e.g. Docker on a host).
#
# Suggested order:
#   1. Local — make up, smoke UI/API, then make test (and lint if you use it)
#   2. AWS dev — ./scripts/deploy.sh dev
#   3. AWS prod — only after dev CloudFront + API URL are verified
#
# Prereq: S3 bucket docbase-terraform-state-<account> + DynamoDB docbase-terraform-locks
set -e

ENVIRONMENT=${1:-dev}
PROJECT_NAME=${2:-docbase}

echo "Deploying ${PROJECT_NAME} frontend to ${ENVIRONMENT}..."

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

if [ "$ENVIRONMENT" = "prod" ] && [ -f "prod.tfvars" ]; then
  TF_APPLY_CMD=(terraform apply -var-file=prod.tfvars -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve)
else
  TF_APPLY_CMD=(terraform apply -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve)
fi

echo "Applying Terraform (S3 + CloudFront)..."
"${TF_APPLY_CMD[@]}"

FRONTEND_BUCKET=$(terraform output -raw s3_frontend_bucket)
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id)
CUSTOM_URL=$(terraform output -raw custom_domain_url 2>/dev/null || true)

cd ../frontend

echo "Building Vite app..."
if [ -n "${DOCBASE_VITE_API_URL:-}" ]; then
  echo "VITE_API_URL=$DOCBASE_VITE_API_URL" > .env.production
  echo "DOCBASE_VITE_API_URL is set — Vite will bake VITE_API_URL into the client (check Network tab: API host should not be CloudFront)."
else
  rm -f .env.production
  echo "DOCBASE_VITE_API_URL not set — build uses same-origin /api/v1 (set GitHub Actions Variable DOCBASE_VITE_API_URL, then re-run deploy)."
fi

npm ci
npm run build
aws s3 sync ./dist "s3://$FRONTEND_BUCKET/" --delete

if [ -n "$DISTRIBUTION_ID" ] && [ "$DISTRIBUTION_ID" != "null" ]; then
  aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*" >/dev/null
fi

cd ..

echo ""
echo "Deployment complete."
echo "CloudFront: $(terraform -chdir=terraform output -raw cloudfront_url)"
if [ -n "$CUSTOM_URL" ]; then
  echo "Custom domain: $CUSTOM_URL"
fi
echo "Frontend bucket: $FRONTEND_BUCKET"
echo "Note: deploy the FastAPI API separately (Docker Compose, ECS, etc.); this stack is static UI only."
