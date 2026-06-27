import type { ReactNode } from "react";

type Side = "right" | "left" | "bottom";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  side?: Side;
  width?: string;
}

const sideClasses: Record<Side, string> = {
  right: "inset-y-0 right-0 w-full md:w-[28rem] md:max-w-full border-l flex flex-col",
  left: "inset-y-0 left-0 w-full md:w-80 border-r flex flex-col",
  bottom: "inset-x-0 bottom-0 border-t",
};

const transitionClasses: Record<Side, string> = {
  right: open ? "translate-x-0" : "translate-x-full",
  left: open ? "translate-x-0" : "-translate-x-full",
  bottom: open ? "translate-y-0" : "translate-y-full",
};

export function Drawer({ open, onClose, title, children, side = "right", width }: DrawerProps) {
  return (
    <>
      <div
        className={`drawer-overlay ${open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"}`}
        onClick={onClose}
        aria-hidden
      />
      <div
        className={`drawer-panel ${sideClasses[side]} ${transitionClasses[side]}`}
        style={side !== "bottom" && width ? { width } : side === "bottom" ? { height: width ?? "45vh" } : undefined}
        role="dialog"
        aria-label={title}
      >
        {title && (
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50">
            <h3 className="font-display font-semibold text-slate-200 text-sm">{title}</h3>
            <button
              onClick={onClose}
              aria-label="Close"
              className="p-1 hover:bg-slate-700/50 rounded-lg text-slate-500 hover:text-slate-300 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        <div className="flex-1 min-h-0 overflow-y-auto">{children}</div>
      </div>
    </>
  );
}
