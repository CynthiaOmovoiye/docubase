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
  description = "IAM instance profile to attach to your EC2 instance for CloudWatch permissions"
  value       = aws_iam_instance_profile.ec2_observability.name
}

output "cloudwatch_agent_ssm_parameter" {
  description = "SSM parameter name for the CloudWatch Agent config (used by install-cloudwatch-agent.sh)"
  value       = aws_ssm_parameter.cloudwatch_agent_config.name
}
