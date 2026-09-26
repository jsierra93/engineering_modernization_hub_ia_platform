# infrastructure/modules/persistence
#
# Task 1.4-tf (PLAN.md). Deterministic-zone storage only:
#   - DynamoDB `runs` table, keyed by run_id, with GSIs by `status` and by `requested_by`
#   - DynamoDB `events` table, keyed by run_id + monotonic sequence
#   - S3 bucket for ws/vN workspaces, JUnit results, diffs and reports
#
# Nothing here grants access to anything — IAM policies that reference these
# resources live in the modules that need them (orchestration, api, and later
# core_ops / agent_phase / fetch_repo per CLAUDE.md's per-service IAM philosophy).

resource "aws_dynamodb_table" "runs" {
  name         = "${var.name_prefix}-runs"
  billing_mode = var.runs_table_billing_mode
  # NOTE: hash_key/range_key are deprecated in favor of key_schema inside
  # global_secondary_index/local_secondary_index blocks (see those below) --
  # but AWS provider v6.66.0 does NOT accept a table-level key_schema block
  # for the primary key, confirmed by `terraform validate`, not assumed.
  # hash_key/range_key remain correct here.
  hash_key = "run_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "requested_by"
    type = "S"
  }

  # Sort key shared by both GSIs so lookups can be ordered by recency.
  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi_status"
    projection_type = "ALL"

    key_schema {
      attribute_name = "status"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "created_at"
      key_type       = "RANGE"
    }
  }

  global_secondary_index {
    name            = "gsi_requested_by"
    projection_type = "ALL"

    key_schema {
      attribute_name = "requested_by"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "created_at"
      key_type       = "RANGE"
    }
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-runs"
  })
}

resource "aws_dynamodb_table" "events" {
  name         = "${var.name_prefix}-events"
  billing_mode = var.runs_table_billing_mode
  hash_key     = "run_id"
  range_key    = "seq"

  attribute {
    name = "run_id"
    type = "S"
  }

  # Monotonic per-run sequence number, assigned by the writer (core_ops / orchestration).
  attribute {
    name = "seq"
    type = "N"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-events"
  })
}

resource "aws_s3_bucket" "workspaces" {
  bucket        = "${var.name_prefix}-workspaces"
  force_destroy = var.s3_force_destroy

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-workspaces"
  })
}

resource "aws_s3_bucket_versioning" "workspaces" {
  bucket = aws_s3_bucket.workspaces.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "workspaces" {
  bucket = aws_s3_bucket.workspaces.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "workspaces" {
  bucket = aws_s3_bucket.workspaces.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Bucket layout convention (enforced by application code, not by Terraform):
#   ws/<run_id>/vN/...      - workspace snapshots per phase
#   ws/<run_id>/junit/...   - JUnit XML per check
#   ws/<run_id>/diffs/...   - generated diffs
#   ws/<run_id>/reports/... - final reports
