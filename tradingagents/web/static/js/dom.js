// Tiny DOM helpers — everything user- or LLM-derived goes through
// textContent (or the markdown sanitizer), never raw innerHTML.

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2), value);
    } else if (value !== null && value !== undefined) {
      node.setAttribute(key, value);
    }
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

export function formatElapsed(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const mins = String(Math.floor(total / 60)).padStart(2, '0');
  const secs = String(total % 60).padStart(2, '0');
  return `${mins}:${secs}`;
}

export function decisionClass(decision) {
  const d = (decision || '').toUpperCase();
  if (d.includes('BUY')) return 'buy';
  if (d.includes('SELL')) return 'sell';
  if (d.includes('HOLD')) return 'hold';
  return 'unknown';
}
