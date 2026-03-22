# get-nonce

just returns a **nonce** (number used once). No batteries included in those 46 bytes of this library.

---

- ✅ build in `webpack` support via `__webpack_nonce__`

# API

- `getNonce(): string|undefined` - returns the current `nonce`
- `setNonce(newValue)` - set's nonce value

## Why?

Why we need a library to access `__webpack_nonce__`? Abstractions!

"I", as a library author, don't want to "predict" the platform "you" going to use.
"I", as well, want an easier way to test and control `nonce` value.

Like - `nonce` is supported out of the box only by webpack, what you are going to do?

This is why this "man-in-the-middle" was created.
Yep, think about `left-pad` :)

## Webpack

> https://webpack.js.org/guides/csp/

To activate the feature set a **webpack_nonce** variable needs to be included in your entry script.

```
__webpack_nonce__ = uuid(); // for example
```

Without `webpack` `__webpack_nonce__` is actually just a global variable,
which makes it actually bundler independent,
however "other bundlers" are able to replicate it only setting it as a global variable
(as here in tests) which violates a "secure" nature of `nonce`.

`get-nonce` is not global.

## Used in

- `react-style-singleton` <- `react-remove-scroll` <- `react-focus-on`

## Inspiration

- [this issue](https://github.com/theKashey/react-remove-scroll/issues/21)
- [styled-components](https://github.com/styled-components/styled-components/blob/147b0e9a1f10786551b13fd27452fcd5c678d5e0/packages/styled-components/src/utils/nonce.js)

# Licence

MIT
