react-style-singleton
====

__300b__ with all dependencies, minified and gzipped


Creates a style component with internal _tracker_.
- Adds styles to the browser on the __first__ instance mount.
- Removes after the __last__ instance unmount.
- Thus helps you deliver styles you need to the customer, and clean up later.
- Is not server-side rendering compatible!


# API

## Component

```js
import {styleSingleton} from 'react-style-singleton'

const Style = styleSingleton();

export const App = () => (
  <Style styles={'body {color:red}'} />
);
```

## Hook

```js
import {styleHookSingleton} from 'react-style-singleton';

const useStyle = styleHookSingleton();
const useAnotherStyle = styleHookSingleton();

export const App = () => {
  useStyle('div {color:red}');
  useAnotherStyle('body { background-color:red }');
  return (<div />);
}
```

# License

MIT