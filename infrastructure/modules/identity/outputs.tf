output "user_pool_id" {
  value = aws_cognito_user_pool.users.id
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.users.arn
}

output "issuer_url" {
  description = "The JWT `iss` claim value every token from this pool carries -- what api's JWT authorizer (task 4.2-tf) validates against. See var.issuer_base_url's own comment for why this isn't always the real AWS hostname."
  value = (
    var.issuer_base_url != null
    ? "${var.issuer_base_url}/${aws_cognito_user_pool.users.id}"
    : "https://cognito-idp.${data.aws_region.current.region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
  )
}

output "cli_client_id" {
  value = aws_cognito_user_pool_client.cli.id
}

output "backstage_client_id" {
  value = aws_cognito_user_pool_client.backstage.id
}

output "backstage_client_secret" {
  value     = aws_cognito_user_pool_client.backstage.client_secret
  sensitive = true
}

output "hosted_ui_domain" {
  value = aws_cognito_user_pool_domain.hosted_ui.domain
}

data "aws_region" "current" {}
