# @emotion/cache

### createCache

`createCache` allows for low level customization of how styles get inserted by emotion. It's intended to be used with the [`<CacheProvider/>`](https://emotion.sh/docs/cache-provider) component to override the default cache, which is created with sensible defaults for most applications.

```javascript
import createCache from '@emotion/cache'

export const myCache = createCache({
  key: 'my-prefix-key',
  stylisPlugins: [
    /* your plugins here */
  ]
})
```

### Primary use cases

- Using emotion in embedded contexts such as an `<iframe/>`

- Setting a [nonce](#nonce-string) on any `<style/>` tag emotion creates for security purposes

- Using emotion with a developer defined `<style/>` tag

- Using emotion with custom Stylis plugins

## Options

### `nonce`

`string`

A nonce that will be set on each style tag that emotion inserts for [Content Security Policies](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP).

### `stylisPlugins`

`Array<Function>`

A Stylis plugins that will be run by Stylis during preprocessing. [Read the Stylis docs to find out more](https://github.com/thysultan/stylis.js#middleware). This can be used for many purposes such as RTL.

> Note:
>
> Prefixer is just a plugin which happens to be put in default `stylisPlugins`. If you plan to use custom `stylisPlugins` and you want to have your styles prefixed automatically you must include prefixer in your custom `stylisPlugins`. You can import `prefixer` from the `stylis` module to do that (`import { prefixer } from 'stylis'`);

### `key`

`string (Pattern: [^a-z-])`

The prefix before class names. It will also be set as the value of the `data-emotion` attribute on the style tags that emotion inserts and it's used in the attribute name that marks style elements in `renderStylesToString` and `renderStylesToNodeStream`. This is **required if using multiple emotion caches in the same app**.

### `container`

`Node`

A DOM node that emotion will insert all of its style tags into. This is useful for inserting styles into iframes or windows.

### `prepend`

`boolean`

A boolean representing whether to prepend rather than append style tags into the specified container DOM node.
