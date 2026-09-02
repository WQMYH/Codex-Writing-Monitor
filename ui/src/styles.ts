export const styles = `
:root { color: #1c2925; background: #f5f1e8; font-family: Inter, "Segoe UI", sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; }
main { padding: 24px; max-width: 980px; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
h1 { margin: 4px 0 20px; font: 600 clamp(28px, 5vw, 52px)/1.05 Georgia, serif; }
.eyebrow, .label { color: #557069; font-size: 12px; letter-spacing: .12em; text-transform: uppercase; }
.review { padding: 8px 12px; border: 1px solid #b78f4c; border-radius: 999px; color: #765617; }
.hero { display: grid; grid-template-columns: 1fr 1fr auto; align-items: end; gap: 12px; padding: 18px; background: #dce8e2; border: 1px solid #b6ccc1; border-radius: 18px; }
.hero div { display: grid; gap: 6px; }
button { border: 0; border-radius: 10px; padding: 11px 16px; background: #315c54; color: white; cursor: pointer; }
.mode-switch { display: flex; gap: 8px; margin-top: 16px; }
.mode-switch button[aria-pressed="false"] { background: #d9dedb; color: #315c54; }
.goal-board { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }
.review-panel { margin-top: 16px; padding: 16px; border: 1px solid #ded8cc; border-radius: 16px; background: rgba(255,255,255,.72); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-top: 16px; }
article, .next { background: rgba(255,255,255,.72); border: 1px solid #ded8cc; border-radius: 16px; padding: 16px; }
article h2 { font-size: 16px; margin: 10px 0 6px; }
article p, .next p { color: #58625e; line-height: 1.5; }
.dot { width: 9px; height: 9px; display: inline-block; border-radius: 50%; background: #b78f4c; }
.dot.available { background: #2f7d64; }
.dot.blocked { background: #a54436; }
.next { margin-top: 16px; }
.meta { font-family: Consolas, monospace; font-size: 12px; }
.error { color: #a54436; }
@media (max-width: 620px) { .hero, .goal-board { grid-template-columns: 1fr; } header { display: block; } }
`;
