export function decisionKind(decision) {
  const d = (decision || "").toLowerCase();
  if (d.includes("buy")) return "buy";
  if (d.includes("sell")) return "sell";
  return "hold";
}
