/*
 * Where ModhubClient gets its bearer token: real OIDC or the local dev placeholder.
 */

import { OAuth2 } from '@backstage/core-app-api';

export interface ModhubTokenProvider {
  getToken(): Promise<string>;
}

export class OAuth2TokenProvider implements ModhubTokenProvider {
  constructor(private readonly authApi: OAuth2) {}

  async getToken(): Promise<string> {
    return this.authApi.getAccessToken(['openid', 'email', 'profile']);
  }
}

export class ManualTokenProvider implements ModhubTokenProvider {
  async getToken(): Promise<string> {
    return 'dev-token-placeholder-see-modhub-backend-devToken-config';
  }
}
