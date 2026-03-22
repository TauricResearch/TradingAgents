<div align="center">
  <h1>React-remove-📜</h1>
  <br/>
   dont even scroll
  <br/>
  
  <a href="https://www.npmjs.com/package/react-remove-scroll">
    <img src="https://img.shields.io/npm/v/react-remove-scroll.svg?style=flat-square" />
  </a>
    
  <a href="https://travis-ci.org/theKashey/react-remove-scroll">
   <img src="https://img.shields.io/travis/theKashey/react-remove-scroll.svg?style=flat-square" alt="Build status">
  </a> 

  <a href="https://www.npmjs.com/package/react-remove-scroll">
   <img src="https://img.shields.io/npm/dm/react-remove-scroll.svg" alt="npm downloads">
  </a> 

  <a href="https://bundlephobia.com/result?p=react-remove-scroll">
   <img src="https://img.shields.io/bundlephobia/minzip/react-remove-scroll.svg" alt="bundle size">
  </a>   
  <br/>
</div>

react-remove-scroll
====
[![NPM version](https://img.shields.io/npm/v/react-remove-scroll.svg)](https://www.npmjs.com/package/react-remove-scroll)

Disables scroll outside of `children` node.

- 🖱 mouse and touch devices friendly
- 📈 vertical and horizontal
- 📜 removes document scroll bar maintaining it space
- ✅ support nested scrollable elements
- 🕳 supports react-portals (uses React Event system)
- ☠️ it could block literally any scroll anywhere

# Usage
Just wrap content, which should be scrollable, and everything else would not. 
```js
import {RemoveScroll} from 'react-remove-scroll';

<RemoveScroll>
  Only this content would be scrollable
</RemoveScroll>  
```

`RemoveScroll` accept following props
- `children`
- `[enabled]` - activate or deactivate component behaviour without removing it.
- `[allowPinchZoom=false]` - enabled "pinch-n-zoom" behavior. By default it might be prevented. However - pinch and zoom might break "scroll isolation", and __disabled by default__.
- `[noRelative=false]` - prevents setting `position: relative` on the body.
- `[noIsolation=false]` - disables outer event capturing. Event capturing is React friendly and unlikely be a problem.
But if you are using _shadowbox_ of some sort - you dont need it.
- `[inert=false]` - ☠️(be careful) disables events the rest of page completely using `pointer-events` except the Lock(+shards). 
React portals not friendly, might lead to production issues. Enable only for __rare__ cases, when you have to disable scrollbars somewhere on the page(except body, Lock and shards).  
- `[forwardProps]` - will forward all props to the `children`
- `[className]` - className for an internal div
- `[removeScrollBar]` - to control scroll bar removal. Set to false, if you prefer to keep it (wheel and touch scroll is still disabled).

# Size
- (🧩 full) 1.7kb after compression (excluding tslib).
---
- (👁 UI) __400b__, visual elements only
- (🚗 sidecar) 1.5kb, side effects
```js
import {sidecar} from "react-remove-scroll";
import {RemoveScroll} from 'react-remove-scroll/UI';

const sidecar = sidecar(() => import('react-remove-scroll/sidecar'));

<RemoveScroll sideCar={sidecar}>
  Will load logic from a sidecar when needed
</RemoveScroll>  
```

> Consider setting `-webkit-overflow-scrolling: touch;` on a document level for a proper mobile experience.

## Internal div
By default RemoveScroll will create a div to handle and capture events.
You may specify `className` for it, if you need, or __remove it__.

The following code samples will produce the same output
```js
<RemoveScroll className="scroll">
  Only this content would be scrollable
</RemoveScroll>
```

```js
<RemoveScroll forwardProps>
  <div className="scroll"> //RemoveScroll will inject props to this div
    Only this content would be scrollable
  </div>
</RemoveScroll> 
```
Pick the first one if you don't need a second.

## Position:fixed elements
To properly size these elements please add a special className to them.
```jsx
import {RemoveScroll} from 'react-remove-scroll';

// to make "width: 100%"
<div className={cx(classWithPositionFixed, RemoveScroll.classNames.fullWidth)} />

// to make "right:0"
<div className={cx(classWithPositionFixed, RemoveScroll.classNames.zeroRight)} />
```
See [react-remove-scroll-bar](https://github.com/theKashey/react-remove-scroll-bar) documentation for details.

## More than one lock
When stacked more is active (default) only one (last) component would be active.

## Over isolation
That could happen - 
you disable scroll on the body, 
you are suppressing all scroll and wheel events,
and you are ghosting the rest of the page by the `inert` prop.

Only something inside Lock does exists for the browser, and that might be less than you expected.

Dont forget about `shard`, dont forget - `inert` is not portals friendly, dont forget - you dont need over isolation in most of the cases.

> just be careful! 

# Performance
To do the job this library setup _non_ passive event listener. Chrome dev tools would complain about it, as a 
performance no-op.

We have to use synchronous scroll/touch handler, and it may affect scrolling performance.

Consider using `noIsolation` mode, if you have large scrollable areas.

# Supported React versions
- v1 supports React 15/16
- v2 requires 16.8.0+ (hooks)

# Scroll-Locky
This is a refactoring of another library - [react-scroll-locky](https://github.com/theKashey/react-scroll-locky) -
to make package smaller and more react-portals friendly.

## See also
 - [react-focus-on](https://github.com/theKashey/react-focus-on) - Finite Modal creator (uses Scroll-Locky) underneath.
 - [react-locky](https://github.com/theKashey/react-locky) - React event canceler
 - [react-scrolllock](https://github.com/jossmac/react-scrolllock) - React scroll lock
 - [scroll-lock](https://github.com/FL3NKEY/scroll-lock) - DOM scroll lock
 - [body-scroll-lock](https://github.com/willmcpo/body-scroll-lock) - DOM scroll lock
 
 > This package is relative smaller(1), more react friendly(2), works with non zero body margins(3), and has a better "overscroll" management. 

# License
MIT