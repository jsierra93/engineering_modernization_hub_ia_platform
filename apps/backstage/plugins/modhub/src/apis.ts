import {
  ApiBlueprint,
  createApiFactory,
  createApiRef,
  discoveryApiRef,
  oauthRequestApiRef,
  configApiRef,
  ApiRef,
} from '@backstage/frontend-plugin-api';
import { OAuth2 } from '@backstage/core-app-api';
import { ModhubApi } from './api/types';
import { ModhubClient } from './api/client';
import { ManualTokenProvider, ModhubTokenProvider, OAuth2TokenProvider } from './api/tokenProvider';

// The browser OIDC flow is blocked on an unresolved "Invalid
// X-Requested-With header" on /auth/oidc/refresh (see PLAN.md 5.6). Until
// that is fixed, modhub-backend's `modhub.devToken` carries every request
// and this keeps the browser from opening a popup that cannot complete.
const USE_DEV_TOKEN = true;

/**
 * Reuses the SAME 'oidc' provider Backstage's own sign-in uses (see
 * packages/backend/src/index.ts and app-config.yaml's auth.providers.oidc)
 * to obtain the caller's raw Cognito access token -- one Cognito login
 * covers both Backstage's own session AND every call to modhub/v1,
 * exactly as the design artifact's identity section describes ("una sola
 * identidad de Cognito").
 *
 * @public
 */
export const modhubAuthApiRef: ApiRef<OAuth2> = createApiRef({
  id: 'auth.modhub',
});

export const modhubAuthApi = ApiBlueprint.make({
  name: 'auth',
  params: define =>
    define(
      createApiFactory({
        api: modhubAuthApiRef,
        deps: {
          discoveryApi: discoveryApiRef,
          oauthRequestApi: oauthRequestApiRef,
          configApi: configApiRef,
        },
        factory: ({ discoveryApi, oauthRequestApi, configApi }) =>
          OAuth2.create({
            discoveryApi,
            oauthRequestApi,
            provider: {
              id: 'oidc',
              title: 'Engineering Modernization Hub',
              icon: () => null,
            },
            environment: configApi.getOptionalString('auth.environment'),
            defaultScopes: ['openid', 'email', 'profile'],
          }),
      }),
    ),
});

export const modhubApiRef: ApiRef<ModhubApi> = createApiRef({
  id: 'plugin.modhub.api',
});

export const modhubApi = ApiBlueprint.make({
  name: 'client',
  params: define =>
    define(
      createApiFactory({
        api: modhubApiRef,
        deps: {
          discoveryApi: discoveryApiRef,
          authApi: modhubAuthApiRef,
        },
        factory: ({ discoveryApi, authApi }) => {
          const tokenProvider: ModhubTokenProvider = USE_DEV_TOKEN
            ? new ManualTokenProvider()
            : new OAuth2TokenProvider(authApi);
          return new ModhubClient(discoveryApi, tokenProvider);
        },
      }),
    ),
});
