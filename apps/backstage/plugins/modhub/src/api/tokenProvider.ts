import { OAuth2 } from '@backstage/core-app-api';

/**
 * Abstracts "how ModhubClient gets a bearer token" so the real OIDC flow
 * and the local dev placeholder (see ManualTokenProvider below) are
 * interchangeable behind one interface -- switching between them is the
 * single `USE_DEV_TOKEN` constant in ../apis.ts, never a change in
 * ModhubClient itself.
 */
export interface ModhubTokenProvider {
  getToken(): Promise<string>;
}

/**
 * The real path: reuses the same 'oidc' provider Backstage's own sign-in
 * uses (see modhubAuthApiRef in ../apis.ts) to get the caller's actual
 * Cognito access token via a browser OAuth2 popup.
 */
export class OAuth2TokenProvider implements ModhubTokenProvider {
  constructor(private readonly authApi: OAuth2) {}

  async getToken(): Promise<string> {
    return this.authApi.getAccessToken(['openid', 'email', 'profile']);
  }
}

/**
 * Dev-only placeholder (2026-09-26): Floci's Cognito emulation doesn't
 * expose an `authorization_endpoint` in its OIDC discovery document, so
 * OAuth2TokenProvider's browser popup flow can never complete against it
 * -- confirmed empirically, not a hypothetical. Rather than obtain a
 * real token in the browser at all, this just stops ModhubClient from
 * attempting that popup -- the REAL token now lives server-side, in
 * modhub-backend's own `modhub.devToken` config key (see
 * plugins/modhub-backend/src/router.ts), which has no frontend
 * visibility restriction to fight (an earlier attempt routed the token
 * through a `@visibility frontend`-annotated config value read here
 * instead, and that proved unreliable in practice). What this provider
 * returns is therefore never actually checked by modhub/v1 -- it only
 * needs to be a non-empty string so ModhubClient's own header-presence
 * check doesn't reject the request before it reaches modhub-backend.
 */
export class ManualTokenProvider implements ModhubTokenProvider {
  async getToken(): Promise<string> {
    return 'dev-token-placeholder-see-modhub-backend-devToken-config';
  }
}
