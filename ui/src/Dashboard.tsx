import { useEffect, useState } from "react";

import type { DashboardSnapshot, ToolBridge } from "./types";

export function Dashboard({ bridge }: { bridge: ToolBridge }) {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"creator" | "reviewer">("creator");

  useEffect(() => {
    void bridge.connect(setSnapshot).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "无法连接 Writing Ops。 ");
    });
  }, [bridge]);

  async function refresh() {
    setError("");
    try {
      setSnapshot(await bridge.refresh());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "刷新失败。 ");
    }
  }

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">WRITING OPS · HOST PROBE</p>
          <h1>{snapshot?.title ?? "写作运行台"}</h1>
        </div>
        <span className="review">人工审阅：{snapshot?.human_review_status ?? "pending"}</span>
      </header>
      <section className="hero">
        <div>
          <span className="label">当前里程碑</span>
          <strong>{snapshot?.milestone ?? "M0"}</strong>
        </div>
        <div>
          <span className="label">状态</span>
          <strong>{snapshot?.milestone_state ?? "implementing"}</strong>
        </div>
        <button type="button" onClick={() => void refresh()}>刷新台账</button>
      </section>
      {error ? <p role="alert" className="error">{error}</p> : null}
      <nav className="mode-switch" aria-label="台面模式">
        <button type="button" aria-pressed={mode === "creator"} onClick={() => setMode("creator")}>创作者模式</button>
        <button type="button" aria-pressed={mode === "reviewer"} onClick={() => setMode("reviewer")}>审查模式</button>
      </nav>
      {mode === "creator" ? (
        <section className="goal-board" aria-label="三级写作目标">
          {(["long_term", "cycle", "daily"] as const).map((level) => (
            <article key={level}>
              <h2>{level === "long_term" ? "长期目标" : level === "cycle" ? "周期计划" : "每日目标"}</h2>
              {(snapshot?.creator.goals[level] ?? []).map((goal) => (
                <p key={`${goal.id}:${goal.revision}`}>
                  {String(goal.payload.objective ?? goal.payload.chapter ?? goal.id)}
                </p>
              ))}
            </article>
          ))}
        </section>
      ) : (
        <section className="review-panel" aria-label="审查模式台面">
          <p>审查产出均待人工审阅。</p>
        </section>
      )}
      <section className="grid" aria-label="宿主探针">
        {(snapshot?.probes ?? []).map((probe) => (
          <article key={probe.component}>
            <span className={`dot ${probe.state}`} aria-hidden="true" />
            <h2>{probe.component}</h2>
            <p>{probe.detail}</p>
          </article>
        ))}
      </section>
      <section className="next">
        <span className="label">下一步</span>
        <p>{snapshot?.next_action ?? "等待首次工具结果。"}</p>
        <p className="meta">{snapshot?.plugin_version ?? "0.1.0"} · {snapshot?.build_id ?? "build pending"} · {snapshot?.ui_resource_uri ?? "ui://writing-ops/dashboard.html"}</p>
      </section>
    </main>
  );
}
