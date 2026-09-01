import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { McpToolBridge } from "./bridge";
import { Dashboard } from "./Dashboard";
import { styles } from "./styles";

const style = document.createElement("style");
style.textContent = styles;
document.head.append(style);

const root = document.getElementById("root");
if (!root) throw new Error("Writing Ops root element is missing");

createRoot(root).render(
  <StrictMode>
    <Dashboard bridge={new McpToolBridge()} />
  </StrictMode>,
);

