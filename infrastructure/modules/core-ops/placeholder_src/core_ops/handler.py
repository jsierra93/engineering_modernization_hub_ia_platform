"""Placeholder handler for lambda core_ops.

This stub exists only so that `infrastructure/modules/core-ops` is a
structurally valid, plannable Terraform module before the real
services/core_ops Python build (PLAN.md tasks 2.4/2.5/2.6) is wired in.

Replace by pointing the module's `lambda_source_dir` variable at the real
build output directory (mirroring infrastructure/scripts/build_lambda.sh's
pattern for lambda api) - no other Terraform change is needed, as long as
the real handler keeps living at core_ops.handler.handler (this module's
`lambda_handler` default).

Reminder (CLAUDE.md invariant #1): this package, and whatever replaces it,
must never import a Bedrock client.
"""


def handler(event, context):
    return {
        "statusCode": 501,
        "body": "lambda core_ops placeholder - real handler not deployed yet",
    }
