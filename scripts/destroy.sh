#!/bin/bash
set -e

if [ $# -eq 0 ]; then
  echo "Error: environment parameter is required"
  echo "Usage: $0 <environment> [project_name]"
  echo "Example: $0 dev"
  echo "Environments: dev, test, prod"
  exit 1
fi

ENVIRONMENT=$1
PROJECT_NAME=${2:-docbase}

echo "Preparing to destroy ${PROJECT_NAME}-${ENVIRONMENT} frontend infrastructure..."

cd "$(dirname "$0")/../terraform"

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${DEFAULT_AWS_REGION:-us-east-1}

terraform init -input=false \
  -backend-config="bucket=docbase-terraform-state-${AWS_ACCOUNT_ID}" \
  -backend-config="key=${ENVIRONMENT}/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=docbase-terraform-locks" \
  -backend-config="encrypt=true"

if ! terraform workspace list | grep -q "$ENVIRONMENT"; then
  echo "Error: workspace '$ENVIRONMENT' does not exist"
  terraform workspace list
  exit 1
fi

terraform workspace select "$ENVIRONMENT"

FRONTEND_BUCKET="${PROJECT_NAME}-${ENVIRONMENT}-frontend-${AWS_ACCOUNT_ID}"

if aws s3 ls "s3://$FRONTEND_BUCKET" 2>/dev/null; then
  echo "Emptying $FRONTEND_BUCKET..."
  aws s3 rm "s3://$FRONTEND_BUCKET" --recursive
else
  echo "Frontend bucket not found or already empty"
fi

if [ "$ENVIRONMENT" = "prod" ] && [ -f "prod.tfvars" ]; then
  terraform destroy -var-file=prod.tfvars -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve
else
  terraform destroy -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve
fi

echo "Infrastructure for ${ENVIRONMENT} has been destroyed."
echo "To remove the workspace: terraform workspace select default && terraform workspace delete $ENVIRONMENT"
