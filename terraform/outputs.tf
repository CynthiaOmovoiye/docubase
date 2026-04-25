output "cloudfront_url" {
  description = "URL of the CloudFront distribution"
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.main.id
}

output "s3_frontend_bucket" {
  description = "Name of the S3 bucket for frontend static assets"
  value       = aws_s3_bucket.frontend.id
}

output "custom_domain_url" {
  description = "Root URL when a custom domain is configured"
  value       = var.use_custom_domain ? "https://${var.root_domain}" : ""
}

output "cloudwatch_dashboard_url" {
  description = "CloudWatch observability dashboard URL"
  value       = "https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "ec2_instance_profile_name" {
  description = "IAM instance profile attached to the EC2 instance"
  value       = aws_iam_instance_profile.ec2_observability.name
}

output "cloudwatch_agent_ssm_parameter" {
  description = "SSM parameter name for the CloudWatch Agent config"
  value       = aws_ssm_parameter.cloudwatch_agent_config.name
}

output "ec2_instance_id" {
  description = "EC2 instance ID — used by GitHub Actions for SSM RunCommand backend deploys"
  value       = aws_instance.backend.id
}

output "ec2_public_ip" {
  description = "Elastic IP address of the backend server"
  value       = aws_eip.backend.public_ip
}

output "ec2_public_dns" {
  description = "Public DNS hostname of the EC2 Elastic IP — use THIS as DOCBASE_BACKEND_ORIGIN_URL (CloudFront does not accept raw IPs)"
  value       = aws_eip.backend.public_dns
}

output "backend_api_url" {
  description = "Direct URL to the backend API (before CloudFront)"
  value       = "http://${aws_eip.backend.public_ip}:8000"
}

output "github_deploy_token_ssm_param" {
  description = "SSM parameter to populate with your GitHub fine-grained PAT"
  value       = aws_ssm_parameter.github_deploy_token.name
}

output "app_env_ssm_param" {
  description = "SSM parameter to populate with your .env file contents"
  value       = aws_ssm_parameter.app_env.name
}
