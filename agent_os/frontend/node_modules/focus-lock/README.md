# focus-lock

It is a trap! We got your focus and will not let him out!

[![NPM](https://nodei.co/npm/focus-lock.png?downloads=true&stars=true)](https://nodei.co/npm/react-focus-lock/)

**Important** - this is a low level package to be used in order to create "focus lock".
It does not provide any "lock" capabilities by itself, only helpers you can use to create one

# Focus-lock implementations

This is a base package for:

- [react-focus-lock](https://github.com/theKashey/react-focus-lock)
  [![downloads](https://badgen.net/npm/dm/react-focus-lock)](https://www.npmtrends.com/react-focus-lock)
- [vue-focus-lock](https://github.com/theKashey/vue-focus-lock)
  [![downloads](https://badgen.net/npm/dm/vue-focus-lock)](https://www.npmtrends.com/vue-focus-lock)
- [dom-focus-lock](https://github.com/theKashey/dom-focus-lock)
  [![downloads](https://badgen.net/npm/dm/dom-focus-lock)](https://www.npmtrends.com/dom-focus-lock)

The common use case will look like final realization.

```js
import { moveFocusInside, focusInside } from 'focus-lock';

if (someNode && !focusInside(someNode)) {
  moveFocusInside(someNode, lastActiveFocus /* very important to know */);
}
```

> note that tracking `lastActiveFocus` is on the end user.

## Declarative control

`focus-lock` provides not only API to be called by some other scripts, but also a way one can leave instructions inside HTML markup
to amend focus behavior in a desired way.

These are `data-attributes` one can add on the elements:

- control
  - `data-focus-lock=[group-name]` to create a focus group (scattered focus)
  - `data-focus-lock-disabled="disabled"` marks such group as disabled and removes from the list. Equal to removing elements from the DOM.
  - `data-no-focus-lock` focus-lock will ignore/allow focus inside marked area. Focus on this elements will not be managed by focus-lock.
- autofocus (via `moveFocusInside(someNode, null)`)
  - `data-autofocus` will autofocus marked element on activation.
  - `data-autofocus-inside` focus-lock will try to autofocus elements within selected area on activation.
  - `data-no-autofocus` focus-lock will not autofocus any node within marked area on activation.

These markers are available as `import * as markers from 'focus-lock/constants'`

## Additional API

### Get focusable nodes

Returns visible and focusable nodes

```ts
import { expandFocusableNodes, getFocusableNodes, getTabbleNodes } from 'focus-lock';

// returns all focusable nodes inside given locations
getFocusableNodes([many, nodes])[0].node.focus();

// returns all nodes reacheable in the "taborder" inside given locations
getTabbleNodes([many, nodes])[0].node.focus();

// returns an "extended information" about focusable nodes inside. To be used for advances cases (react-focus-lock)
expandFocusableNodes(singleNodes);
```

### Programmatic focus management

Allows moving back and forth between focusable/tabbable elements

```ts
import { focusNextElement, focusPrevElement } from 'focus-lock';
focusNextElement(document.activeElement, {
  scope: theBoundingDOMNode,
}); // -> next tabbable element
```

### Return focus

Advanced API to return focus (from the Modal) to the last or the next best location

```ts
import { captureFocusRestore } from 'focus-lock';
const restore = captureFocusRestore(element);
// ....
restore()?.focus(); // restores focus the the element, or it's siblings in case it no longer exists
```

# WHY?

From [MDN Article about accessible dialogs](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/ARIA_Techniques/Using_the_dialog_role):

- The dialog must be properly labeled
- Keyboard **focus must be managed** correctly

This one is about managing the focus.

I'v got a good [article about focus management, dialogs and WAI-ARIA](https://medium.com/@antonkorzunov/its-a-focus-trap-699a04d66fb5).

# Focus fighting

It is possible, that more that one "focus management system" is present on the site.
For example, you are using FocusLock for your content, and also using some
Modal dialog, with FocusTrap inside.

Both system will try to do their best, and move focus into their managed areas.
Stack overflow. Both are dead.

Focus Lock(React-Focus-Lock, Vue-Focus-Lock and so on) implements anti-fighting
protection - once the battle is detected focus-lock will surrender(as long there is no way to win this fight).

You may also land a peace by special data attribute - `data-no-focus-lock`(constants.FOCUS_ALLOW). It will
remove focus management from all nested elements, letting you open modals, forms, or
use any third party component safely. Focus lock will just do nothing, while focus is on the marked elements.

# API

`default(topNode, lastNode)` (aka setFocus), moves focus inside topNode, keeping in mind that last focus inside was - lastNode

# Licence

MIT
