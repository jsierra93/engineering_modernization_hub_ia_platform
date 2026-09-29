/*
 * Proxy from Backstage to modhub/v1: forwards the caller's bearer token verbatim, adding only x-trace-id.
 * With modhub.devToken set (local only) every request uses that token instead.
 */

import { LoggerService } from '@backstage/backend-plugin-api';
import { NotAllowedError } from '@backstage/errors';
import { randomUUID } from 'node:crypto';
import express from 'express';
import Router from 'express-promise-router';

export interface RouterOptions {
  logger: LoggerService;
  modhubBaseUrl: string;
  devToken?: string;
}

function getOrGenerateTraceId(req: express.Request): string {
  return req.header('x-trace-id') || randomUUID();
}

function forwardedHeaders(req: express.Request, devToken?: string, traceId?: string): HeadersInit {
  const authorization = devToken ? `Bearer ${devToken}` : req.header('authorization');
  if (!authorization) {
    throw new NotAllowedError('Missing Authorization header');
  }
  return {
    authorization,
    'content-type': 'application/json',
    'x-trace-id': traceId || randomUUID(),
  };
}

export async function createRouter(
  options: RouterOptions,
): Promise<express.Router> {
  const { logger, modhubBaseUrl, devToken } = options;
  const router = Router();
  router.use(express.json());

  router.use((req: express.Request, res: express.Response, next: express.NextFunction) => {
    const traceId = getOrGenerateTraceId(req);
    (req as any).traceId = traceId;
    res.setHeader('x-trace-id', traceId);
    logger.info(`[trace_id=${traceId}] ${req.method} ${req.path}`);
    next();
  });

  router.post('/runs', async (req, res) => {
    const traceId = (req as any).traceId;
    const upstream = await fetch(`${modhubBaseUrl}/modhub/v1/runs`, {
      method: 'POST',
      headers: forwardedHeaders(req, devToken, traceId),
      body: JSON.stringify(req.body),
    });
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.get('/runs', async (req, res) => {
    const traceId = (req as any).traceId;
    const qs = new URLSearchParams(
      req.query as Record<string, string>,
    ).toString();
    const upstream = await fetch(
      `${modhubBaseUrl}/modhub/v1/runs${qs ? `?${qs}` : ''}`,
      { headers: forwardedHeaders(req, devToken, traceId) },
    );
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.get('/runs/:runId', async (req, res) => {
    const traceId = (req as any).traceId;
    const upstream = await fetch(
      `${modhubBaseUrl}/modhub/v1/runs/${encodeURIComponent(req.params.runId)}`,
      { headers: forwardedHeaders(req, devToken, traceId) },
    );
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.get('/runs/:runId/report', async (req, res) => {
    const traceId = (req as any).traceId;
    const upstream = await fetch(
      `${modhubBaseUrl}/modhub/v1/runs/${encodeURIComponent(req.params.runId)}/report`,
      { headers: forwardedHeaders(req, devToken, traceId) },
    );
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.post('/runs/:runId/approval', async (req, res) => {
    const traceId = (req as any).traceId;
    const upstream = await fetch(
      `${modhubBaseUrl}/modhub/v1/runs/${encodeURIComponent(req.params.runId)}/approval`,
      {
        method: 'POST',
        headers: forwardedHeaders(req, devToken, traceId),
        body: JSON.stringify(req.body),
      },
    );
    const body = await upstream.text();
    res.status(upstream.status).type('application/json').send(body);
  });

  router.post('/runs/:runId/pull-request', async (req, res) => {
    const traceId = (req as any).traceId;
    const upstream = await fetch(
      `${modhubBaseUrl}/modhub/v1/runs/${encodeURIComponent(req.params.runId)}/pull-request`,
      {
        method: 'POST',
        headers: forwardedHeaders(req, devToken, traceId),
        body: JSON.stringify(req.body ?? {}),
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
