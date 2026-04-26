#!/bin/bash
# Install and configure the CloudWatch Agent on the EC2 host.
# Run this once after:
#   1. terraform apply (creates SSM parameter + IAM instance profile)
#   2. Attaching the IAM instance profile to this EC2 instance
#
# Usage:
#   ./scripts/install-cloudwatch-agent.sh [environment] [region]
#   ./scripts/install-cloudwatch-agent.sh prod us-east-1
# SSM path matches Terraform: /AmazonCloudWatch-<project_name>-<environment>-config
# If project_name in terraform.tfvars is not "docbase", set DOCBASE_PROJECT_NAME first.
set -euo pipefail

ENVIRONMENT=${1:-prod}
AWS_REGION=${2:-us-east-1}
# Must match terraform variable project_name (see aws_ssm_parameter.cloudwatch_agent_config).
PROJECT_NAME="${DOCBASE_PROJECT_NAME:-docbase}"
SSM_PARAM="/AmazonCloudWatch-${PROJECT_NAME}-${ENVIRONMENT}-config"

echo "Installing CloudWatch Agent for ${PROJECT_NAME} (${ENVIRONMENT}) in ${AWS_REGION}..."

# ── Install the agent ─────────────────────────────────────────────────────────
if command -v amazon-cloudwatch-agent-ctl &>/dev/null; then
  echo "CloudWatch Agent already installed — skipping download."
else
  ARCH=$(uname -m)
  if [ "$ARCH" = "aarch64" ]; then
    PKG="amazon-cloudwatch-agent.rpm"
    URL="https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/arm64/latest/${PKG}"
  else
    PKG="amazon-cloudwatch-agent.rpm"
    URL="https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/${PKG}"
  fi

  echo "Downloading CloudWatch Agent from ${URL}..."
  curl -fsSL "$URL" -o "/tmp/${PKG}"

  if command -v rpm &>/dev/null; then
    sudo rpm -U "/tmp/${PKG}"
  elif command -v dpkg &>/dev/null; then
    # Ubuntu/Debian — download the .deb variant instead
    DEB="amazon-cloudwatch-agent.deb"
    DEB_URL="https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/${DEB}"
    curl -fsSL "$DEB_URL" -o "/tmp/${DEB}"
    sudo dpkg -i "/tmp/${DEB}"
  else
    echo "ERROR: Unsupported package manager. Install the CloudWatch Agent manually." >&2
    exit 1
  fi
fi

# ── Fetch config from SSM and start the agent ─────────────────────────────────
echo "Fetching agent config from SSM: ${SSM_PARAM}"
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c "ssm:${SSM_PARAM}"

echo ""
echo "CloudWatch Agent installed and running."
echo "System metrics will appear in the 'Docbase/$(python3 -c "print('${ENVIRONMENT}'.title())")' namespace within 1–2 minutes."
echo ""
echo "Verify status:"
echo "  sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -m ec2 -a status"
