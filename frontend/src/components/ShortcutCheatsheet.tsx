import { Dialog, DialogContent } from "./ui/dialog";
import { Kbd } from "./ui/kbd";
import { SHORTCUT_CHEATSHEET } from "@/lib/shortcuts";
import { useUiStore } from "@/stores/ui";

export function ShortcutCheatsheet() {
  const { shortcutsOpen, setShortcutsOpen } = useUiStore();
  return (
    <Dialog open={shortcutsOpen} onOpenChange={setShortcutsOpen}>
      <DialogContent title="Keyboard shortcuts">
        <table className="w-full text-sm">
          <tbody>
            {SHORTCUT_CHEATSHEET.map((row) => (
              <tr key={row.keys} className="border-b border-border/50">
                <td className="py-1.5 pr-4">
                  <Kbd>{row.keys}</Kbd>
                </td>
                <td className="py-1.5 text-fg-muted">{row.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-fg-subtle">
          The kill switch has no shortcut by design: halting trading requires a
          typed confirmation in Settings.
        </p>
      </DialogContent>
    </Dialog>
  );
}
