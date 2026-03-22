<h1>react-remove-scroll-bar</h1>

[![npm](https://img.shields.io/npm/v/react-remove-scroll-bar.svg)](https://www.npmjs.com/package/react-remove-scroll-bar)
[![bundle size](https://badgen.net/bundlephobia/minzip/react-remove-scroll-bar)](https://bundlephobia.com/result?p=react-remove-scroll-bar)
[![downloads](https://badgen.net/npm/dm/react-remove-scroll-bar)](https://www.npmtrends.com/react-remove-scroll-bar)

<hr />

> v1+ for React 15, v2+ requires React 16.8+

Removes scroll bar (by setting `overflow: hidden` on body), and preserves the scroll bar "gap".

Read - it just makes scroll bar invisible.

Does nothing if scroll bar does not consume any space.

# Usage

```js
import {RemoveScrollBar} from 'react-remove-scroll-bar';

<RemoveScrollBar /> -> no scroll bar
```

### The Right Border
To prevent content jumps __position:fixed__ elements with `right:0`  should have additional classname applied.
It will just provide a _non-zero_ right, when it needed, to maintain the right "gap".
```js
import {zeroRightClassName,fullWidthClassName, noScrollbarsClassName} from 'react-remove-scroll-bar';

// to set `right:0` on an element
<div className={zeroRightClassName} />

// to set `width:100%` on an element
<div className={fullWidthClassName} />

// to remove scrollbar from an element
<div className={noScrollbarsClassName} />

```

# Size
500b after compression (excluding tslib).

# Scroll-Locky
All code is a result of a [react-scroll-locky](https://github.com/theKashey/react-scroll-locky) refactoring.

# Article
There is a medium article about preventing the body scroll - [How to fight the <body> scroll](https://medium.com/@antonkorzunov/how-to-fight-the-body-scroll-2b00267b37ac)

# License
MIT
