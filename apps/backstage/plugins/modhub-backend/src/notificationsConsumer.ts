import {
  DeleteMessageCommand,
  ReceiveMessageCommand,
  SQSClient,
} from '@aws-sdk/client-sqs';
import { LoggerService } from '@backstage/backend-plugin-api';
import { NotificationService } from '@backstage/plugin-notifications-node';
import { SignalsService } from '@backstage/plugin-signals-node';

export const MODHUB_SIGNAL_CHANNEL = 'modhub:runs';

type Options = {
  queueUrl: string;
  region: string;
  logger: LoggerService;
  notifications?: NotificationService;
  signals?: SignalsService;
  /** Injected in tests; defaults to a real client using the ambient chain. */
  client?: SQSClient;
};

type QueueMessage = {
  event_type?: string;
  run_id?: string;
  plan_hash?: string;
};

/**
 * Long-polls the notifications queue Step Functions writes to, turns each
 * message into a Backstage notification plus a signal, and deletes it.
 *
 * Deleting only after both were emitted is deliberate: a message redelivered
 * after a crash is a duplicate notification, which is recoverable, whereas
 * deleting first would silently lose an approval request.
 */
export class NotificationsConsumer {
  private readonly client: SQSClient;
  private stopped = false;

  constructor(private readonly options: Options) {
    this.client = options.client ?? new SQSClient({ region: options.region });
  }

  stop() {
    this.stopped = true;
  }

  async start() {
    const { logger, queueUrl } = this.options;
    logger.info(`modhub: consuming approval notifications from ${queueUrl}`);

    while (!this.stopped) {
      try {
        const received = await this.client.send(
          new ReceiveMessageCommand({
            QueueUrl: queueUrl,
            MaxNumberOfMessages: 10,
            WaitTimeSeconds: 20,
          }),
        );

        for (const message of received.Messages ?? []) {
          await this.handle(message.Body, message.ReceiptHandle);
        }
      } catch (error) {
        logger.error(`modhub: SQS poll failed: ${error}`);
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }
  }

  private async handle(body?: string, receiptHandle?: string) {
    const { logger, notifications, signals, queueUrl } = this.options;
    if (!body || !receiptHandle) {
      return;
    }

    let payload: QueueMessage;
    try {
      payload = JSON.parse(body);
    } catch {
      logger.warn(`modhub: discarding unparseable queue message: ${body.slice(0, 200)}`);
      await this.client.send(
        new DeleteMessageCommand({ QueueUrl: queueUrl, ReceiptHandle: receiptHandle }),
      );
      return;
    }

    const runId = payload.run_id ?? 'unknown';

    if (payload.event_type === 'AWAITING_APPROVAL') {
      await notifications?.send({
        recipients: { type: 'broadcast' },
        payload: {
          title: 'Plan de modernización pendiente de aprobación',
          description: `El run ${runId} espera tu revisión.`,
          link: `/modhub`,
          topic: 'modhub',
          severity: 'normal',
        },
      });
    }

    await signals?.publish({
      recipients: { type: 'broadcast' },
      channel: MODHUB_SIGNAL_CHANNEL,
      message: { event_type: payload.event_type ?? 'UNKNOWN', run_id: runId },
    });

    await this.client.send(
      new DeleteMessageCommand({ QueueUrl: queueUrl, ReceiptHandle: receiptHandle }),
    );
    logger.info(`modhub: notified ${payload.event_type} for run ${runId}`);
  }
}
