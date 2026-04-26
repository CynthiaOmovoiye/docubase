variable "project_name" {
  description = "Name prefix for all resources"
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, prod."
  }
}

variable "use_custom_domain" {
  description = "Attach a custom domain to CloudFront"
  type        = bool
  default     = false
}

variable "root_domain" {
  description = "Apex domain name, e.g. mydomain.com"
  type        = string
  default     = ""
}

variable "backend_origin_url" {
  description = "Public hostname of the backend API server, e.g. ec2-1-2-3-4.compute-1.amazonaws.com or api.mydomain.com. No scheme, no trailing slash."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 30
  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.log_retention_days)
    error_message = "log_retention_days must be a valid CloudWatch retention value."
  }
}

variable "alarm_email" {
  description = "Email address for CloudWatch alarm notifications. Leave empty to skip SNS/email setup."
  type        = string
  default     = ""
}

# ─── EC2 ─────────────────────────────────────────────────────────────────────

variable "ec2_instance_type" {
  description = "EC2 instance type for the backend server."
  type        = string
  default     = "t3.small"
}

variable "ec2_key_name" {
  description = "EC2 key pair name for emergency SSH access. Leave empty to disable SSH key auth (SSM Session Manager is used for all normal access)."
  type        = string
  default     = ""
}

variable "ssh_allowed_cidr" {
  description = "CIDR block allowed to reach port 22. WARNING: 0.0.0.0/0 exposes SSH to the public internet. Empty string disables the SSH ingress rule entirely (recommended; use SSM Session Manager instead)."
  type        = string
  default     = "0.0.0.0/0"
}

variable "github_repo" {
  description = "GitHub repository in owner/name format, e.g. 'CynthiaOmovoiye/docubase'. Used by the EC2 bootstrap script to git clone."
  type        = string
  default     = "CynthiaOmovoiye/docubase"
}
