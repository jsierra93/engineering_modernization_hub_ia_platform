/*
 * Starts the approval-notifications consumer when a queue is configured; the proxy does not depend on it.
 */

import { LoggerService, RootConfigService } from '@backstage/backend-plugin-api';
import { NotificationService } from '@backstage/plugin-notifications-node';
import { SignalsService } from '@backstage/plugin-signals-node';
import { NotificationsConsumer } from './notificationsConsumer';

type Options = {
  config: RootConfigService;
  logger: LoggerService;
  notifications?: NotificationService;
  signals?: SignalsService;
};

export function startApprovalNotifications({ config, logger, notifications, signals }: Options) {
  const queueUrl = config.getOptionalString('modhub.notificationsQueueUrl');
  if (!queueUrl) {
    logger.info('modhub.notificationsQueueUrl unset -- approval notifications disabled');
    return;
  }

  const consumer = new NotificationsConsumer({
    queueUrl,
    region: config.getString('modhub.awsRegion'),
    logger,
    notifications,
    signals,
  });
  consumer.start().catch(error => logger.error(`modhub: consumer stopped: ${error}`));
}
