# @emotion/weak-memoize

> A memoization function that uses a WeakMap

## Install

```bash
yarn add @emotion/weak-memoize
```

## Usage

Because @emotion/weak-memoize uses a WeakMap the argument must be a non primitive type, e.g. objects, functions, arrays and etc. The function passed to `weakMemoize` must also only accept a single argument.

```jsx
import weakMemoize from '@emotion/weak-memoize'

let doThing = weakMemoize(({ someProperty }) => {
  return { newName: someProperty }
})

let obj = { someProperty: true }

let firstResult = doThing(obj)

let secondResult = doThing(obj)

firstResult === secondResult // true

let newObj = { someProperty: true }

let thirdResult = doThing(newObj)

thirdResult === firstResult // false
```
