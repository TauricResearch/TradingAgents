import isDevelopment from '#is-development'
/*

Based off glamor's StyleSheet, thanks Sunil ❤️

high performance StyleSheet for css-in-js systems

- uses multiple style tags behind the scenes for millions of rules
- uses `insertRule` for appending in production for *much* faster performance

// usage

import { StyleSheet } from '@emotion/sheet'

let styleSheet = new StyleSheet({ key: '', container: document.head })

styleSheet.insert('#box { border: 1px solid red; }')
- appends a css rule into the stylesheet

styleSheet.flush()
- empties the stylesheet of all its contents

*/

function sheetForTag(tag: HTMLStyleElement): CSSStyleSheet {
  if (tag.sheet) {
    return tag.sheet
  }

  // this weirdness brought to you by firefox
  /* istanbul ignore next */
  for (let i = 0; i < document.styleSheets.length; i++) {
    if (document.styleSheets[i].ownerNode === tag) {
      return document.styleSheets[i]
    }
  }

  // this function should always return with a value
  // TS can't understand it though so we make it stop complaining here
  return undefined as any
}

export type Options = {
  nonce?: string
  key: string
  container: Node
  speedy?: boolean
  prepend?: boolean
  insertionPoint?: HTMLElement
}

function createStyleElement(options: Options): HTMLStyleElement {
  let tag = document.createElement('style')
  tag.setAttribute('data-emotion', options.key)
  if (options.nonce !== undefined) {
    tag.setAttribute('nonce', options.nonce)
  }
  tag.appendChild(document.createTextNode(''))
  tag.setAttribute('data-s', '')
  return tag
}

export class StyleSheet {
  isSpeedy: boolean
  ctr: number
  tags: HTMLStyleElement[]
  // Using Node instead of HTMLElement since container may be a ShadowRoot
  container: Node
  key: string
  nonce: string | undefined
  prepend: boolean | undefined
  before: Element | null
  insertionPoint: HTMLElement | undefined

  private _alreadyInsertedOrderInsensitiveRule: boolean | undefined

  constructor(options: Options) {
    this.isSpeedy =
      options.speedy === undefined ? !isDevelopment : options.speedy
    this.tags = []
    this.ctr = 0
    this.nonce = options.nonce
    // key is the value of the data-emotion attribute, it's used to identify different sheets
    this.key = options.key
    this.container = options.container
    this.prepend = options.prepend
    this.insertionPoint = options.insertionPoint
    this.before = null
  }

  private _insertTag = (tag: HTMLStyleElement): void => {
    let before
    if (this.tags.length === 0) {
      if (this.insertionPoint) {
        before = this.insertionPoint.nextSibling
      } else if (this.prepend) {
        before = this.container.firstChild
      } else {
        before = this.before
      }
    } else {
      before = this.tags[this.tags.length - 1].nextSibling
    }
    this.container.insertBefore(tag, before)
    this.tags.push(tag)
  }

  hydrate(nodes: HTMLStyleElement[]): void {
    nodes.forEach(this._insertTag)
  }

  insert(rule: string): void {
    // the max length is how many rules we have per style tag, it's 65000 in speedy mode
    // it's 1 in dev because we insert source maps that map a single rule to a location
    // and you can only have one source map per style tag
    if (this.ctr % (this.isSpeedy ? 65000 : 1) === 0) {
      this._insertTag(createStyleElement(this))
    }
    const tag = this.tags[this.tags.length - 1]

    if (isDevelopment) {
      const isImportRule =
        rule.charCodeAt(0) === 64 && rule.charCodeAt(1) === 105

      if (isImportRule && this._alreadyInsertedOrderInsensitiveRule) {
        // this would only cause problem in speedy mode
        // but we don't want enabling speedy to affect the observable behavior
        // so we report this error at all times
        console.error(
          `You're attempting to insert the following rule:\n` +
            rule +
            '\n\n`@import` rules must be before all other types of rules in a stylesheet but other rules have already been inserted. Please ensure that `@import` rules are before all other rules.'
        )
      }

      this._alreadyInsertedOrderInsensitiveRule =
        this._alreadyInsertedOrderInsensitiveRule || !isImportRule
    }

    if (this.isSpeedy) {
      const sheet = sheetForTag(tag)
      try {
        // this is the ultrafast version, works across browsers
        // the big drawback is that the css won't be editable in devtools
        sheet.insertRule(rule, sheet.cssRules.length)
      } catch (e) {
        if (
          isDevelopment &&
          !/:(-moz-placeholder|-moz-focus-inner|-moz-focusring|-ms-input-placeholder|-moz-read-write|-moz-read-only|-ms-clear|-ms-expand|-ms-reveal){/.test(
            rule
          )
        ) {
          console.error(
            `There was a problem inserting the following rule: "${rule}"`,
            e
          )
        }
      }
    } else {
      tag.appendChild(document.createTextNode(rule))
    }
    this.ctr++
  }

  flush(): void {
    this.tags.forEach(tag => tag.parentNode?.removeChild(tag))
    this.tags = []
    this.ctr = 0
    if (isDevelopment) {
      this._alreadyInsertedOrderInsensitiveRule = false
    }
  }
}
