import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Dashboard } from "./Dashboard";
import type { DashboardSnapshot, ToolBridge } from "./types";

const snapshot: DashboardSnapshot = {
  schema_version: 1,
  title: "写作运行台",
  plugin_version: "0.1.0",
  build_id: "sha256:test",
  ui_resource_uri: "ui://writing-ops/dashboard.html",
  milestone: "M0",
  milestone_state: "implementing",
  independent_review_status: "pending",
  human_review_status: "pending",
  probes: [{ component: "mcp-tool", state: "available", detail: "可用" }],
  completed: [],
  pending: [],
  blocked: [],
  next_action: "安装探针",
  text_dashboard: "M0",
  creator: {
    human_review_status: "pending",
    artifacts: [],
    goals: { long_term: [], cycle: [], daily: [] }
  },
  reviewer: {
    human_review_status: "pending",
    trace_events: [],
    commit_sets: [],
    milestone_reviews: [],
    human_reviews: []
  }
};

describe("Dashboard", () => {
  it("renders the initial tool result and refreshes through the MCP bridge", async () => {
    const refreshed: DashboardSnapshot = { ...snapshot, milestone_state: "review_ready" };
    const bridge: ToolBridge = {
      connect: vi.fn(async (onInitial) => onInitial(snapshot)),
      refresh: vi.fn(async () => refreshed)
    };

    render(<Dashboard bridge={bridge} />);
    expect(await screen.findByText("人工审阅：pending")).toBeInTheDocument();
    expect(screen.getByText("mcp-tool")).toBeInTheDocument();
    expect(screen.getByText(/ui:\/\/writing-ops\/dashboard.html/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "刷新台账" }));
    expect(await screen.findByText("review_ready")).toBeInTheDocument();
    expect(bridge.refresh).toHaveBeenCalledOnce();
  });

  it("renders creator and reviewer modes from the shared view model", async () => {
    const sharedViewModel = {
      ...snapshot,
      schema_version: 2,
      creator: {
        human_review_status: "pending",
        artifacts: [{
          id: "artifact-1",
          run_id: "run-1",
          kind: "candidate_text",
          sha256: "abc123",
          created_at: "2026-09-02T12:00:00+00:00",
          human_review_status: "pending",
          integrity_status: "verified"
        }],
        goals: {
          long_term: [{ id: "long", revision: 1, payload: { objective: "finish the novel" }, human_review_status: "pending" }],
          cycle: [{ id: "cycle", revision: 1, payload: { objective: "finish the arc" }, human_review_status: "pending" }],
          daily: [{ id: "daily", revision: 1, payload: { chapter: "chapter 3" }, human_review_status: "pending" }]
        }
      },
      reviewer: {
        human_review_status: "approved",
        commit_sets: [{
          id: "commit-set-1",
          milestone_id: "M2",
          revision: 1,
          payload: null,
          integrity_status: "legacy_unverified",
          payload_hash: "commit-set-hash",
          created_at: "2026-09-02T12:00:00+00:00",
          human_review_status: "approved"
        }],
        milestone_reviews: [{
          id: "review-1",
          milestone_id: "M2",
          commit_set_id: "commit-set-1",
          verdict: "passed_with_findings",
          findings: [{ id: "M2-MINOR", severity: "minor", status: "open" }],
          created_at: "2026-09-02T12:00:00+00:00",
          human_review_status: "pending",
          integrity_status: "verified"
        }],
        human_reviews: [{
          id: "human-1",
          subject_type: "commit_set",
          subject_id: "commit-set-1",
          status: "approved",
          comment: "accept this exact revision",
          created_at: "2026-09-02T12:00:00+00:00"
        }],
        trace_events: [{
          run_id: "run-1",
          sequence: 2,
          event_type: "step_ack",
          payload: { step_id: "generate-1", outcome: "durable_ack", state: "completed" },
          previous_hash: "previous",
          event_hash: "event-hash",
          created_at: "2026-09-02T12:00:00+00:00",
          human_review_status: "pending"
        }]
      }
    } as unknown as DashboardSnapshot;
    const bridge: ToolBridge = {
      connect: vi.fn(async (onInitial) => onInitial(sharedViewModel)),
      refresh: vi.fn(async () => sharedViewModel)
    };

    const view = render(<Dashboard bridge={bridge} />);
    const panel = within(view.container);
    expect(await panel.findByRole("button", { name: "创作者模式" })).toBeInTheDocument();
    expect(panel.getByText("finish the novel")).toBeInTheDocument();
    expect(panel.getByText(/candidate_text.*abc123/)).toBeInTheDocument();

    fireEvent.click(panel.getByRole("button", { name: "审查模式" }));
    expect(panel.getByText("审查产出状态：approved")).toBeInTheDocument();
    expect(panel.getByText(/step_ack.*#2.*event-hash/)).toBeInTheDocument();
    expect(panel.getByText(/M2.*revision 1.*approved/)).toBeInTheDocument();
    expect(panel.getByText(/passed_with_findings.*1 finding/)).toBeInTheDocument();
    expect(panel.getByText(/accept this exact revision/)).toBeInTheDocument();
  });
});
