/**
 * Common client-side helpers for the TradingAgents dashboard.
 * Loaded once in Layout.tsx; available to all page-specific scripts.
 */

function _esc(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _cls(pnl) {
  if (pnl == null) return "";
  if (pnl > 0) return "positive";
  if (pnl < 0) return "negative";
  return "";
}

function _fmt(n, dec) {
  if (n == null) return "\u2014";
  return n.toFixed(dec != null ? dec : 2);
}

function _fmtPnl(pnl) {
  if (pnl == null) return "\u2014";
  var sign = pnl >= 0 ? "+" : "";
  return sign + _fmt(pnl, 2);
}

function _fmtDate(d) {
  if (!d) return "\u2014";
  var months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  var parts = d.split("-");
  if (parts.length !== 3) return d;
  return parseInt(parts[2], 10) + "-" + months[parseInt(parts[1], 10) - 1];
}

function _norm(vals) {
  if (!vals || vals.length === 0) return [];
  var lo = Math.min.apply(null, vals);
  var hi = Math.max.apply(null, vals);
  var rng = hi - lo;
  if (rng === 0) return vals.map(function () { return 50; });
  return vals.map(function (v) {
    return Math.round(((v - lo) / rng) * 100);
  });
}

function _sparkline(priceHistory) {
  if (!priceHistory || priceHistory.length === 0) return null;
  var closes = priceHistory
    .slice(-20)
    .map(function (h) { return h.close; })
    .reverse();
  var norm = _norm(closes);
  return norm.length > 0 ? "{l:" + norm.join(",") + "}" : null;
}
