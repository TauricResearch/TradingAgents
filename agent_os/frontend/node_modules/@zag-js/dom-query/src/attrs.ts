type Booleanish = boolean | "true" | "false"

export const dataAttr = (guard: boolean | undefined) => {
  return (guard ? "" : undefined) as Booleanish
}

export const ariaAttr = (guard: boolean | undefined) => {
  return guard ? "true" : undefined
}
