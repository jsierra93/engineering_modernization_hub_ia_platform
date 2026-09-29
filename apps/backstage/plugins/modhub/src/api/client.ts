/*
 * Client for modhub-backend's proxy routes; attaches a bearer token to every request.
 */

import { DiscoveryApi } from '@backstage/core-plugin-api';
import {
  ApprovalInput,
  CreateRunInput,
  CreateRunResponse,
  ModhubApi,
  Report, Run,
} from './types';
import { ModhubTokenProvider } from './tokenProvider';

export class ModhubClient implements ModhubApi {
  constructor(
    private readonly discoveryApi: DiscoveryApi,
    private readonly tokenProvider: ModhubTokenProvider,
  ) {}

  private async authHeader(): Promise<Record<string, string>> {
    const token = await this.tokenProvider.getToken();
    return { Authorization: `Bearer ${token}` };
  }

  private async baseUrl(): Promise<string> {
    return this.discoveryApi.getBaseUrl('modhub-backend');
  }

  async createRun(input: CreateRunInput): Promise<CreateRunResponse> {
    const response = await fetch(`${await this.baseUrl()}/runs`, {
      method: 'POST',
      headers: { ...(await this.authHeader()), 'content-type': 'application/json' },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.json();
  }

  async listRuns(params?: { mine?: boolean; status?: string }): Promise<Run[]> {
    const qs = new URLSearchParams();
    if (params?.mine) qs.set('mine', 'true');
    if (params?.status) qs.set('status', params.status);
    const query = qs.toString();
    const response = await fetch(`${await this.baseUrl()}/runs${query ? `?${query}` : ''}`, {
      headers: await this.authHeader(),
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    const body = await response.json();
    return body.items;
  }

  async getRun(runId: string): Promise<Run> {
    const response = await fetch(`${await this.baseUrl()}/runs/${runId}`, {
      headers: await this.authHeader(),
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.json();
  }

  async getReport(runId: string): Promise<Report> {
    const response = await fetch(`${await this.baseUrl()}/runs/${runId}/report`, {
      headers: await this.authHeader(),
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.json();
  }

  async openPullRequest(runId: string): Promise<{ pull_request_url: string; branch: string }> {
    const response = await fetch(`${await this.baseUrl()}/runs/${runId}/pull-request`, {
      method: 'POST',
      headers: await this.authHeader(),
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.json();
  }

  async approve(runId: string, input: ApprovalInput): Promise<Run> {
    const response = await fetch(`${await this.baseUrl()}/runs/${runId}/approval`, {
      method: 'POST',
      headers: { ...(await this.authHeader()), 'content-type': 'application/json' },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      throw await this.toError(response);
    }
    return response.json();
  }

  private async toError(response: Response): Promise<Error> {
    const body = await response.json().catch(() => ({}));
    return new Error(body.message ?? `modhub request failed: ${response.status}`);
  }
}
