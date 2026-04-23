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
