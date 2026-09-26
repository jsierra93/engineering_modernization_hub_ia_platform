/**
 * Mirrors packages/contracts/openapi.yaml's Run/StrategyManifest shapes
 * closely enough for the frontend's own needs -- this plugin does not
 * generate types from the OpenAPI spec (out of scope for this pass), so
 * keep this in sync by hand if the contract changes.
 */
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
}

export interface CreateRunInput {
  repo: string;
  commit: string;
  objetivo: string;
  max_usd: number;
  max_iterations: number;
  max_minutes: number;
}

export interface ApprovalInput {
  decision: 'approve' | 'reject';
  plan_hash: string;
  reason?: string;
}

/** services/api/handler.py's create_run response shape -- narrower than
 * the full Run record (see that handler's own _ok_response call). */
export interface CreateRunResponse {
  run_id: string;
  status: string;
  resolved_strategy: { id: string; version: string; match_confidence: number };
  requested_by: string;
  created_at: string;
}

export interface ModhubApi {
  createRun(input: CreateRunInput): Promise<CreateRunResponse>;
  listRuns(params?: { mine?: boolean; status?: string }): Promise<Run[]>;
  getRun(runId: string): Promise<Run>;
  approve(runId: string, input: ApprovalInput): Promise<Run>;
}
