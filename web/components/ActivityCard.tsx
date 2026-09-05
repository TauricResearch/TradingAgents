"use client";

import { useRef, useState } from "react";

export type FeedMsg = { time: string; type: string; content: string; agent?: string | null };

/** Floating, draggable live-activity card. Click any event for full context. */
export default function ActivityCard({ messages }: { messages: FeedMsg[] }) {
  const [min, setMin] = useState(false);
  const [sel, setSel] = useState<FeedMsg | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const drag = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);

  // Agent messages only — tool calls already live in Messages & Tools.
  const items = messages.filter((m) => m.type !== "Tool").slice(-30).reverse();

  function onDown(e: React.MouseEvent) {
    const el = (e.currentTarget as HTMLElement).parentElement as HTMLElement;
    const r = el.getBoundingClientRect();
    drag.current = { sx: e.clientX, sy: e.clientY, ox: r.left, oy: r.top };
    el.style.left = `${r.left}px`;
    el.style.top = `${r.top}px`;
    el.style.right = "auto";
    el.style.bottom = "auto";
    function move(ev: MouseEvent) {
      const d = drag.current;
      if (!d) return;
      setPos({ x: d.ox + ev.clientX - d.sx, y: d.oy + ev.clientY - d.sy });
    }
    function up() {
      drag.current = null;
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
    }
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  }

  return (
    <>
      <div className="floatcard" style={pos ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" } : undefined}>
        <header onMouseDown={onDown}>
          <span>Live activity</span>
          <button onClick={() => setMin(!min)}>{min ? "+" : "–"}</button>
        </header>
        {!min && (
          <div className="scroll" style={{ padding: "4px 12px 10px" }}>
            {!items.length && <div className="shimmer" style={{ height: 90, marginTop: 6 }} />}
            {items.map((m, i) => {
              const flat = (m.content || "").replace(/\s+/g, " ");
              return (
                <div
                  key={i}
                  onClick={() => setSel(m)}
                  style={{ borderBottom: "1px solid #f0f0f0", padding: "6px 0", cursor: "pointer" }}
                >
                  <div className="dim" style={{ fontSize: 11 }}>
                    {m.agent ? <b style={{ color: "#ea580c" }}>{m.agent}</b> : null}{m.agent ? " · " : ""}{m.time} · {m.type}
                  </div>
                  <div style={{ fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {flat.slice(0, 140)}{flat.length > 140 ? "…" : ""}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {sel && (
        <div className="modalback" onClick={(e) => { if (e.target === e.currentTarget) setSel(null); }}>
          <div className="modalbox">
            <header style={{ padding: "8px 12px", borderBottom: "2px solid #ea580c", display: "flex", justifyContent: "space-between" }}>
              <b>{sel.agent ? `${sel.agent} · ` : ""}{sel.time} · {sel.type}</b>
              <button onClick={() => setSel(null)} style={{ border: 0, background: "transparent", cursor: "pointer" }}>✕</button>
            </header>
            <pre>{sel.content || "(empty)"}</pre>
          </div>
        </div>
      )}
    </>
  );
}
