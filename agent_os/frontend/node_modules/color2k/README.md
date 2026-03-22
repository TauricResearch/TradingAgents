# [color2k](https://color2k.com)

[![bundlephobia](https://badgen.net/bundlephobia/minzip/color2k)](https://bundlephobia.com/result?p=color2k) [![github status checks](https://badgen.net/github/checks/ricokahler/color2k)](https://github.com/ricokahler/color2k/actions) [![codecov](https://codecov.io/gh/ricokahler/color2k/branch/master/graph/badge.svg)](https://codecov.io/gh/ricokahler/color2k) ![weekly downloads](https://badgen.net/npm/dw/color2k) [![semantic-release](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--release-e10079.svg)](https://github.com/semantic-release/semantic-release)

> a color parsing and manipulation lib served in roughly 2kB or less (2.8kB to be more precise)

color2k is a color parsing and manipulation library with the objective of keeping the bundle size as small as possible while still satisfying all of your color manipulation needs in an sRGB space.

The full bundle size is [currently 2.8kB](https://bundlephobia.com/result?p=color2k) but [gets as small as 2.1k](https://bundlejs.com/?q=color2k&treeshake=[{darken}]) with tree shaking.

## Size comparison

| lib                                                       | size                                                  |
| --------------------------------------------------------- | ----------------------------------------------------- |
| [chroma-js](https://github.com/gka/chroma.js)             | [13.7kB](https://bundlephobia.com/result?p=chroma-js) |
| [polished](https://github.com/styled-components/polished) | [11.2kB](https://bundlephobia.com/result?p=polished)  |
| [color](https://github.com/Qix-/color)                    | [7.6kB](https://bundlephobia.com/result?p=color)      |
| [tinycolor2](https://github.com/bgrins/TinyColor)         | [5kB](https://bundlephobia.com/result?p=tinycolor2)   |
| color2k                                                   | [2.8kB](https://bundlephobia.com/result?p=color2k) 😎 |

👋 Compare tree-shaken bundle outputs on [bundlejs.com](https://bundlejs.com/?share=PTAEFcDsGMHsFt4FNIBdQENIBNRIB4AOsATuvLNuADZIDOoqsoc8hGJSjAFkgJYlQdPgC96oAFASQeIqXQAqUADMSCUACJo3NfAwBaAFZ0NAbmlgCxMqCWr1G4tT51e2MxdnXFK3ZrjUpB4yVvK2vg6ofJAAngGkAEweoTYA3tgcANYoAL4R8P6wgSQJmR5AA)

## Installation

Install with a package manager such as `npm`

```
npm i color2k
```

**OR** use with [skypack.dev](https://www.skypack.dev/) in supported environments (e.g. [deno](https://deno.land/manual/linking_to_external_code), [modern browsers](https://docs.skypack.dev/#whats-old-is-new-again)).

```js
import { darken, transparentize } from 'https://cdn.skypack.dev/color2k?min';
```

## Usage

```js
import { darken, transparentize } from 'color2k';

// e.g.
darken('blue', 0.1);
transparentize('red', 0.5);
```

## How so small?

There are two secrets that keep this lib especially small:

1. Simplicity — only handles basic color manipulation functions
2. Less branching in code — only support two color models as outputs, namely `rgba` and `hsla`

### Why only `rgba` and `hsla` as outputs?

This lib was created with the use case of CSS-in-JS in mind. At the end of the day, all that matters is that the browser can understand the color string you gave it as a `background-color`.

Because only those two color models are supported, we don't have to add code to deal with optional alpha channels or converting to non-browser supported color models (e.g. CMYK).

We believe that this lib is sufficient for all of your color manipulation needs. If we're missing a feature, feel free to [open an issue](https://github.com/ricokahler/color2k/issues/new) 😎.

## Credits

Heavy credits goes to polished.js and sass. Much of the implementation of this lib is copied from polished!

<!-- DOCS-END -->

## API and Documentation

[Head over to the docs site](https://color2k.com)
