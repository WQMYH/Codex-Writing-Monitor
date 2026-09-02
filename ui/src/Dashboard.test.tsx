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
    goals: { long_term: [], cycle: [], daily: [] }
  },
  reviewer: { human_review_status: "pending" }
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
        goals: {
          long_term: [{ id: "long", revision: 1, payload: { objective: "finish the novel" }, human_review_status: "pending" }],
          cycle: [{ id: "cycle", revision: 1, payload: { objective: "finish the arc" }, human_review_status: "pending" }],
          daily: [{ id: "daily", revision: 1, payload: { chapter: "chapter 3" }, human_review_status: "pending" }]
        }
      },
      reviewer: { human_review_status: "pending" }
    } as unknown as DashboardSnapshot;
    const bridge: ToolBridge = {
      connect: vi.fn(async (onInitial) => onInitial(sharedViewModel)),
      refresh: vi.fn(async () => sharedViewModel)
    };

    const view = render(<Dashboard bridge={bridge} />);
    const panel = within(view.container);
    expect(await panel.findByRole("button", { name: "创作者模式" })).toBeInTheDocument();
    expect(panel.getByText("finish the novel")).toBeInTheDocument();

    fireEvent.click(panel.getByRole("button", { name: "审查模式" }));
    expect(panel.getByText("审查产出均待人工审阅。")).toBeInTheDocument();
  });
});
