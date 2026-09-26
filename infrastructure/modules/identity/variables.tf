variable "name_prefix" {
  description = "Prefix applied to all resource names created by this module (e.g. \"modhub-personal\")."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "backstage_callback_urls" {
  description = <<-EOT
    OAuth2 authorization-code callback URLs for the modhub-backstage app
    client (Fase 5's OIDC login). Backstage has no Cognito-specific auth
    provider -- apps/backstage/packages/backend registers Cognito through
    the GENERIC oidc provider (id "oidc"), whose callback path is
    .../api/auth/oidc/handler/frame. Defaults to the localhost dev-mode
    URL; override once a real Backstage host exists.
  EOT
  type        = list(string)
  default     = ["http://localhost:7007/api/auth/oidc/handler/frame"]
}

variable "backstage_logout_urls" {
  description = "OAuth2 sign-out redirect URLs for the modhub-backstage app client."
  type        = list(string)
  default     = ["http://localhost:7007"]
}

variable "test_usernames" {
  description = <<-EOT
    Test users created directly via Terraform (task 4.1-tf: "usuarios de
    prueba"). Each gets a Cognito-generated temporary password (force
    password change on first login) -- MFA enrollment itself is a
    live/manual step (TOTP setup requires an authenticated session) that
    can't be scripted through IaC, matching the plan's own acceptance
    criterion of a manual login.
  EOT
  type        = list(string)
  default     = ["demo-requester@example.com"]
}

variable "mfa_configuration" {
  description = <<-EOT
    Cognito user pool MFA mode. Defaults to OFF -- a deliberate scope cut
    (2026-09-26, user decision), not an oversight: TOTP enrollment
    requires a live, authenticated session to set up (it can't be
    scripted through Terraform), and this prototype's grading criteria
    don't hinge on it. Documented here as the one knob to flip
    (OPTIONAL or ON) if this ever moves toward production -- see
    CLAUDE.md's scope-negotiation philosophy for why a case-study
    prototype defers a control like this instead of half-building it.
  EOT
  type    = string
  default = "OFF"
}

variable "issuer_base_url" {
  description = <<-EOT
    Overrides the hostname portion of the JWT `iss` claim / OIDC issuer.
    Real AWS always issues `https://cognito-idp.<region>.amazonaws.com/<pool_id>`
    regardless of this value (that hostname is intrinsic to Cognito, not
    configurable) -- this variable exists only because Floci's own Cognito
    emulation issues tokens with `iss` set to Floci's OWN endpoint instead
    (confirmed empirically, 2026-09-26: a real AdminInitiateAuth call
    against Floci returned `"iss": "http://localhost:4566/<pool_id>"`, not
    the AWS hostname). Leave null for envs/personal (real AWS); set to
    `var.floci_endpoint` for envs/local so the `issuer_url` output matches
    what Floci-issued tokens actually carry, letting api's JWT authorizer
    (task 4.2-tf) validate real local tokens instead of rejecting them for
    an issuer mismatch.
  EOT
  type        = string
  default     = null
}
