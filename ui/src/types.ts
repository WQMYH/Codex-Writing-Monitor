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

export interface CreatorDashboardView {
  goals: GoalHierarchyView;
  human_review_status: "pending" | "approved" | "rejected";
}

export interface ReviewerDashboardView {
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
