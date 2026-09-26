/**
 * Fase 5, task 5.2. This router forwards a bearer token to modhub/v1 on
 * every request. It never holds or asserts a service-level credential of
 * its own for the REAL path -- see the design artifact's "modhub-backend
 * ... no afirma identidades" -- the frontend's own Cognito access token
 * (obtained from the `oidc` auth provider, NOT Backstage's internal
 * session token) is what normally travels here as a plain
 * `Authorization: Bearer <token>` header.
 *
 * Local-dev exception, `devToken` (config key `modhub.devToken`,
 * backend-only, 2026-09-26): Floci's Cognito emulation doesn't expose an
 * `authorization_endpoint` in its OIDC discovery document, so the real
 * browser popup flow can never complete against it -- confirmed
 * empirically, not a hypothetical, and a frontend-side workaround (a
 * manually-pasted token gated by a `@visibility frontend` config flag)
 * also proved unreliable in practice. Backend config has no visibility
 * restriction at all, so this is the more robust place to short-circuit:
 * when `modhub.devToken` is set, EVERY request uses it, regardless of
 * whatever the browser sent -- see start-local-env.sh's own printed curl
 * command for how to mint a fresh one against Floci. Delete this config
 * key once pointed at real AWS and the real per-user Cognito token takes
 * over automatically -- no code change needed.
 */

import { LoggerService } from '@backstage/backend-plugin-api';
import { NotAllowedError } from '@backstage/errors';
import express from 'express';
import Router from 'express-promise-router';

export interface RouterOptions {
  logger: LoggerService;
  modhubBaseUrl: string;
  devToken?: string;
}

function forwardedHeaders(req: express.Request, devToken?: string): HeadersInit {
  const authorization = devToken ? `Bearer ${devToken}` : req.header('authorization');
  if (!authorization) {
    throw new NotAllowedError('Missing Authorization header');
  }
  return {
    authorization,
    'content-type': 'application/json',
  };
}

export async function createRouter(
  options: RouterOptions,
): Promise<express.Router> {
  const { logger, modhubBaseUrl, devToken } = options;
  const router = Router();
  router.use(express.json());

  // Every route below is a thin, verbatim proxy onto modhub/v1's own
  // routes (packages/contracts/openapi.yaml) -- this plugin adds no
  // request/response shape of its own, so the frontend's ModhubClient
  // (plugins/modhub) and a direct call to modhub/v1 behave identically.

  router.post('/runs', async (req, res) => {
    const upstream = await fetch(`${modhubBaseUrl}/modhub/v1/runs`, {
      method: 'POST',
      headers: forwardedHeaders(req, devToken),
      body: JSON.stringify(req.body),
    });
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.get('/runs', async (req, res) => {
    const qs = new URLSearchParams(
      req.query as Record<string, string>,
    ).toString();
    const upstream = await fetch(
      `${modhubBaseUrl}/modhub/v1/runs${qs ? `?${qs}` : ''}`,
      { headers: forwardedHeaders(req, devToken) },
    );
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.get('/runs/:runId', async (req, res) => {
    const upstream = await fetch(
      `${modhubBaseUrl}/modhub/v1/runs/${req.params.runId}`,
      { headers: forwardedHeaders(req, devToken) },
    );
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.post('/runs/:runId/approval', async (req, res) => {
    const upstream = await fetch(
      `${modhubBaseUrl}/modhub/v1/runs/${req.params.runId}/approval`,
      {
        method: 'POST',
        headers: forwardedHeaders(req, devToken),
        body: JSON.stringify(req.body),
      },
    );
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.use(
    (
      error: Error,
      _req: express.Request,
      res: express.Response,
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      _next: express.NextFunction,
    ) => {
      logger.warn(`modhub-backend proxy error: ${error.message}`);
      const status = error instanceof NotAllowedError ? 401 : 502;
      res.status(status).json({ code: 'MODHUB_PROXY_ERROR', message: error.message });
    },
  );

  return router;
}
