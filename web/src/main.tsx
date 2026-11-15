import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import { App } from "./App";
import "./styles.css";
import { applyFont } from "./font";
import { applyTheme } from "./theme";

applyTheme();
applyFont();

function render(demoBar?: JSX.Element, routes?: Record<string, JSX.Element>) {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      {demoBar}
      <App routes={routes} />
    </StrictMode>,
  );
}

// Click dummy (vite --mode demo): the same client on a simulated backend.
// In every other build this branch and the mock are removed.
if (import.meta.env.MODE === "demo") {
  Promise.all([import("./demo/mock"), import("./demo/DemoBar")]).then(([mock, bar]) => {
    mock.installMock();
    render(<bar.DemoBar />, { "choose-role": <bar.ChooseRole /> });
  });
} else {
  render();
}
