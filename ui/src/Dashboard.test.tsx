import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Dashboard } from "./Dashboard";
import type { DashboardSnapshot, ToolBridge } from "./types";

const snapshot: DashboardSnapshot = {
  schema_version: 1,
  title: "写作运行台",
  plugin_version: "0.1.0",
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
  text_dashboard: "M0"
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
});
