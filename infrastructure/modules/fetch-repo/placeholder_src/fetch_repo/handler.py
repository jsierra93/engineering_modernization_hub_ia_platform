"""Placeholder handler for lambda fetch_repo.

This stub exists only so that `infrastructure/modules/fetch-repo` is a
structurally valid, plannable Terraform module before the real
services/fetch_repo Python build (PLAN.md task 2.2) is wired in.

Replace by pointing the module's `lambda_source_dir` variable at the real
build output directory (mirroring infrastructure/scripts/build_lambda.sh's
pattern for lambda api) - no other Terraform change is needed, as long as
the real handler keeps living at fetch_repo.handler.handler (this module's
`lambda_handler` default).
"""


def handler(event, context):
    return {
        "statusCode": 501,
        "body": "lambda fetch_repo placeholder - real handler not deployed yet",
    }
