/**
 * Right-column turn inspector.
 *
 * The component intentionally owns no tab state.  Keying the flat turn panel
 * by selectedTurnId remounts every artifact reader when selection changes, so
 * content from a previously selected turn cannot remain visible.
 */
import { RoleInputPanel } from "./RoleInputPanel";

export interface InspectorProps {
  selectedTurnId: string | null;
}

export function Inspector({ selectedTurnId }: InspectorProps): JSX.Element {
  return (
    <div className="inspector-content">
      <RoleInputPanel
        key={selectedTurnId ?? "no-selected-turn"}
        turn_id={selectedTurnId}
      />
    </div>
  );
}
