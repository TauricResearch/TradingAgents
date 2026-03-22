export function itemById<T extends HTMLElement>(v: T[], id: string) {
  return v.find((node) => node.id === id)
}

export function indexOfId<T extends HTMLElement>(v: T[], id: string) {
  const item = itemById(v, id)
  return item ? v.indexOf(item) : -1
}

export function nextById<T extends HTMLElement>(v: T[], id: string, loop = true) {
  let idx = indexOfId(v, id)
  idx = loop ? (idx + 1) % v.length : Math.min(idx + 1, v.length - 1)
  return v[idx]
}

export function prevById<T extends HTMLElement>(v: T[], id: string, loop = true) {
  let idx = indexOfId(v, id)
  if (idx === -1) return loop ? v[v.length - 1] : null
  idx = loop ? (idx - 1 + v.length) % v.length : Math.max(0, idx - 1)
  return v[idx]
}
