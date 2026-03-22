import { EmotionCache } from '@emotion/utils'
import {
  alloc,
  dealloc,
  delimit,
  Element,
  from,
  Middleware,
  next,
  peek,
  position,
  slice,
  token
} from 'stylis'

// based on https://github.com/thysultan/stylis.js/blob/e6843c373ebcbbfade25ebcc23f540ed8508da0a/src/Tokenizer.js#L239-L244
const identifierWithPointTracking = (
  begin: number,
  points: number[],
  index: number
) => {
  let previous = 0
  let character = 0

  while (true) {
    previous = character
    character = peek()

    // &\f
    if (previous === 38 && character === 12) {
      points[index] = 1
    }

    if (token(character)) {
      break
    }

    next()
  }

  return slice(begin, position)
}

const toRules = (parsed: string[], points: number[]) => {
  // pretend we've started with a comma
  let index = -1
  let character = 44

  do {
    switch (token(character)) {
      case 0:
        // &\f
        if (character === 38 && peek() === 12) {
          // this is not 100% correct, we don't account for literal sequences here - like for example quoted strings
          // stylis inserts \f after & to know when & where it should replace this sequence with the context selector
          // and when it should just concatenate the outer and inner selectors
          // it's very unlikely for this sequence to actually appear in a different context, so we just leverage this fact here
          points[index] = 1
        }
        parsed[index] += identifierWithPointTracking(
          position - 1,
          points,
          index
        )
        break
      case 2:
        parsed[index] += delimit(character)
        break
      case 4:
        // comma
        if (character === 44) {
          // colon
          parsed[++index] = peek() === 58 ? '&\f' : ''
          points[index] = parsed[index].length
          break
        }
      // fallthrough
      default:
        parsed[index] += from(character)
    }
  } while ((character = next()))

  return parsed
}

const getRules = (value: string, points: number[]) =>
  dealloc(toRules(alloc(value) as string[], points))

// WeakSet would be more appropriate, but only WeakMap is supported in IE11
const fixedElements = /* #__PURE__ */ new WeakMap()

export let compat: Middleware = element => {
  if (
    element.type !== 'rule' ||
    !element.parent ||
    // positive .length indicates that this rule contains pseudo
    // negative .length indicates that this rule has been already prefixed
    element.length < 1
  ) {
    return
  }

  let value = element.value
  let parent: Element | null = element.parent
  let isImplicitRule =
    element.column === parent.column && element.line === parent.line

  while (parent.type !== 'rule') {
    parent = parent.parent
    if (!parent) return
  }

  // short-circuit for the simplest case
  if (
    element.props.length === 1 &&
    value.charCodeAt(0) !== 58 /* colon */ &&
    !fixedElements.get(parent)
  ) {
    return
  }

  // if this is an implicitly inserted rule (the one eagerly inserted at the each new nested level)
  // then the props has already been manipulated beforehand as they that array is shared between it and its "rule parent"
  if (isImplicitRule) {
    return
  }

  fixedElements.set(element, true)

  const points: number[] = []
  const rules = getRules(value, points)
  const parentRules = parent.props

  for (let i = 0, k = 0; i < rules.length; i++) {
    for (let j = 0; j < parentRules.length; j++, k++) {
      ;(element.props as string[])[k] = points[i]
        ? rules[i].replace(/&\f/g, parentRules[j])
        : `${parentRules[j]} ${rules[i]}`
    }
  }
}

export let removeLabel: Middleware = element => {
  if (element.type === 'decl') {
    const value = element.value
    if (
      // charcode for l
      value.charCodeAt(0) === 108 &&
      // charcode for b
      value.charCodeAt(2) === 98
    ) {
      // this ignores label
      element.return = ''
      element.value = ''
    }
  }
}

const ignoreFlag =
  'emotion-disable-server-rendering-unsafe-selector-warning-please-do-not-use-this-the-warning-exists-for-a-reason'

const isIgnoringComment = (element: Element) =>
  element.type === 'comm' &&
  (element.children as string).indexOf(ignoreFlag) > -1

export let createUnsafeSelectorsAlarm =
  (cache: Pick<EmotionCache, 'compat'>): Middleware =>
  (element, index, children) => {
    if (element.type !== 'rule' || cache.compat) return

    const unsafePseudoClasses = element.value.match(
      /(:first|:nth|:nth-last)-child/g
    )

    if (unsafePseudoClasses) {
      const isNested = !!element.parent
      // in nested rules comments become children of the "auto-inserted" rule and that's always the `element.parent`
      //
      // considering this input:
      // .a {
      //   .b /* comm */ {}
      //   color: hotpink;
      // }
      // we get output corresponding to this:
      // .a {
      //   & {
      //     /* comm */
      //     color: hotpink;
      //   }
      //   .b {}
      // }
      const commentContainer = isNested
        ? element.parent!.children
        : // global rule at the root level
          children

      for (let i = commentContainer.length - 1; i >= 0; i--) {
        const node = commentContainer[i] as Element

        if (node.line < element.line) {
          break
        }

        // it is quite weird but comments are *usually* put at `column: element.column - 1`
        // so we seek *from the end* for the node that is earlier than the rule's `element` and check that
        // this will also match inputs like this:
        // .a {
        //   /* comm */
        //   .b {}
        // }
        //
        // but that is fine
        //
        // it would be the easiest to change the placement of the comment to be the first child of the rule:
        // .a {
        //   .b { /* comm */ }
        // }
        // with such inputs we wouldn't have to search for the comment at all
        // TODO: consider changing this comment placement in the next major version
        if (node.column < element.column) {
          if (isIgnoringComment(node)) {
            return
          }
          break
        }
      }

      unsafePseudoClasses.forEach(unsafePseudoClass => {
        console.error(
          `The pseudo class "${unsafePseudoClass}" is potentially unsafe when doing server-side rendering. Try changing it to "${
            unsafePseudoClass.split('-child')[0]
          }-of-type".`
        )
      })
    }
  }

let isImportRule = (element: Element) =>
  element.type.charCodeAt(1) === 105 && element.type.charCodeAt(0) === 64

const isPrependedWithRegularRules = (index: number, children: Element[]) => {
  for (let i = index - 1; i >= 0; i--) {
    if (!isImportRule(children[i])) {
      return true
    }
  }
  return false
}

// use this to remove incorrect elements from further processing
// so they don't get handed to the `sheet` (or anything else)
// as that could potentially lead to additional logs which in turn could be overhelming to the user
const nullifyElement = (element: Element) => {
  element.type = ''
  element.value = ''
  element.return = ''
  element.children = ''
  element.props = ''
}

export let incorrectImportAlarm: Middleware = (element, index, children) => {
  if (!isImportRule(element)) {
    return
  }

  if (element.parent) {
    console.error(
      "`@import` rules can't be nested inside other rules. Please move it to the top level and put it before regular rules. Keep in mind that they can only be used within global styles."
    )
    nullifyElement(element)
  } else if (isPrependedWithRegularRules(index, children)) {
    console.error(
      "`@import` rules can't be after other rules. Please put your `@import` rules before your other rules."
    )
    nullifyElement(element)
  }
}
