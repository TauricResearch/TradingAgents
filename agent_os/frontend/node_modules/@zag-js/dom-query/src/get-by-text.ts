import { indexOfId } from "./get-by-id"

const getValueText = <T extends HTMLElement>(item: T) => item.dataset.valuetext ?? item.textContent ?? ""

const match = (valueText: string, query: string) => valueText.trim().toLowerCase().startsWith(query.toLowerCase())

const wrap = <T>(v: T[], idx: number) => {
  return v.map((_, index) => v[(Math.max(idx, 0) + index) % v.length])
}

export function getByText<T extends HTMLElement>(v: T[], text: string, currentId?: string | null) {
  const index = currentId ? indexOfId(v, currentId) : -1
  let items = currentId ? wrap(v, index) : v

  const isSingleKey = text.length === 1

  if (isSingleKey) {
    items = items.filter((item) => item.id !== currentId)
  }

  return items.find((item) => match(getValueText(item), text))
}
