import { App } from "@modelcontextprotocol/ext-apps";

import type { DashboardSnapshot, ToolBridge, ToolResult } from "./types";

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

