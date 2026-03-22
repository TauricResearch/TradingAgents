<p align="center">
  <img src="bear.jpg" />
</p>

[![Build Status](https://img.shields.io/github/actions/workflow/status/pmndrs/zustand/lint-and-type.yml?branch=main&style=flat&colorA=000000&colorB=000000)](https://github.com/pmndrs/zustand/actions?query=workflow%3ALint)
[![Build Size](https://img.shields.io/bundlephobia/minzip/zustand?label=bundle%20size&style=flat&colorA=000000&colorB=000000)](https://bundlephobia.com/result?p=zustand)
[![Version](https://img.shields.io/npm/v/zustand?style=flat&colorA=000000&colorB=000000)](https://www.npmjs.com/package/zustand)
[![Downloads](https://img.shields.io/npm/dt/zustand.svg?style=flat&colorA=000000&colorB=000000)](https://www.npmjs.com/package/zustand)
[![Discord Shield](https://img.shields.io/discord/740090768164651008?style=flat&colorA=000000&colorB=000000&label=discord&logo=discord&logoColor=ffffff)](https://discord.gg/poimandres)

A small, fast and scalable bearbones state-management solution using simplified flux principles. Has a comfy API based on hooks, isn't boilerplatey or opinionated.

Don't disregard it because it's cute. It has quite the claws, lots of time was spent dealing with common pitfalls, like the dreaded [zombie child problem](https://react-redux.js.org/api/hooks#stale-props-and-zombie-children), [react concurrency](https://github.com/bvaughn/rfcs/blob/useMutableSource/text/0000-use-mutable-source.md), and [context loss](https://github.com/facebook/react/issues/13332) between mixed renderers. It may be the one state-manager in the React space that gets all of these right.

You can try a live demo [here](https://githubbox.com/pmndrs/zustand/tree/main/examples/demo).

```bash
npm i zustand
```

:warning: This readme is written for JavaScript users. If you are a TypeScript user, be sure to check out our [TypeScript Usage section](#typescript-usage).

## First create a store

Your store is a hook! You can put anything in it: primitives, objects, functions. State has to be updated immutably and the `set` function [merges state](./docs/guides/immutable-state-and-merging.md) to help it.

```jsx
import { create } from 'zustand'

const useBearStore = create((set) => ({
  bears: 0,
  increasePopulation: () => set((state) => ({ bears: state.bears + 1 })),
  removeAllBears: () => set({ bears: 0 }),
}))
```

## Then bind your components, and that's it!

Use the hook anywhere, no providers are needed. Select your state and the component will re-render on changes.

```jsx
function BearCounter() {
  const bears = useBearStore((state) => state.bears)
  return <h1>{bears} around here ...</h1>
}

function Controls() {
  const increasePopulation = useBearStore((state) => state.increasePopulation)
  return <button onClick={increasePopulation}>one up</button>
}
```

### Why zustand over redux?

- Simple and un-opinionated
- Makes hooks the primary means of consuming state
- Doesn't wrap your app in context providers
- [Can inform components transiently (without causing render)](#transient-updates-for-often-occurring-state-changes)

### Why zustand over context?

- Less boilerplate
- Renders components only on changes
- Centralized, action-based state management

---

# Recipes

## Fetching everything

You can, but bear in mind that it will cause the component to update on every state change!

```jsx
const state = useBearStore()
```

## Selecting multiple state slices

It detects changes with strict-equality (old === new) by default, this is efficient for atomic state picks.

```jsx
const nuts = useBearStore((state) => state.nuts)
const honey = useBearStore((state) => state.honey)
```

If you want to construct a single object with multiple state-picks inside, similar to redux's mapStateToProps, you can use [useShallow](./docs/guides/prevent-rerenders-with-use-shallow.md) to prevent unnecessary rerenders when the selector output does not change according to shallow equal.

```jsx
import { create } from 'zustand'
import { useShallow } from 'zustand/react/shallow'

const useBearStore = create((set) => ({
  bears: 0,
  increasePopulation: () => set((state) => ({ bears: state.bears + 1 })),
  removeAllBears: () => set({ bears: 0 }),
}))

// Object pick, re-renders the component when either state.nuts or state.honey change
const { nuts, honey } = useBearStore(
  useShallow((state) => ({ nuts: state.nuts, honey: state.honey })),
)

// Array pick, re-renders the component when either state.nuts or state.honey change
const [nuts, honey] = useBearStore(
  useShallow((state) => [state.nuts, state.honey]),
)

// Mapped picks, re-renders the component when state.treats changes in order, count or keys
const treats = useBearStore(useShallow((state) => Object.keys(state.treats)))
```

For more control over re-rendering, you may provide any custom equality function.

```jsx
const treats = useBearStore(
  (state) => state.treats,
  (oldTreats, newTreats) => compare(oldTreats, newTreats),
)
```

## Overwriting state

The `set` function has a second argument, `false` by default. Instead of merging, it will replace the state model. Be careful not to wipe out parts you rely on, like actions.

```jsx
import omit from 'lodash-es/omit'

const useFishStore = create((set) => ({
  salmon: 1,
  tuna: 2,
  deleteEverything: () => set({}, true), // clears the entire store, actions included
  deleteTuna: () => set((state) => omit(state, ['tuna']), true),
}))
```

## Async actions

Just call `set` when you're ready, zustand doesn't care if your actions are async or not.

```jsx
const useFishStore = create((set) => ({
  fishies: {},
  fetch: async (pond) => {
    const response = await fetch(pond)
    set({ fishies: await response.json() })
  },
}))
```

## Read from state in actions

`set` allows fn-updates `set(state => result)`, but you still have access to state outside of it through `get`.

```jsx
const useSoundStore = create((set, get) => ({
  sound: 'grunt',
  action: () => {
    const sound = get().sound
    ...
```

## Reading/writing state and reacting to changes outside of components

Sometimes you need to access state in a non-reactive way or act upon the store. For these cases, the resulting hook has utility functions attached to its prototype.

:warning: This technique is not recommended for adding state in [React Server Components](https://github.com/reactjs/rfcs/blob/main/text/0188-server-components.md) (typically in Next.js 13 and above). It can lead to unexpected bugs and privacy issues for your users. For more details, see [#2200](https://github.com/pmndrs/zustand/discussions/2200).

```jsx
const useDogStore = create(() => ({ paw: true, snout: true, fur: true }))

// Getting non-reactive fresh state
const paw = useDogStore.getState().paw
// Listening to all changes, fires synchronously on every change
const unsub1 = useDogStore.subscribe(console.log)
// Updating state, will trigger listeners
useDogStore.setState({ paw: false })
// Unsubscribe listeners
unsub1()

// You can of course use the hook as you always would
function Component() {
  const paw = useDogStore((state) => state.paw)
  ...
```

### Using subscribe with selector

If you need to subscribe with a selector,
`subscribeWithSelector` middleware will help.

With this middleware `subscribe` accepts an additional signature:

```ts
subscribe(selector, callback, options?: { equalityFn, fireImmediately }): Unsubscribe
```

```js
import { subscribeWithSelector } from 'zustand/middleware'
const useDogStore = create(
  subscribeWithSelector(() => ({ paw: true, snout: true, fur: true })),
)

// Listening to selected changes, in this case when "paw" changes
const unsub2 = useDogStore.subscribe((state) => state.paw, console.log)
// Subscribe also exposes the previous value
const unsub3 = useDogStore.subscribe(
  (state) => state.paw,
  (paw, previousPaw) => console.log(paw, previousPaw),
)
// Subscribe also supports an optional equality function
const unsub4 = useDogStore.subscribe(
  (state) => [state.paw, state.fur],
  console.log,
  { equalityFn: shallow },
)
// Subscribe and fire immediately
const unsub5 = useDogStore.subscribe((state) => state.paw, console.log, {
  fireImmediately: true,
})
```

## Using zustand without React

Zustand core can be imported and used without the React dependency. The only difference is that the create function does not return a hook, but the API utilities.

```jsx
import { createStore } from 'zustand/vanilla'

const store = createStore((set) => ...)
const { getState, setState, subscribe, getInitialState } = store

export default store
```

You can use a vanilla store with `useStore` hook available since v4.

```jsx
import { useStore } from 'zustand'
import { vanillaStore } from './vanillaStore'

const useBoundStore = (selector) => useStore(vanillaStore, selector)
```

:warning: Note that middlewares that modify `set` or `get` are not applied to `getState` and `setState`.

## Transient updates (for often occurring state-changes)

The subscribe function allows components to bind to a state-portion without forcing re-render on changes. Best combine it with useEffect for automatic unsubscribe on unmount. This can make a [drastic](https://codesandbox.io/s/peaceful-johnson-txtws) performance impact when you are allowed to mutate the view directly.

```jsx
const useScratchStore = create((set) => ({ scratches: 0, ... }))

const Component = () => {
  // Fetch initial state
  const scratchRef = useRef(useScratchStore.getState().scratches)
  // Connect to the store on mount, disconnect on unmount, catch state-changes in a reference
  useEffect(() => useScratchStore.subscribe(
    state => (scratchRef.current = state.scratches)
  ), [])
  ...
```

## Sick of reducers and changing nested states? Use Immer!

Reducing nested structures is tiresome. Have you tried [immer](https://github.com/mweststrate/immer)?

```jsx
import { produce } from 'immer'

const useLushStore = create((set) => ({
  lush: { forest: { contains: { a: 'bear' } } },
  clearForest: () =>
    set(
      produce((state) => {
        state.lush.forest.contains = null
      }),
    ),
}))

const clearForest = useLushStore((state) => state.clearForest)
clearForest()
```

[Alternatively, there are some other solutions.](./docs/guides/updating-state.md#with-immer)

## Persist middleware

You can persist your store's data using any kind of storage.

```jsx
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

const useFishStore = create(
  persist(
    (set, get) => ({
      fishes: 0,
      addAFish: () => set({ fishes: get().fishes + 1 }),
    }),
    {
      name: 'food-storage', // name of the item in the storage (must be unique)
      storage: createJSONStorage(() => sessionStorage), // (optional) by default, 'localStorage' is used
    },
  ),
)
```

[See the full documentation for this middleware.](./docs/integrations/persisting-store-data.md)

## Immer middleware

Immer is available as middleware too.

```jsx
import { create } from 'zustand'
import { immer } from 'zustand/middleware/immer'

const useBeeStore = create(
  immer((set) => ({
    bees: 0,
    addBees: (by) =>
      set((state) => {
        state.bees += by
      }),
  })),
)
```

## Can't live without redux-like reducers and action types?

```jsx
const types = { increase: 'INCREASE', decrease: 'DECREASE' }

const reducer = (state, { type, by = 1 }) => {
  switch (type) {
    case types.increase:
      return { grumpiness: state.grumpiness + by }
    case types.decrease:
      return { grumpiness: state.grumpiness - by }
  }
}

const useGrumpyStore = create((set) => ({
  grumpiness: 0,
  dispatch: (args) => set((state) => reducer(state, args)),
}))

const dispatch = useGrumpyStore((state) => state.dispatch)
dispatch({ type: types.increase, by: 2 })
```

Or, just use our redux-middleware. It wires up your main-reducer, sets the initial state, and adds a dispatch function to the state itself and the vanilla API.

```jsx
import { redux } from 'zustand/middleware'

const useGrumpyStore = create(redux(reducer, initialState))
```

## Redux devtools

```jsx
import { devtools } from 'zustand/middleware'

// Usage with a plain action store, it will log actions as "setState"
const usePlainStore = create(devtools((set) => ...))
// Usage with a redux store, it will log full action types
const useReduxStore = create(devtools(redux(reducer, initialState)))
```

One redux devtools connection for multiple stores

```jsx
import { devtools } from 'zustand/middleware'

// Usage with a plain action store, it will log actions as "setState"
const usePlainStore1 = create(devtools((set) => ..., { name, store: storeName1 }))
const usePlainStore2 = create(devtools((set) => ..., { name, store: storeName2 }))
// Usage with a redux store, it will log full action types
const useReduxStore = create(devtools(redux(reducer, initialState)), , { name, store: storeName3 })
const useReduxStore = create(devtools(redux(reducer, initialState)), , { name, store: storeName4 })
```

Assigning different connection names will separate stores in redux devtools. This also helps group different stores into separate redux devtools connections.

devtools takes the store function as its first argument, optionally you can name the store or configure [serialize](https://github.com/zalmoxisus/redux-devtools-extension/blob/master/docs/API/Arguments.md#serialize) options with a second argument.

Name store: `devtools(..., {name: "MyStore"})`, which will create a separate instance named "MyStore" in the devtools.

Serialize options: `devtools(..., { serialize: { options: true } })`.

#### Logging Actions

devtools will only log actions from each separated store unlike in a typical _combined reducers_ redux store. See an approach to combining stores https://github.com/pmndrs/zustand/issues/163

You can log a specific action type for each `set` function by passing a third parameter:

```jsx
const useBearStore = create(devtools((set) => ({
  ...
  eatFish: () => set(
    (prev) => ({ fishes: prev.fishes > 1 ? prev.fishes - 1 : 0 }),
    undefined,
    'bear/eatFish'
  ),
  ...
```

You can also log the action's type along with its payload:

```jsx
  ...
  addFishes: (count) => set(
    (prev) => ({ fishes: prev.fishes + count }),
    undefined,
    { type: 'bear/addFishes', count, }
  ),
  ...
```

If an action type is not provided, it is defaulted to "anonymous". You can customize this default value by providing an `anonymousActionType` parameter:

```jsx
devtools(..., { anonymousActionType: 'unknown', ... })
```

If you wish to disable devtools (on production for instance). You can customize this setting by providing the `enabled` parameter:

```jsx
devtools(..., { enabled: false, ... })
```

## React context

The store created with `create` doesn't require context providers. In some cases, you may want to use contexts for dependency injection or if you want to initialize your store with props from a component. Because the normal store is a hook, passing it as a normal context value may violate the rules of hooks.

The recommended method available since v4 is to use the vanilla store.

```jsx
import { createContext, useContext } from 'react'
import { createStore, useStore } from 'zustand'

const store = createStore(...) // vanilla store without hooks

const StoreContext = createContext()

const App = () => (
  <StoreContext.Provider value={store}>
    ...
  </StoreContext.Provider>
)

const Component = () => {
  const store = useContext(StoreContext)
  const slice = useStore(store, selector)
  ...
```

## TypeScript Usage

Basic typescript usage doesn't require anything special except for writing `create<State>()(...)` instead of `create(...)`...

```ts
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import type {} from '@redux-devtools/extension' // required for devtools typing

interface BearState {
  bears: number
  increase: (by: number) => void
}

const useBearStore = create<BearState>()(
  devtools(
    persist(
      (set) => ({
        bears: 0,
        increase: (by) => set((state) => ({ bears: state.bears + by })),
      }),
      {
        name: 'bear-storage',
      },
    ),
  ),
)
```

A more complete TypeScript guide is [here](docs/guides/typescript.md).

## Best practices

- You may wonder how to organize your code for better maintenance: [Splitting the store into separate slices](./docs/guides/slices-pattern.md).
- Recommended usage for this unopinionated library: [Flux inspired practice](./docs/guides/flux-inspired-practice.md).
- [Calling actions outside a React event handler in pre-React 18](./docs/guides/event-handler-in-pre-react-18.md).
- [Testing](./docs/guides/testing.md)
- For more, have a look [in the docs folder](./docs/)

## Third-Party Libraries

Some users may want to extend Zustand's feature set which can be done using third-party libraries made by the community. For information regarding third-party libraries with Zustand, visit [the doc](./docs/integrations/third-party-libraries.md).

## Comparison with other libraries

- [Difference between zustand and other state management libraries for React](https://docs.pmnd.rs/zustand/getting-started/comparison)
