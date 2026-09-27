import { coreServices, createBackendPlugin } from '@backstage/backend-plugin-api';
import { notificationService } from '@backstage/plugin-notifications-node';
import { signalsServiceRef } from '@backstage/plugin-signals-node';
import { NotificationsConsumer } from './notificationsConsumer';
import { createRouter } from './router';

/**
 * Forwards each caller's own Cognito bearer token to modhub/v1, and runs
 * the pump that turns queued approval events into Backstage notifications
 * and live signals.
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
        notifications: notificationService,
        signals: signalsServiceRef,
      },
      async init({ logger, httpRouter, config, notifications, signals }) {
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

        const queueUrl = config.getOptionalString('modhub.notificationsQueueUrl');
        if (!queueUrl) {
          logger.info('modhub.notificationsQueueUrl unset -- approval notifications disabled');
          return;
        }

        const consumer = new NotificationsConsumer({
          queueUrl,
          region: config.getOptionalString('modhub.awsRegion') ?? 'us-east-2',
          logger,
          notifications,
          signals,
        });
        // Not awaited: this polls for the lifetime of the backend.
        consumer.start().catch(error => logger.error(`modhub: consumer stopped: ${error}`));
      },
    });
  },
});
