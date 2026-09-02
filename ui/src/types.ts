export type ProbeState = "available" | "not_tested" | "blocked";

export interface ProbeStatus {
  component: string;
  state: ProbeState;
  detail: string;
}

export interface GoalRevisionView {
  id: string;
  revision: number;
  payload: Record<string, unknown>;
  human_review_status: "pending" | "approved" | "rejected";
}

export interface GoalHierarchyView {
  long_term: GoalRevisionView[];
  cycle: GoalRevisionView[];
  daily: GoalRevisionView[];
}

export interface ArtifactView {
  id: string;
  run_id: string | null;
  kind: string;
  sha256: string;
  created_at: string;
  human_review_status: "pending" | "approved" | "rejected";
  integrity_status: "verified";
}

export interface TraceEventView {
  run_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  previous_hash: string | null;
  event_hash: string;
  created_at: string;
  human_review_status: "pending" | "approved" | "rejected";
  integrity_status: "verified";
}

export interface CommitSetView {
  id: string;
  milestone_id: string;
  revision: number;
  payload: Record<string, unknown> | null;
  payload_hash: string;
  created_at: string;
  human_review_status: "pending" | "approved" | "rejected";
  integrity_status: "verified" | "legacy_unverified";
}

export interface MilestoneReviewView {
  id: string;
  milestone_id: string;
  commit_set_id: string;
  verdict: "passed" | "passed_with_findings" | "failed" | "blocked";
  findings: Array<Record<string, unknown>>;
  created_at: string;
  human_review_status: "pending" | "approved" | "rejected";
}

export interface HumanReviewView {
  id: string;
  subject_type: string;
  subject_id: string;
  status: "approved" | "rejected";
  comment: string | null;
  created_at: string;
}

export interface CreatorDashboardView {
  goals: GoalHierarchyView;
  artifacts: ArtifactView[];
  human_review_status: "pending" | "approved" | "rejected";
}

export interface ReviewerDashboardView {
  trace_events: TraceEventView[];
  commit_sets: CommitSetView[];
  milestone_reviews: MilestoneReviewView[];
  human_reviews: HumanReviewView[];
  human_review_status: "pending" | "approved" | "rejected";
}

export interface DashboardSnapshot {
  schema_version: number;
  title: string;
  plugin_version: string;
  build_id: string;
  ui_resource_uri: string;
  milestone: string;
  milestone_state: "implementing" | "review_ready" | "completed" | "blocked";
  independent_review_status: "pending" | "passed" | "failed";
  human_review_status: "pending" | "approved" | "rejected";
  probes: ProbeStatus[];
  completed: string[];
  pending: string[];
  blocked: string[];
  next_action: string;
  text_dashboard: string;
  creator: CreatorDashboardView;
  reviewer: ReviewerDashboardView;
}

export interface ToolResult<T> {
  structuredContent?: T;
  structured_content?: T;
  isError?: boolean;
  content?: Array<{ type: string; text?: string }>;
}

export interface ToolBridge {
  connect(onInitial: (value: DashboardSnapshot) => void): Promise<void>;
  refresh(): Promise<DashboardSnapshot>;
}
