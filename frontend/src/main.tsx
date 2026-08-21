import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./vigil/tokens.css";
import "./vigil/components.css";
import "./vigil/app.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
