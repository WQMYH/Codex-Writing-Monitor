import { App } from "@modelcontextprotocol/ext-apps";

import type { DashboardSnapshot, ToolBridge, ToolResult } from "./types";

export interface LoopbackBootstrap {
  endpoint: string;
  sessionToken: string;
  csrfToken: string;
  mountId: "writing-ops-root";
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export function parseLoopbackBootstrap(hash: string): LoopbackBootstrap | null {
  if (!hash || hash === "#") return null;
  const parameters = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  const endpointValue = parameters.get("endpoint");
  const sessionToken = parameters.get("session") ?? "";
  const csrfToken = parameters.get("csrf") ?? "";
  const mountId = parameters.get("mount") ?? "writing-ops-root";
  if (!endpointValue) throw new Error("Writing Ops loopback endpoint is missing");
  const endpoint = new URL(endpointValue);
  if (
    endpoint.protocol !== "http:" ||
    !["127.0.0.1", "[::1]", "localhost"].includes(endpoint.hostname) ||
    !endpoint.port ||
    endpoint.pathname !== "/api/writing-ops/dashboard" ||
    endpoint.search ||
    endpoint.hash ||
    endpoint.username ||
    endpoint.password
  ) {
    throw new Error("Writing Ops endpoint must be the fixed loopback dashboard API");
  }
  if (sessionToken.length < 32 || csrfToken.length < 32) {
    throw new Error("Writing Ops in-memory tokens are invalid");
  }
  if (mountId !== "writing-ops-root") {
    throw new Error("Writing Ops mount target is invalid");
  }
  return { endpoint: endpoint.toString(), sessionToken, csrfToken, mountId };
}

export function consumeLoopbackBootstrap(
  hash: string,
  clearFragment: () => void,
): LoopbackBootstrap | null {
  const bootstrap = parseLoopbackBootstrap(hash);
  if (bootstrap) clearFragment();
  return bootstrap;
}

function structured<T>(result: ToolResult<T>): T {
  const value = result.structuredContent ?? result.structured_content;
  if (!value || result.isError) {
    const message = result.content?.find((item) => item.type === "text")?.text;
    throw new Error(message ?? "Writing Ops 工具未返回结构化结果。");
  }
  return value;
}

export class McpToolBridge implements ToolBridge {
  private readonly app = new App({ name: "Writing Ops Dashboard", version: "0.1.0" });
  private connected = false;

  async connect(onInitial: (value: DashboardSnapshot) => void): Promise<void> {
    this.app.ontoolresult = (result) => {
      try {
        onInitial(structured<DashboardSnapshot>(result as ToolResult<DashboardSnapshot>));
      } catch {
        // UI-initiated calls are handled by their awaiting callers.
      }
    };
    if (!this.connected) {
      await this.app.connect();
      this.connected = true;
    }
  }

  async refresh(): Promise<DashboardSnapshot> {
    const result = await this.app.callServerTool({ name: "writing_dashboard", arguments: {} });
    return structured<DashboardSnapshot>(result as ToolResult<DashboardSnapshot>);
  }
}

export class LoopbackToolBridge implements ToolBridge {
  constructor(
    private readonly bootstrap: LoopbackBootstrap,
    private readonly fetcher: FetchLike = fetch,
  ) {}

  async connect(onInitial: (value: DashboardSnapshot) => void): Promise<void> {
    onInitial(await this.refresh());
  }

  async refresh(): Promise<DashboardSnapshot> {
    const response = await this.fetcher(this.bootstrap.endpoint, {
      method: "GET",
      mode: "cors",
      cache: "no-store",
      credentials: "omit",
      referrerPolicy: "no-referrer",
      headers: {
        "X-Writing-Ops-Session": this.bootstrap.sessionToken,
        "X-Writing-Ops-CSRF": this.bootstrap.csrfToken,
      },
    });
    if (!response.ok) throw new Error(`Writing Ops loopback returned ${response.status}`);
    const value: unknown = await response.json();
    if (
      typeof value !== "object" ||
      value === null ||
      (value as { schema_version?: unknown }).schema_version !== 2 ||
      typeof (value as { title?: unknown }).title !== "string" ||
      typeof (value as { creator?: unknown }).creator !== "object" ||
      typeof (value as { reviewer?: unknown }).reviewer !== "object"
    ) {
      throw new Error("Writing Ops loopback returned an invalid ViewModel");
    }
    return value as DashboardSnapshot;
  }
}
