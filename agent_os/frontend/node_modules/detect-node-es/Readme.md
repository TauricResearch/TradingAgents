## detect-node
> This is a fork of `detect-node`.

Differences:
- uses named export {isNode}
- has d.ts integrated
- supports ESM

### Install

```shell
npm install --save detect-node-es
```

### Usage:

```diff
-var isNode = require('detect-node');
+var {isNode} = require('detect-node-es');

if (isNode) {
  console.log("Running under Node.JS");
} else {
  alert("Hello from browser (or whatever not-a-node env)");
}
```

The check is performed as:
```js
module.exports = false;

// Only Node.JS has a process variable that is of [[Class]] process
try {
 module.exports = Object.prototype.toString.call(global.process) === '[object process]' 
} catch(e) {}

```

Thanks to Ingvar Stepanyan for the initial idea. This check is both **the most reliable I could find** and it does not use `process` env directly, which would cause browserify to include it into the build.
