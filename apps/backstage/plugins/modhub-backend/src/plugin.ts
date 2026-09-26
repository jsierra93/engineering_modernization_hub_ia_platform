import { coreServices, createBackendPlugin } from '@backstage/backend-plugin-api';
import { createRouter } from './router';

/**
 * The modhub-backend plugin: forwards each caller's own Cognito bearer
 * token to modhub/v1 (task 5.2), and is where the SQS notification pump
 * (task 5.2-tf/5.4) would run once built -- not part of this pass (see
 * PLAN.md's Fase 5 notes on why Notifications/Signals stayed Diseñado).
 *
 * @public
 */
export const modhubBackendPlugin = createBackendPlugin({
  pluginId: 'modhub-backend',
  register(env) {
    env.registerInit({
      deps: {
        logger: coreServices.logger,
        httpRouter: coreServices.httpRouter,
        config: coreServices.rootConfig,
      },
      async init({ logger, httpRouter, config }) {
        const modhubBaseUrl = config.getString('modhub.baseUrl');
        const devToken = config.getOptionalString('modhub.devToken');
        if (devToken) {
          logger.warn(
            'modhub.devToken is set -- every request to modhub/v1 uses this fixed token, ' +
              'ignoring the caller\'s own. Local/dev only; delete this key for real AWS.',
          );
        }
        httpRouter.use(await createRouter({ logger, modhubBaseUrl, devToken }));
        httpRouter.addAuthPolicy({
          path: '/',
          allow: 'unauthenticated',
        });
      },
    });
  },
});
