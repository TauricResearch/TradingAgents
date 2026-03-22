# Welcome to Chakra UI ⚡️

[![All Contributors](https://img.shields.io/badge/all_contributors-2-orange.svg?style=flat-square)](#contributors-)

- Works out of the box. Chakra UI contains a set of polished React components
  that work out of the box.

- Flexible & composable. Chakra UI components are built on top of a React UI
  Primitive for endless composability.

- Accessible. Chakra UI components follows the WAI-ARIA guidelines
  specifications.

- Dark Mode 😍: All components are dark mode compatible.

## Looking for the documentation?

https://chakra-ui.com

## Installing Chakra UI

⚡️Chakra UI is made up of multiple components and tools which you can import
one by one. All you need to do is install the `@chakra-ui/react` package:

```sh
$ yarn add @chakra-ui/react
# or
$ npm install --save @chakra-ui/react
```

# Getting set up

To start using the components, please follow these steps:

1. Wrap your application in a `ThemeProvider` provided by **@chakra-ui/react**

```jsx
import { ThemeProvider, ColorModeProvider } from "@chakra-ui/react"

const App = ({ children }) => (
  <ThemeProvider>
    <ColorModeProvider>{children}</ColorModeProvider>
  </ThemeProvider>
)
```

`ColorModeProvider` is a context that provides light mode and dark mode values
to the components. It also comes with a function to toggle between light/dark
mode.

2. Now you can start using components like so!:

```jsx
import { Button } from "@chakra-ui/react"

const App = () => <Button>I just consumed some ⚡️Chakra!</Button>
```

# Contributing

Feel like contributing? That's awesome! We have a
[contributing guide](../../CONTRIBUTING.md) to help guide you.

The components to be built come from the
[Aria Practices Design Patterns and Widgets](https://www.w3.org/TR/wai-aria-practices-1.1).

## Contributors ✨

Thanks goes to these wonderful people
([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tr>
    <td style="text-align: center"><a href="https://github.com/segunadebayo"><img src="https://avatars2.githubusercontent.com/u/6916170?v=4" width="100px;" alt="Segun Adebayo"/><br /><sub><b>Segun Adebayo</b></sub></a><br /><a href="https://github.com/chakra-ui/chakra-ui/commits?author=segunadebayo" title="Code">💻</a> <a href="#maintenance-segunadebayo" title="Maintenance">🚧</a> <a href="https://github.com/chakra-ui/chakra-ui/commits?author=segunadebayo" title="Documentation">📖</a> <a href="#example-segunadebayo" title="Examples">💡</a> <a href="#design-segunadebayo" title="Design">🎨</a></td>
    <td style="text-align: center"><a href="https://github.com/tioluwani94"><img src="https://avatars1.githubusercontent.com/u/11310046?v=4" width="100px;" alt="Tioluwani Kolawole"/><br /><sub><b>Tioluwani Kolawole</b></sub></a><br /><a href="https://github.com/chakra-ui/chakra-ui/commits?author=tioluwani94" title="Documentation">📖</a> <a href="#example-tioluwani94" title="Examples">💡</a> <a href="#maintenance-tioluwani94" title="Maintenance">🚧</a></td>
  </tr>
</table>

<!-- markdownlint-enable -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the
[all-contributors](https://github.com/all-contributors/all-contributors)
specification. Contributions of any kind welcome!
