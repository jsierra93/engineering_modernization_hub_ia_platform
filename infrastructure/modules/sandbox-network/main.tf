# infrastructure/modules/sandbox-network
#
# Task 2.1-tf (PLAN.md). Minimal PUBLIC network for the ephemeral Fargate
# sandbox that executes named checks (install/unit_tests/lint) against a
# workspace fetched from S3. "Public" here matches the design artifact's
# "modo public": one public subnet with an internet gateway, egress
# restricted to port 443 only, ~$0 fixed cost. No VPC endpoints, no NAT
# gateway. The private mode (VPC endpoints, no internet egress at all) is
# Plus item P.2 -- not built here. One AZ is enough for a prototype; this
# module does not build multi-AZ redundancy nobody asked for.
#
# CLAUDE.md invariant #8 drives every choice in the task definition below:
# the sandbox has NO task role (no AWS credentials of any kind reach the
# running container -- only an execution role exists, and that role is used
# by the ECS agent itself to pull the image and ship logs, never exposed
# inside the container process), NO environment variables baked into the
# definition (check-specific input arrives via ECS RunTask
# containerOverrides at invocation time -- see
# infrastructure/modules/orchestration's ASL), and non-root (enforced by
# the sandbox image itself, built under sandbox/ by a parallel task -- this
# task definition does not set a "user" override and must not need to).
#
# This module does not push an image to the ECR repository it creates --
# that is the parallel sandbox-image task's job (a `docker push`, by hand
# or by a script, outside Terraform's scope). var.sandbox_image_tag
# defaults to a tag that does not exist yet on purpose; the task definition
# is still valid Terraform, it just cannot successfully RunTask until an
# image is pushed under that tag.

locals {
  az = coalesce(var.availability_zone, "${var.aws_region}a")
}

resource "aws_vpc" "sandbox" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox-vpc"
  })
}

resource "aws_internet_gateway" "sandbox" {
  vpc_id = aws_vpc.sandbox.id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox-igw"
  })
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.sandbox.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = local.az
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox-public"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.sandbox.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.sandbox.id
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox-public-rt"
  })
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Egress restricted to port 443 only -- the sandbox only ever speaks HTTPS
# (fetching its own workspace via a presigned S3 URL, package indexes for
# the `install` check). No ingress at all: nothing ever calls into it.
resource "aws_security_group" "sandbox" {
  name        = "${var.name_prefix}-sandbox-sg"
  description = "Egress-only, port 443, for the ephemeral check-runner sandbox."
  vpc_id      = aws_vpc.sandbox.id

  egress {
    description = "HTTPS egress only"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox-sg"
  })
}

resource "aws_ecr_repository" "sandbox" {
  name                 = "${var.name_prefix}-sandbox"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox"
  })
}

resource "aws_ecs_cluster" "sandbox" {
  name = "${var.name_prefix}-sandbox"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox"
  })
}

resource "aws_cloudwatch_log_group" "sandbox" {
  name              = "/aws/ecs/${var.name_prefix}-sandbox"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# Execution role only, used by the ECS agent to pull the image from ECR and
# ship container logs to CloudWatch -- never exposed to the running
# container's process. This is NOT a task role: aws_ecs_task_definition
# below sets no task_role_arn at all, which is invariant #8's control (no
# AWS credentials of any kind reach the sandbox).
data "aws_iam_policy_document" "ecs_task_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-sandbox-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume_role.json

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox-execution-role"
  })
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_ecs_task_definition" "sandbox" {
  family                   = "${var.name_prefix}-sandbox"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.sandbox_cpu
  memory                   = var.sandbox_memory
  execution_role_arn       = aws_iam_role.execution.arn
  # No task_role_arn -- invariant #8: the sandbox holds no AWS credentials
  # of any kind.

  runtime_platform {
    cpu_architecture        = var.sandbox_architecture == "arm64" ? "ARM64" : "X86_64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name      = var.sandbox_container_name
      image     = "${aws_ecr_repository.sandbox.repository_url}:${var.sandbox_image_tag}"
      essential = true
      # Deliberately no "environment" key -- check-specific input (which
      # check to run, where its workspace/results live) arrives exclusively
      # via ECS RunTask containerOverrides at invocation time (see
      # infrastructure/modules/orchestration's ASL Baseline state), never
      # baked into this static task definition.
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.sandbox.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "sandbox"
        }
      }
    }
  ])

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-sandbox"
  })
}
