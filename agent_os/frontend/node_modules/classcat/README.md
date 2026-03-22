# Classcat

> Build a [`class`](https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/class) attribute string quickly.

- Framework agnostic, reusable, plain vanilla JavaScript.
- Up to [2.5x faster](#benchmarks) than alternatives.
- [217 B](http://bundlephobia.com/result?p=classcat) (minified+gzipped). 👌

This module makes it easy to build a space-delimited `class` attribute string from an object or array of CSS class names. Just pair each class with a boolean value to add or remove them conditionally.

```js
import cc from "classcat"

export const ToggleButton = ({ isOn, toggle }) => (
  <div className="btn" onClick={() => toggle(!isOn)}>
    <div
      className={cc({
        circle: true,
        off: !isOn,
        on: isOn,
      })}
    />
    <span className={cc({ textOff: !isOn })}>{isOn ? "ON" : "OFF"}</span>
  </div>
)
```

[Try with React](https://codepen.io/jorgebucaran/pen/NYgLwG?editors=0010), [lit-html](https://codepen.io/jorgebucaran/pen/LjPJEp?editors=1000), [Mithril](https://codepen.io/jorgebucaran/pen/JjjOjwB?editors=1100), [Superfine](https://codepen.io/jorgebucaran/pen/wrMvjz?editors=1000)

## Installation

```console
npm install classcat
```

Or without a build step—import it right in your browser.

```html
<script type="module">
  import cc from "https://unpkg.com/classcat"
</script>
```

## API

### `cc(names)`

```ps
cc(names: string | number | object | array): string
```

```js
import cc from "classcat"

cc("elf") //=> "elf"

cc(["elf", "orc", "gnome"]) //=> "elf orc gnome"

cc({
  elf: false,
  orc: null,
  gnome: undefined,
}) //=> ""

cc({
  elf: true,
  orc: false,
  gnome: true,
}) //=> "elf gnome"

cc([
  {
    elf: true,
    orc: false,
  },
  "gnome",
]) //=> "elf gnome"
```

## Benchmarks

```console
npm --prefix bench start
```

## License

[MIT](LICENSE.md)
