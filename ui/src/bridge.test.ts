import { describe, expect, it, vi } from "vitest";

import {
  consumeLoopbackBootstrap,
  LoopbackToolBridge,
  parseLoopbackBootstrap,
} from "./bridge";
import type { DashboardSnapshot } from "./types";

const snapshot: DashboardSnapshot = {
  schema_version: 2,
  title: "写作运行台",
  plugin_version: "0.1.0",
  build_id: "sha256:test",
  ui_resource_uri: "ui://writing-ops/dashboard.html",
  milestone: "M2",
  milestone_state: "implementing",
  independent_review_status: "pending",
  human_review_status: "pending",
  probes: [],
  completed: [],
  pending: [],
  blocked: [],
  next_action: "review",
  text_dashboard: "text",
  creator: {
    goals: { long_term: [], cycle: [], daily: [] },
    artifacts: [],
    human_review_status: "pending"
  },
  reviewer: {
    trace_events: [],
    commit_sets: [],
    milestone_reviews: [],
    human_reviews: [],
    human_review_status: "pending"
  }
};

describe("loopback dashboard bridge", () => {
  it("accepts only the fixed loopback endpoint and keeps tokens in memory", async () => {
    const bootstrap = parseLoopbackBootstrap(
      "#endpoint=http%3A%2F%2F127.0.0.1%3A43125%2Fapi%2Fwriting-ops%2Fdashboard" +
      "&session=abcdefghijklmnopqrstuvwxyz123456&csrf=zyxwvutsrqponmlkjihgfedcba654321" +
      "&mount=writing-ops-root"
    );
    expect(bootstrap).toEqual({
      endpoint: "http://127.0.0.1:43125/api/writing-ops/dashboard",
      sessionToken: "abcdefghijklmnopqrstuvwxyz123456",
      csrfToken: "zyxwvutsrqponmlkjihgfedcba654321",
      mountId: "writing-ops-root"
    });
    expect(() => parseLoopbackBootstrap(
      "#endpoint=https%3A%2F%2Fevil.example%2Fapi%2Fwriting-ops%2Fdashboard" +
      "&session=abcdefghijklmnopqrstuvwxyz123456&csrf=zyxwvutsrqponmlkjihgfedcba654321"
    )).toThrow(/loopback/);

    const clearFragment = vi.fn();
    expect(consumeLoopbackBootstrap(
      "#endpoint=http%3A%2F%2F127.0.0.1%3A43125%2Fapi%2Fwriting-ops%2Fdashboard" +
      "&session=abcdefghijklmnopqrstuvwxyz123456&csrf=zyxwvutsrqponmlkjihgfedcba654321",
      clearFragment
    )).toMatchObject({ endpoint: bootstrap!.endpoint });
    expect(clearFragment).toHaveBeenCalledOnce();

    const fetcher = vi.fn(async () => new Response(JSON.stringify(snapshot), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    }));
    const bridge = new LoopbackToolBridge(bootstrap!, fetcher);
    const initial = vi.fn();
    await bridge.connect(initial);

    expect(initial).toHaveBeenCalledWith(snapshot);
    expect(fetcher).toHaveBeenCalledWith(bootstrap!.endpoint, expect.objectContaining({
      cache: "no-store",
      credentials: "omit",
      referrerPolicy: "no-referrer",
      headers: {
        "X-Writing-Ops-Session": bootstrap!.sessionToken,
        "X-Writing-Ops-CSRF": bootstrap!.csrfToken
      }
    }));
  });
});
