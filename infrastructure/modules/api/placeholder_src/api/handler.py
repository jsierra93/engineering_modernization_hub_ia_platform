"""Placeholder handler for lambda api.

This stub exists only so that `infrastructure/modules/api` is a structurally
valid, plannable Terraform module before the real services/api Python build
is wired in (that build is happening in parallel, see PLAN.md task 1.6).

Replace by pointing the module's `lambda_source_dir` variable at the real
build output directory (see infrastructure/scripts/build_lambda.sh) - no
other Terraform change is needed. Module path (api.handler.handler)
matches the real services/api/src/api/handler.py's layout exactly, so the
`lambda_handler` variable's default works for both.
"""


def handler(event, context):
    return {
        "statusCode": 501,
        "body": "lambda api placeholder - real handler not deployed yet",
    }
