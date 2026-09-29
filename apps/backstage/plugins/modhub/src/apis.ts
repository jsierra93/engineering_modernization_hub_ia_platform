/*
 * Frontend API wiring: OAuth2 auth API and the ModhubClient with its token provider.
 */

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

const USE_DEV_TOKEN = true;

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
