# CloudWatch observability: IAM, log groups, metric filters, alarms, dashboard.
# The EC2 instance is managed outside Terraform — attach the instance profile
# created here to your instance manually (or via your EC2 bootstrap script).
# After attaching, run scripts/install-cloudwatch-agent.sh on the EC2 host.

# ─── IAM: EC2 → CloudWatch ────────────────────────────────────────────────────

resource "aws_iam_role" "ec2_observability" {
  name = "${local.name_prefix}-ec2-observability"
  tags = local.common_tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ec2_observability" {
  name = "cloudwatch-logs-and-metrics"
  role = aws_iam_role.ec2_observability.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
          "logs:DescribeLogGroups",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
        ]
        Resource = "arn:aws:ssm:*:*:parameter/AmazonCloudWatch-*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeTags",
          "ec2:DescribeInstances",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_instance_profile" "ec2_observability" {
  name = "${local.name_prefix}-ec2-observability"
  role = aws_iam_role.ec2_observability.name
  tags = local.common_tags
}

# ─── CloudWatch Agent config (SSM) ───────────────────────────────────────────
# System metrics only — application logs are shipped via Docker awslogs driver.
# No InstanceId dimension: keeps the dashboard simple for a single-EC2 setup.

resource "aws_ssm_parameter" "cloudwatch_agent_config" {
  name      = "/AmazonCloudWatch-${local.name_prefix}-config"
  type      = "String"
  overwrite = true
  tags      = local.common_tags

  value = jsonencode({
    agent = {
      metrics_collection_interval = 60
      run_as_user                 = "cwagent"
    }
    metrics = {
      namespace = "Docbase/${title(var.environment)}"
      metrics_collected = {
        cpu = {
          measurement                 = ["cpu_usage_idle", "cpu_usage_user", "cpu_usage_system"]
          metrics_collection_interval = 60
          totalcpu                    = true
        }
        mem = {
          measurement                 = ["mem_used_percent", "mem_available_percent"]
          metrics_collection_interval = 60
        }
        disk = {
          measurement              = ["used_percent"]
          metrics_collection_interval = 60
          resources                = ["/", "/var/lib/docker"]
          ignore_file_system_types = ["sysfs", "devtmpfs", "tmpfs"]
        }
        net = {
          measurement                 = ["bytes_sent", "bytes_recv"]
          metrics_collection_interval = 60
          resources                   = ["*"]
        }
        netstat = {
          measurement                 = ["tcp_established", "tcp_time_wait"]
          metrics_collection_interval = 60
        }
      }
    }
  })
}

# ─── Log Groups ───────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/docbase/${var.environment}/backend"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/docbase/${var.environment}/worker"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

# ─── Metric Filters ───────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_metric_filter" "chat_latency" {
  name           = "${local.name_prefix}-chat-latency"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.event = \"chat_latency_metrics\" }"

  metric_transformation {
    name      = "ChatLatencyMs"
    namespace = "Docbase/${title(var.environment)}/Chat"
    value     = "$.total_ms"
    unit      = "Milliseconds"
  }
}

resource "aws_cloudwatch_log_metric_filter" "workspace_chat_latency" {
  name           = "${local.name_prefix}-workspace-chat-latency"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.event = \"workspace_chat_latency_metrics\" }"

  metric_transformation {
    name      = "WorkspaceChatLatencyMs"
    namespace = "Docbase/${title(var.environment)}/Chat"
    value     = "$.total_ms"
    unit      = "Milliseconds"
  }
}

resource "aws_cloudwatch_log_metric_filter" "budget_exceeded" {
  name           = "${local.name_prefix}-budget-exceeded"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.budget_exceeded = true }"

  metric_transformation {
    name      = "BudgetExceededCount"
    namespace = "Docbase/${title(var.environment)}/Chat"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "retrieval_chunks" {
  name           = "${local.name_prefix}-retrieval-chunks"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.event = \"retrieval_complete\" }"

  metric_transformation {
    name      = "RetrievalChunksReturned"
    namespace = "Docbase/${title(var.environment)}/Retrieval"
    value     = "$.chunks_returned"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "missing_evidence" {
  name           = "${local.name_prefix}-missing-evidence"
  log_group_name = aws_cloudwatch_log_group.backend.name
  # Count retrievals where lexical search returned nothing (proxy for missing evidence)
  pattern        = "{ $.event = \"retrieval_complete\" && $.lexical_hits = 0 }"

  metric_transformation {
    name      = "MissingEvidenceCount"
    namespace = "Docbase/${title(var.environment)}/Retrieval"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "app_errors" {
  name           = "${local.name_prefix}-app-errors"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "{ $.level = \"error\" }"

  metric_transformation {
    name      = "AppErrorCount"
    namespace = "Docbase/${title(var.environment)}/Errors"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "worker_errors" {
  name           = "${local.name_prefix}-worker-errors"
  log_group_name = aws_cloudwatch_log_group.worker.name
  pattern        = "{ $.level = \"error\" }"

  metric_transformation {
    name      = "WorkerErrorCount"
    namespace = "Docbase/${title(var.environment)}/Errors"
    value     = "1"
    unit      = "Count"
  }
}

# ─── SNS Alarm Notifications ──────────────────────────────────────────────────

resource "aws_sns_topic" "alarms" {
  count = var.alarm_email != "" ? 1 : 0
  name  = "${local.name_prefix}-alarms"
  tags  = local.common_tags
}

resource "aws_sns_topic_subscription" "alarm_email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarm_actions = var.alarm_email != "" ? [aws_sns_topic.alarms[0].arn] : []
}

# ─── Alarms ───────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "chat_p95_latency" {
  alarm_name          = "${local.name_prefix}-chat-p95-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ChatLatencyMs"
  namespace           = "Docbase/${title(var.environment)}/Chat"
  period              = 300
  extended_statistic  = "p95"
  threshold           = 5000
  alarm_description   = "P95 chat latency > 5s for 3 consecutive 5-minute windows"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "budget_exceeded_rate" {
  alarm_name          = "${local.name_prefix}-budget-exceeded-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "BudgetExceededCount"
  namespace           = "Docbase/${title(var.environment)}/Chat"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "More than 5 latency budget breaches in a 5-minute window"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "app_error_rate" {
  alarm_name          = "${local.name_prefix}-app-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "AppErrorCount"
  namespace           = "Docbase/${title(var.environment)}/Errors"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "More than 10 application errors in a 5-minute window"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "zero_retrieval_chunks" {
  alarm_name          = "${local.name_prefix}-zero-retrieval-chunks"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "RetrievalChunksReturned"
  namespace           = "Docbase/${title(var.environment)}/Retrieval"
  period              = 300
  statistic           = "Average"
  threshold           = 1
  alarm_description   = "Average retrieved chunks near zero — RAG pipeline may be broken"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = local.common_tags
}

# ─── Dashboard ────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.name_prefix}-observability"

  dashboard_body = jsonencode({
    widgets = [
      # Row 1: Chat Latency
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Chat Latency (p50 / p95 / p99)"
          view    = "timeSeries"
          stacked = false
          region  = "us-east-1"
          period  = 300
          yAxis   = { left = { min = 0, label = "ms" } }
          metrics = [
            ["Docbase/${title(var.environment)}/Chat", "ChatLatencyMs", { stat = "p50", label = "Single-twin p50" }],
            [".", ".", { stat = "p95", label = "Single-twin p95" }],
            [".", ".", { stat = "p99", label = "Single-twin p99" }],
            ["Docbase/${title(var.environment)}/Chat", "WorkspaceChatLatencyMs", { stat = "p50", label = "Workspace p50" }],
            [".", ".", { stat = "p95", label = "Workspace p95" }],
          ]
        }
      },
      # Row 1: Budget Breaches
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Latency Budget Breaches"
          view    = "timeSeries"
          stacked = false
          region  = "us-east-1"
          period  = 300
          yAxis   = { left = { min = 0, label = "count" } }
          metrics = [
            ["Docbase/${title(var.environment)}/Chat", "BudgetExceededCount", { stat = "Sum", label = "Budget exceeded", color = "#d62728" }],
          ]
        }
      },
      # Row 2: RAG Retrieval
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "RAG — Chunks Retrieved"
          view    = "timeSeries"
          stacked = false
          region  = "us-east-1"
          period  = 300
          yAxis   = { left = { min = 0, label = "chunks" } }
          metrics = [
            ["Docbase/${title(var.environment)}/Retrieval", "RetrievalChunksReturned", { stat = "Average", label = "avg chunks" }],
            [".", ".", { stat = "Minimum", label = "min chunks" }],
          ]
        }
      },
      # Row 2: Missing Evidence
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "RAG — Missing Evidence Events"
          view    = "timeSeries"
          stacked = false
          region  = "us-east-1"
          period  = 300
          yAxis   = { left = { min = 0, label = "count" } }
          metrics = [
            ["Docbase/${title(var.environment)}/Retrieval", "MissingEvidenceCount", { stat = "Sum", label = "missing evidence", color = "#ff7f0e" }],
          ]
        }
      },
      # Row 3: Errors
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title   = "Application Errors"
          view    = "timeSeries"
          stacked = true
          region  = "us-east-1"
          period  = 300
          yAxis   = { left = { min = 0, label = "count" } }
          metrics = [
            ["Docbase/${title(var.environment)}/Errors", "AppErrorCount", { stat = "Sum", label = "API errors", color = "#d62728" }],
            [".", "WorkerErrorCount", { stat = "Sum", label = "Worker errors", color = "#e377c2" }],
          ]
        }
      },
      # Row 3: EC2 CPU
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title   = "EC2 CPU Utilisation"
          view    = "timeSeries"
          stacked = false
          region  = "us-east-1"
          period  = 60
          yAxis   = { left = { min = 0, max = 100, label = "%" } }
          metrics = [
            ["Docbase/${title(var.environment)}", "cpu_usage_user", { stat = "Average", label = "user" }],
            [".", "cpu_usage_system", { stat = "Average", label = "system" }],
          ]
        }
      },
      # Row 4: Memory
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 12
        height = 6
        properties = {
          title   = "EC2 Memory Used"
          view    = "timeSeries"
          stacked = false
          region  = "us-east-1"
          period  = 60
          yAxis   = { left = { min = 0, max = 100, label = "%" } }
          metrics = [
            ["Docbase/${title(var.environment)}", "mem_used_percent", { stat = "Average", label = "memory used %" }],
          ]
        }
      },
      # Row 4: Disk
      {
        type   = "metric"
        x      = 12
        y      = 18
        width  = 12
        height = 6
        properties = {
          title   = "EC2 Disk Used"
          view    = "timeSeries"
          stacked = false
          region  = "us-east-1"
          period  = 60
          yAxis   = { left = { min = 0, max = 100, label = "%" } }
          metrics = [
            ["Docbase/${title(var.environment)}", "disk_used_percent", { stat = "Average", label = "/ disk %" }],
          ]
        }
      },
      # Row 5: Alarm Status
      {
        type   = "alarm"
        x      = 0
        y      = 24
        width  = 24
        height = 4
        properties = {
          title  = "Alarm Status"
          alarms = [
            aws_cloudwatch_metric_alarm.chat_p95_latency.arn,
            aws_cloudwatch_metric_alarm.budget_exceeded_rate.arn,
            aws_cloudwatch_metric_alarm.app_error_rate.arn,
            aws_cloudwatch_metric_alarm.zero_retrieval_chunks.arn,
          ]
        }
      },
      # Row 6: Log Insights — Recent Errors
      {
        type   = "log"
        x      = 0
        y      = 28
        width  = 24
        height = 6
        properties = {
          title         = "Recent Errors (last 1h)"
          view          = "table"
          region        = "us-east-1"
          logGroupNames = [aws_cloudwatch_log_group.backend.name]
          query         = "fields @timestamp, event, error | filter level = 'error' | sort @timestamp desc | limit 50"
        }
      },
    ]
  })
}
