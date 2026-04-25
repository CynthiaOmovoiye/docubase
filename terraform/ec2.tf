# ─── EC2 Backend Server ───────────────────────────────────────────────────────
#
# Provisions the EC2 instance that runs the docbase FastAPI backend + ARQ worker
# via Docker Compose. All deploys happen via SSM RunCommand — no SSH required.
#
# First-time setup:
#   1. Add GitHub secrets/vars (see .github/workflows/deploy.yml comments)
#   2. Populate the two SSM SecureString parameters this file creates:
#        /docbase/{env}/github-deploy-token  — fine-grained GitHub PAT (repo read)
#        /docbase/{env}/app-env              — contents of your .env file
#   3. Push to main → GitHub Actions runs terraform apply → EC2 is provisioned
#      and bootstraps itself automatically.
#
# Migrating an existing EC2 instance:
#   If you have an existing instance you want Terraform to adopt instead of
#   creating a new one, run once before the first `terraform apply`:
#
#     terraform import aws_instance.backend <your-instance-id>
#     terraform import aws_eip.backend <your-eip-allocation-id>   # if you have one
#
#   Then set TF_VAR_ec2_key_name if your instance uses a key pair.

# ─── AMI ─────────────────────────────────────────────────────────────────────

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ─── Networking ───────────────────────────────────────────────────────────────

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "backend" {
  name        = "${local.name_prefix}-backend"
  description = "docbase backend API server"
  vpc_id      = data.aws_vpc.default.id
  tags        = merge(local.common_tags, { Name = "${local.name_prefix}-backend" })

  # API port — CloudFront proxies /api/* here
  ingress {
    description = "Backend API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # SSH — disabled by default; pass ssh_allowed_cidr to enable for debugging
  dynamic "ingress" {
    for_each = var.ssh_allowed_cidr != "" ? [1] : []
    content {
      description = "SSH (restricted)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [var.ssh_allowed_cidr]
    }
  }

  # All outbound (Docker pull, AWS APIs, git, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Elastic IP — stable address so CloudFront backend_origin_url never changes
resource "aws_eip" "backend" {
  domain = "vpc"
  tags   = merge(local.common_tags, { Name = "${local.name_prefix}-backend-eip" })
}

resource "aws_eip_association" "backend" {
  instance_id   = aws_instance.backend.id
  allocation_id = aws_eip.backend.id
}

# ─── IAM: add SSM Session Manager to the observability role ──────────────────
# The observability role already has CloudWatch + SSM GetParameter (for CW agent).
# These permissions enable SSM Session Manager (no-SSH shell) and allow the
# instance to pull its own .env and GitHub token from SSM.

resource "aws_iam_role_policy" "ec2_ssm_sessions" {
  name = "ssm-session-manager"
  role = aws_iam_role.ec2_observability.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SSMSessionManager"
        Effect = "Allow"
        Action = [
          "ssm:UpdateInstanceInformation",
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
        ]
        Resource = "*"
      },
      {
        Sid    = "ReadAppSecrets"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
        ]
        # Allow access to app-specific secrets only
        Resource = "arn:aws:ssm:*:*:parameter/docbase/${var.environment}/*"
      },
    ]
  })
}

# ─── SSM SecureString parameters ─────────────────────────────────────────────
# These are created as placeholders. Populate them once in the AWS Console or
# via the CLI — Terraform will never overwrite an existing value (lifecycle).

resource "aws_ssm_parameter" "github_deploy_token" {
  name        = "/docbase/${var.environment}/github-deploy-token"
  type        = "SecureString"
  value       = "REPLACE_ME"
  description = "Fine-grained GitHub PAT with repo Contents read access. Used by EC2 to git clone/pull."
  tags        = local.common_tags

  lifecycle {
    # Never overwrite once you've set the real value
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "app_env" {
  name        = "/docbase/${var.environment}/app-env"
  type        = "SecureString"
  value       = "# Paste your full .env file contents here"
  description = "docbase .env file. Paste the full contents of your .env into this parameter."
  tags        = local.common_tags

  lifecycle {
    ignore_changes = [value]
  }
}

# ─── EC2 Instance ─────────────────────────────────────────────────────────────

resource "aws_instance" "backend" {
  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = var.ec2_instance_type
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.backend.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_observability.name
  key_name               = var.ec2_key_name != "" ? var.ec2_key_name : null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    delete_on_termination = true
    encrypted             = true
  }

  # First-boot setup: installs Docker, clones repo, writes .env, starts compose.
  # This runs ONCE at creation — all subsequent deploys use SSM RunCommand.
  user_data = base64encode(templatefile("${path.module}/templates/bootstrap.sh.tpl", {
    aws_region      = "us-east-1"
    environment     = var.environment
    project_name    = var.project_name
    github_repo     = var.github_repo
    ssm_env_param   = aws_ssm_parameter.app_env.name
    ssm_token_param = aws_ssm_parameter.github_deploy_token.name
    ssm_cw_param    = aws_ssm_parameter.cloudwatch_agent_config.name
  }))

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-backend" })

  lifecycle {
    # Never replace the instance on code or AMI changes.
    # Code deploys happen via SSM RunCommand in CI/CD.
    # AMI updates: replace manually via console or `terraform taint` + apply.
    ignore_changes = [user_data, ami]
  }
}
