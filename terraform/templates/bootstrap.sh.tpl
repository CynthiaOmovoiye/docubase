#!/bin/bash
# EC2 first-boot bootstrap for docbase backend.
# Runs once at instance creation via user_data.
# All subsequent code deploys happen via SSM RunCommand — never re-run this.
#
# What it does:
#   1. Installs Docker, Docker Compose v2, git, jq
#   2. Fetches .env from SSM SecureString
#   3. Clones the repo using a GitHub deploy token from SSM
#   4. Starts docker-compose (backend + worker + supporting services)
#   5. Installs and starts the CloudWatch agent (system metrics)
#   6. Creates a systemd service so containers restart after reboots
set -euo pipefail

REGION="${aws_region}"
ENVIRONMENT="${environment}"
PROJECT="${project_name}"
GITHUB_REPO="${github_repo}"
APP_DIR="/home/ec2-user/docubase"
SSM_ENV_PARAM="${ssm_env_param}"
SSM_TOKEN_PARAM="${ssm_token_param}"
SSM_CW_PARAM="${ssm_cw_param}"
LOG_FILE="/var/log/docbase-bootstrap.log"

exec > >(tee -a "$LOG_FILE") 2>&1
echo "[bootstrap] Started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ─── 1. System packages ───────────────────────────────────────────────────────

echo "[bootstrap] Installing Docker, git, jq..."
dnf update -y
dnf install -y docker git jq

# Docker Compose v2 plugin
COMPOSE_VERSION="v2.27.1"
COMPOSE_ARCH=$(uname -m | sed 's/x86_64/x86_64/;s/aarch64/aarch64/')
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL \
  "https://github.com/docker/compose/releases/download/$${COMPOSE_VERSION}/docker-compose-linux-$${COMPOSE_ARCH}" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Enable and start Docker
systemctl enable --now docker
usermod -aG docker ec2-user

echo "[bootstrap] Docker $(docker --version) ready"

# ─── 2. Fetch secrets from SSM ───────────────────────────────────────────────

echo "[bootstrap] Fetching GitHub deploy token from SSM..."
GITHUB_TOKEN=$(aws ssm get-parameter \
  --name "$SSM_TOKEN_PARAM" \
  --with-decryption \
  --query "Parameter.Value" \
  --output text \
  --region "$REGION")

echo "[bootstrap] Fetching .env from SSM..."
APP_ENV=$(aws ssm get-parameter \
  --name "$SSM_ENV_PARAM" \
  --with-decryption \
  --query "Parameter.Value" \
  --output text \
  --region "$REGION")

# ─── 3. Clone repository ─────────────────────────────────────────────────────

echo "[bootstrap] Cloning $GITHUB_REPO..."
git clone \
  "https://x-access-token:$${GITHUB_TOKEN}@github.com/$${GITHUB_REPO}.git" \
  "$APP_DIR"

chown -R ec2-user:ec2-user "$APP_DIR"

# Write .env
echo "$APP_ENV" > "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

# ─── 4. Configure Docker log driver ──────────────────────────────────────────
# Switch containers to the awslogs driver so logs appear in CloudWatch.

cat >> "$APP_DIR/.env" <<ENVBLOCK

# Docker log driver — injected by bootstrap
DOCKER_LOG_DRIVER=awslogs
AWS_DEFAULT_REGION=$REGION
ENVIRONMENT=$ENVIRONMENT
ENVBLOCK

# ─── 5. Start application ─────────────────────────────────────────────────────

echo "[bootstrap] Starting docker compose..."
cd "$APP_DIR"
# Run as ec2-user so docker socket permissions are correct
sudo -u ec2-user docker compose up -d

echo "[bootstrap] Containers started:"
sudo -u ec2-user docker compose ps

# ─── 6. Systemd service (auto-restart on reboot) ──────────────────────────────

cat > /etc/systemd/system/docbase.service <<UNIT
[Unit]
Description=docbase Docker Compose application
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300
User=ec2-user
Group=ec2-user

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable docbase.service

# ─── 7. CloudWatch agent ──────────────────────────────────────────────────────

echo "[bootstrap] Installing CloudWatch agent..."
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
  CW_URL="https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/arm64/latest/amazon-cloudwatch-agent.rpm"
else
  CW_URL="https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm"
fi

curl -fsSL "$CW_URL" -o /tmp/amazon-cloudwatch-agent.rpm
rpm -U /tmp/amazon-cloudwatch-agent.rpm

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c "ssm:$${SSM_CW_PARAM}"

echo "[bootstrap] CloudWatch agent started"

# ─── Done ─────────────────────────────────────────────────────────────────────

echo "[bootstrap] Completed successfully at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[bootstrap] App dir: $APP_DIR"
echo "[bootstrap] Tail application logs: docker compose -f $APP_DIR/docker-compose.yml logs -f"
