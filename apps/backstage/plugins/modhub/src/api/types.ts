/*
 * Frontend types mirroring packages/contracts/openapi.yaml; kept in sync by hand.
 */

export interface PlannedFileChange {
  path: string;
  reason: string;
}

export interface DiscoveryPlan {
  viable: boolean;
  viability_reason: string;
  summary: string;
  planned_changes?: PlannedFileChange[];
  sources?: string[];
  risks?: string[];
}

export interface Run {
  run_id: string;
  repo: string;
  commit: string;
  objetivo: string;
  status: string;
  strategy_id: string;
  strategy_version: string;
  requested_by: string;
  max_usd: number;
  spent_usd: number;
  max_iterations: number;
  iterations_used: number;
  max_minutes: number;
  created_at: string;
  plan_hash?: string | null;
  plan?: DiscoveryPlan | null;
}

export interface CreateRunInput {
  repo: string;
  commit: string;
  objetivo: string;
  max_usd: number;
  max_iterations: number;
  max_minutes: number;
  restricciones?: { excluded_paths: string[] };
}

export interface ApprovalInput {
  decision: 'approve' | 'reject';
  plan_hash: string;
  reason?: string;
}

export interface CreateRunResponse {
  run_id: string;
  status: string;
  resolved_strategy: { id: string; version: string; match_confidence: number };
  requested_by: string;
  created_at: string;
}

export interface Report {
  run_id: string;
  status: string;
  repo: string;
  commit: string;
  objetivo: string;
  strategy: { id: string; version: string };
  verdict: {
    status: string;
    spent_usd: number;
    max_usd: number;
    iterations_used: number;
    max_iterations: number;
  };
  narrative: {
    summary?: string;
    viability_reason?: string;
    sources?: string[];
    risks?: string[];
  };
  reason_code?: string | null;
  security_events?: { type: string; message?: string | null; data?: Record<string, unknown> }[];
  changed_paths: string[];
  pull_request_url?: string | null;
  diff?: string | null;
  models_used: Record<string, string>;
  plan_hash?: string | null;
  created_at: string;
}

export interface ModhubApi {
  createRun(input: CreateRunInput): Promise<CreateRunResponse>;
  listRuns(params?: { mine?: boolean; status?: string }): Promise<Run[]>;
  getReport(runId: string): Promise<Report>;
  openPullRequest(runId: string): Promise<{ pull_request_url: string; branch: string }>;
  getRun(runId: string): Promise<Run>;
  approve(runId: string, input: ApprovalInput): Promise<Run>;
}
