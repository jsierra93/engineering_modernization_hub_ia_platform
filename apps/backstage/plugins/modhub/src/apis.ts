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

// The ONLY switch between the real OIDC popup flow and the local dev
// escape hatch. Deliberately a plain code constant, NOT a Backstage
// config key: a `@visibility frontend`-annotated config value
// (modhub.devAuth) was tried first and proved unreliable in practice
// (confirmed empirically, 2026-09-26 -- the page kept falling through to
// the real OAuth2 popup even with the flag set). The real per-request
// auth override now lives server-side instead (modhub-backend's
// `modhub.devToken` config, which has no visibility restriction to fight)
// -- this constant only needs to stop the BROWSER from attempting a
// popup that can't complete against Floci; what token it sends doesn't
// matter once devToken is set backend-side. Flip to false once pointed
// at real AWS with a working browser OIDC flow.
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
