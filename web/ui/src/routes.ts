// Client-side routes that pages link to.

export const researchKey = (coin: string, date: string): string => `${coin}/${date}`

export const researchHref = (coin: string, date: string): string =>
  `/research/${encodeURIComponent(coin)}/${encodeURIComponent(date)}`
