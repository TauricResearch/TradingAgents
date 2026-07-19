import { WorkbenchProvider } from "./state/WorkbenchStore";
import { WorkbenchLayout } from "./components/layout/WorkbenchLayout";

/**
 * App root: wraps the workbench in the per-run store provider and renders the
 * three-column layout. F2 (reducer + SSE) and F3 (controls + history) are
 * wired together inside WorkbenchLayout; G1-G3 will fill the center workflow
 * timeline and the right audit inspector.
 */
export function App() {
  return (
    <WorkbenchProvider>
      <WorkbenchLayout />
    </WorkbenchProvider>
  );
}