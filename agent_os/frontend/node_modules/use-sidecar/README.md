<div align="center">
  <h1>🏎 side car</h1>
  <br/>
   Alternative way to code splitting
  <br/>
  
  <a href="https://www.npmjs.com/package/use-sidecar">
    <img src="https://img.shields.io/npm/v/use-sidecar.svg?style=flat-square" />
  </a>
    
  <a href="https://travis-ci.org/theKashey/use-sidecar">
   <img src="https://img.shields.io/travis/theKashey/use-sidecar.svg?style=flat-square" alt="Build status">
  </a> 

  <a href="https://www.npmjs.com/package/use-sidecar">
   <img src="https://img.shields.io/npm/dm/use-sidecar.svg" alt="npm downloads">
  </a> 

  <a href="https://bundlephobia.com/result?p=use-sidecar">
   <img src="https://img.shields.io/bundlephobia/minzip/use-sidecar.svg" alt="bundle size">
  </a>   
  <br/>
</div>

UI/Effects code splitting pattern
 - [read the original article](https://dev.to/thekashey/sidecar-for-a-code-splitting-1o8g) to understand concepts behind.
 - [read how Google](https://medium.com/@cramforce/designing-very-large-javascript-applications-6e013a3291a3) split view and logic.
 - [watch how Facebook](https://developers.facebook.com/videos/2019/building-the-new-facebookcom-with-react-graphql-and-relay/) defers "interactivity" effects. 

## Terminology: 
- `sidecar` - non UI component, which may carry effects for a paired UI component.
- `UI` - UI component, which interactivity is moved to a `sidecar`.

`UI` is a _view_, `sidecar` is the _logic_ for it. Like Batman(UI) and his sidekick Robin(effects). 

## Concept
- a `package` exposes __3 entry points__ using a [nested `package.json` format](https://github.com/theKashey/multiple-entry-points-example):
  - default aka `combination`, and lets hope tree shaking will save you
  - `UI`, with only UI part
  - `sidecar`, with all the logic
  - > `UI` + `sidecar` === `combination`. The size of `UI+sidecar` might a bit bigger than size of their `combination`.
  Use [size-limit](https://github.com/ai/size-limit) to control their size independently. 
  

- package uses a `medium` to talk with own sidecar, breaking explicit dependency.
 
- if package depends on another _sidecar_ package:
  - it shall export dependency side car among own sidecar.
  - package imports own sidecar via `medium`, thus able to export multiple sidecars via one export. 

- final consumer uses `sidecar` or `useSidecar` to combine pieces together.  

## Rules
- `UI` components might use/import any other `UI` components
- `sidecar` could use/import any other `sidecar`

That would form two different code branches, you may load separately - UI first, and effect sidecar later.
That also leads to a obvious consequence - __one sidecar may export all sidecars__.
- to decouple `sidecars` from module exports, and be able to pick "the right" one at any point
you have to use `exportSidecar(medium, component)` to export it, and use the same `medium` to import it back.
- this limitation is for __libraries only__, as long as in the usercode you might 
dynamically import whatever and whenever you want. 

- `useMedium` is always async - action would be executed in a next tick, or on the logic load.
- `sidecar` is always async - is does not matter have you loaded logic or not - component would be 
rendered at least in the next tick.

> except `medium.read`, which synchronously read the data from a medium, 
and `medium.assingSyncMedium` which changes `useMedium` to be sync. 

## SSR and usage tracking
Sidecar pattern is clear:
- you dont need to use/render any `sidecars` on server.
- you dont have to load `sidecars` prior main render.

Thus - no usage tracking, and literally no SSR. It's just skipped.


# API

## createMedium()
- Type: Util. Creates shared effect medium for algebraic effect.
- Goal: To decouple modules from each other.
- Usage: `use` in UI side, and `assign` from side-car. All effects would be executed.
- Analog: WeakMap, React.__SECRET_DOM_DO_NOT_USE_OR_YOU_WILL_BE_FIRED
```js
const medium = createMedium(defaultValue);
const cancelCb = medium.useMedium(someData);

// like
useEffect(() => medium.useMedium(someData), []);

medium.assignMedium(someDataProcessor)

// createSidecarMedium is a helper for createMedium to create a "sidecar" symbol
const effectCar = createSidecarMedium();
```

> ! For consistence `useMedium` is async - sidecar load status should not affect function behavior,
thus effect would be always executed at least in the "next tick". You may alter
this behavior by using `medium.assingSyncMedium`.


## exportSidecar(medium, component)
- Type: HOC
- Goal: store `component` inside `medium` and return external wrapper
- Solving: decoupling module exports to support exporting multiple sidecars via a single entry point.
- Usage: use to export a `sidecar`
- Analog: WeakMap
```js
import {effectCar} from './medium';
import {EffectComponent} from './Effect';
// !!! - to prevent Effect from being imported
// `effectCar` medium __have__ to be defined in another file
// const effectCar = createSidecarMedium();
export default exportSidecar(effectCar, EffectComponent);
```

## sidecar(importer)
- Type: HOC
- Goal: React.lazy analog for code splitting, but does not require `Suspense`, might provide error failback.
- Usage: like React.lazy to load a side-car component.
- Analog: React.Lazy
```js
import {sidecar} from "use-sidecar";
const Sidecar =  sidecar(() => import('./sidecar'), <span>on fail</span>);

<>
 <Sidecar />
 <UI />
</> 
```
### Importing `exportedSidecar`
Would require additional prop to be set - ```<Sidecar sideCar={effectCar} />```

## useSidecar(importer)
- Type: hook, loads a `sideCar` using provided `importer` which shall follow React.lazy API
- Goal: to load a side car without displaying any "spinners".
- Usage: load side car for a component
- Analog: none
```js
import {useSidecar} from 'use-sidecar';

const [Car, error] = useSidecar(() => import('./sideCar'));
return (
  <>
    {Car ? <Car {...props} /> : null}
    <UIComponent {...props}>
  </>
); 
```
### Importing `exportedSideCar`
You have to specify __effect medium__ to read data from, as long as __export itself is empty__.
```js
import {useSidecar} from 'use-sidecar';

/* medium.js: */ export const effectCar = useMedium({});
/* sideCar.js: */export default exportSidecar(effectCar, EffectComponent);

const [Car, error] = useSidecar(() => import('./sideCar'), effectCar); 
return (
  <>
    {Car ? <Car {...props} /> : null}
    <UIComponent {...props}>
  </>
);
```

## renderCar(Component)
- Type: HOC, moves renderProp component to a side channel
- Goal: Provide render prop support, ie defer component loading keeping tree untouched.
- Usage: Provide `defaults` and use them until sidecar is loaded letting you code split (non visual) render-prop component
- Analog: - Analog: code split library like [react-imported-library](https://github.com/theKashey/react-imported-library) or [@loadable/lib](https://www.smooth-code.com/open-source/loadable-components/docs/library-splitting/).
```js
import {renderCar, sidecar} from "use-sidecar";
const RenderCar = renderCar(
  // will move side car to a side channel
  sidecar(() => import('react-powerplug').then(imports => imports.Value)),
  // default render props
  [{value: 0}]  
);

<RenderCar>
  {({value}) => <span>{value}</span>}
</RenderCar>
```

## setConfig(config)
```js
setConfig({
  onError, // sets default error handler
});
```

# Examples
## Deferred effect
Let's imagine - on element focus you have to do "something", for example focus anther element

#### Original code
```js
onFocus = event => {
  if (event.currentTarget === event.target) {
    document.querySelectorAll('button', event.currentTarget)
  }
}
```

#### Sidecar code

3. Use medium (yes, .3)
```js
// we are calling medium with an original event as an argument
const onFocus = event => focusMedium.useMedium(event);
```
2. Define reaction
```js
// in a sidecar

// we are setting handler for the effect medium
// effect is complicated - we are skipping event "bubbling", 
// and focusing some button inside a parent
focusMedium.assignMedium(event => {
  if (event.currentTarget === event.target) {
    document.querySelectorAll('button', event.currentTarget)
  }
});

```
1. Create medium
Having these constrains - we have to clone `event`, as long as React would eventually reuse SyntheticEvent, thus not
preserve `target` and `currentTarget`. 
```js
// 
const focusMedium = createMedium(null, event => ({...event}));
```
Now medium side effect is ok to be async

__Example__: [Effect for react-focus-lock](https://github.com/theKashey/react-focus-lock/blob/8c69c644ecfeed2ec9dc0dc4b5b30e896a366738/src/Lock.js#L48) - 1kb UI, 4kb sidecar

### Medium callback
Like a library level code splitting

#### Original code
```js
import {x, y} from './utils';

useEffect(() => {
  if (x()) {
    y()
  }
}, []);
```

#### Sidecar code

```js
// medium
const utilMedium = createMedium();

// utils
const x = () => { /* ... */};
const y = () => { /* ... */};

// medium will callback with exports exposed
utilMedium.assignMedium(cb => cb({
 x, y
}));


// UI
// not importing x and y from the module system, but would be given via callback
useEffect(() => {
  utilMedium.useMedium(({x,y}) => {
      if (x()) {
        y()
      }
  })
}, []);
```

- Hint: there is a easy way to type it
```js
const utilMedium = createMedium<(cb: typeof import('./utils')) => void>();
``` 

__Example__: [Callback API for react-focus-lock](https://github.com/theKashey/react-focus-lock/blob/8c69c644ecfeed2ec9dc0dc4b5b30e896a366738/src/MoveFocusInside.js#L12) 

### Split effects
Lets take an example from a Google - Calendar app, with view and logic separated.
To be honest - it's not easy to extract logic from application like calendar - usually it's tight coupled.

#### Original code
```js
const CalendarUI = () => { 
  const [date, setDate] = useState();
  const onButtonClick = useCallback(() => setDate(Date.now), []);
  
  return (
    <>
     <input type="date" onChange={setDate} value={date} />
     <input type="button" onClick={onButtonClick}>Set Today</button>
    </>
  )
}
```
#### Sidecar code

```js
const CalendarUI = () => {
  const [events, setEvents] = useState({});
  const [date, setDate] = useState();
  
  return (
    <>
     <Sidecar setDate={setDate} setEvents={setEvents}/>
     <UILayout {...events} date={date}/>
    </>
  )
}

const UILayout = ({onDateChange, onButtonClick, date}) => (
  <>
      <input type="date" onChange={onDateChange} value={date} />
      <input type="button" onClick={onButtonClick}>Set Today</button>
  </>
);

// in a sidecar
// we are providing callbacks back to UI
const Sidecar = ({setDate, setEvents}) => {
  useEffect(() => setEvents({
      onDateChange:setDate,
      onButtonClick: () => setDate(Date.now),
  }), []);
  
  return null;
}
```  

While in this example this looks a bit, you know, strange - there are 3 times more code
that in the original example - that would make a sense for a real Calendar, especially
if some helper library, like `moment`, has been used.

__Example__: [Effect for react-remove-scroll](https://github.com/theKashey/react-remove-scroll/blob/666472d5c77fb6c4e5beffdde87c53ae63ef42c5/src/SideEffect.tsx#L166) - 300b UI, 2kb sidecar

# Licence

MIT

