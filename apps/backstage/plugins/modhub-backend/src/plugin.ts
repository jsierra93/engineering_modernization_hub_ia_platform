/*
 * Backend plugin: mounts the modhub/v1 proxy and starts the approval-notifications consumer.
 */

import { coreServices, createBackendPlugin } from '@backstage/backend-plugin-api';
import { notificationService } from '@backstage/plugin-notifications-node';
import { signalsServiceRef } from '@backstage/plugin-signals-node';
import { NotificationsConsumer } from './notificationsConsumer';
import { createRouter } from './router';

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
        consumer.start().catch(error => logger.error(`modhub: consumer stopped: ${error}`));
      },
    });
  },
});
