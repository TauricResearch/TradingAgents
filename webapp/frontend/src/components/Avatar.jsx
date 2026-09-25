// A small, fixed palette (not a random hash-to-hue) so avatars stay inside
// the app's own color system instead of clashing with it.
const PALETTE = ["#2c5f8a", "#1f7a5c", "#7a5a2c", "#6a4c93", "#b3543a", "#3a6ea5"];

function initialsFor(name, email) {
  const source = (name || "").trim() || (email || "").trim();
  if (!source) return "?";
  if (name?.trim()) {
    const parts = name.trim().split(/\s+/);
    return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
  }
  return source[0].toUpperCase();
}

function colorFor(seed) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

export function Avatar({ name, email, size = 32 }) {
  const initials = initialsFor(name, email);
  const bg = colorFor(email || name || "?");
  return (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.4, background: bg }}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}
