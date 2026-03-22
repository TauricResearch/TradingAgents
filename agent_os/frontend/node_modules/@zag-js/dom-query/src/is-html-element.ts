export const isHTMLElement = (v: any): v is HTMLElement =>
  typeof v === "object" && v?.nodeType === Node.ELEMENT_NODE && typeof v?.nodeName === "string"
