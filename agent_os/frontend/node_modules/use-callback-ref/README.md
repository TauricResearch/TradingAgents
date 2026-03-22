<div align="center">
  <h1>🤙 use-callback-ref 📞</h1>
  <br/>
  The same `useRef` but it will callback: 📞 Hello! Your ref was changed!
  <br/>
    <a href="https://www.npmjs.com/package/use-callback-ref">
      <img src="https://img.shields.io/npm/v/use-callback-ref.svg?style=flat-square" />
    </a>
    <a href="https://travis-ci.org/theKashey/use-callback-ref">
       <img alt="Travis" src="https://img.shields.io/travis/theKashey/use-callback-ref/master.svg?style=flat-square">
    </a>
    <a href="https://bundlephobia.com/result?p=use-callback-ref">
      <img src="https://img.shields.io/bundlephobia/minzip/use-callback-ref.svg" alt="bundle size">
    </a> 
</div>

---

> Keep in mind that useRef doesn't notify you when its content changes.
> Mutating the .current property doesn't cause a re-render.
> If you want to run some code when React attaches or detaches a ref to a DOM node,
> you may want to use ~~a callback ref instead~~ .... **useCallbackRef** instead.

– [Hooks API Reference](https://reactjs.org/docs/hooks-reference.html#useref)

Read more about `use-callback` pattern and use cases:

- https://dev.to/thekashey/the-same-useref-but-it-will-callback-8bo

This library exposes helpers to handle any case related to `ref` _lifecycle_

- `useCallbackRef` - react on a ref change (replacement for `useRef`)
  - `createCallbackRef` - - low level version of `useCallbackRef`
- `useMergeRefs` - merge multiple refs together creating a stable return ref
  - `mergeRefs` - low level version of `useMergeRefs`
- `useTransformRef` - transform one ref to another (replacement for `useImperativeHandle`)
  - `transformRef` - low level version of `useTransformRef`
- `useRefToCallback` - convert RefObject to an old callback-style ref
  - `refToCallback` - low level version of `useRefToCallback`
- `assignRef` - assign value to the ref, regardless it is RefCallback or RefObject

All functions are tree shakable, but even together it's **less then 300b**.

# API

💡 Some commands are hooks based, and returns the same refs/functions every render.
But some are not, to be used in classes or non-react code.

## useRef API

🤔 Use case: every time you have to react to ref change

API is 99% compatible with React `createRef` and `useRef`, and just adds another argument - `callback`,
which would be called on **ref update**.

#### createCallbackRef - to replace React.createRef

- `createCallbackRef(callback)` - would call provided `callback` when ref is changed.

#### useCallbackRef - to replace React.useRef

- `useCallbackRef(initialValue, callback)` - would call provided `callback` when ref is changed.

> `callback` in both cases is `callback(newValue, oldValue)`. Callback would not be called if newValue and oldValue is the same.

```js
import { useRef, createRef, useState } from 'react';
import { useCallbackRef, createCallbackRef } from 'use-callback-ref';

const Component = () => {
  const [, forceUpdate] = useState();
  // I dont need callback when ref changes
  const ref = useRef(null);

  // but sometimes - it could be what you need
  const anotherRef = useCallbackRef(null, () => forceUpdate());

  useEffect(() => {
    // now it's just possible
  }, [anotherRef.current]); // react to dom node change
};
```

💡 You can use `useCallbackRef` to convert RefObject into RefCallback, creating bridges between the old and the new code

```js
// some old component
const onRefUpdate = (newRef) => {...}
const refObject = useCallbackRef(null, onRefUpdate);
// ...
<SomeNewComponent ref={refObject}/>
```

## assignRef

🤔 Use case: every time you need to assign ref manually, and you dont know the shape of the ref

`assignRef(ref, value)` - assigns `values` to the `ref`. `ref` could be RefObject or RefCallback.

```
🚫 ref.current = value // what if it's a callback-ref?
🚫 ref(value) // but what if it's a object ref?

import {assignRef} from "use-callback-ref";
✅ assignRef(ref, value);
```

## useTransformRef (to replace React.useImperativeHandle)

🤔 Use case: ref could be different.
`transformRef(ref, tranformer):Ref` - return a new `ref` which would propagate all changes to the provided `ref` with applied `transform`

```js
// before
const ResizableWithRef = forwardRef((props, ref) => <Resizable {...props} ref={(i) => i && ref(i.resizable)} />);

// after

const ResizableWithRef = forwardRef((props, ref) => (
  <Resizable {...props} ref={transformRef(ref, (i) => (i ? i.resizable : null))} />
));
```

## refToCallback

`refToCallback(ref: RefObject): RefCallback` - for compatibility between the old and the new code.
For the compatibility between `RefCallback` and RefObject use `useCallbackRef(undefined, callback)`

## useMergeRefs

`mergeRefs(refs: arrayOfRefs, [defaultValue]):ReactMutableRef` - merges a few refs together

When developing low level UI components, it is common to have to use a local ref but also support an external one using React.forwardRef. Natively, React does not offer a way to set two refs inside the ref property. This is the goal of this small utility.

```js
import React from 'react';
import { useMergeRefs } from 'use-callback-ref';

const MergedComponent = React.forwardRef((props, ref) => {
  const localRef = React.useRef();
  // ...
  // both localRef and ref would be populated with the `ref` to a `div`
  return <div ref={useMergeRefs([localRef, ref])} />;
});
```

💡 - `useMergeRefs` will always give you the same return, and you don't have to worry about `[localRef, ref]` unique every render.

## mergeRefs

`mergeRefs(refs: arrayOfRefs, [defaultValue]):ReactMutableRef` - merges a few refs together
is a non-hook based version. Will produce the new `ref` every run, causing the old one to unmount, and be _populated_ with the `null` value.

> mergeRefs are based on https://github.com/smooth-code/react-merge-refs, just exposes a RefObject, instead of a callback

`mergeRefs` are "safe" to use as a part of other hooks-based commands, but don't forget - it returns a new object every call.

# Similar packages:

- [apply-ref](https://github.com/mitchellhamilton/apply-ref) - `applyRefs` is simular to `mergeRef`, `applyRef` is similar to `assignRef`
- [useForkRef](https://react-hooks.org/docs/use-fork-ref) - `useForkRef` is simular to `useMergeRefs`, but accepts only two arguments.
- [react-merge-refs](https://github.com/gregberge/react-merge-refs) - `merge-refs` is simular to `useMergeRefs`, but not a hook and does not provide "stable" reference.

---

> Is it a rocket science? No, `RefObject` is no more than `{current: ref}`, and `use-callback-ref` is no more than `getter` and `setter` on that field.

# License

MIT
