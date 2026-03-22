<div align="left">
  <h1 align="center">REACT FOCUS LOCK</h1>
  <img src="./assets/ackbar.png" alt="it-is-a-trap" width="200" height="200" align="right">
  
  - browser friendly focus lock<br/>
  - matching all your use cases<br/>
  - trusted by best UI frameworks<br/>
  - the thing Admiral Ackbar was talking about<br/>
  <br/>

[![CircleCI status](https://img.shields.io/circleci/project/github/theKashey/react-focus-lock/master.svg?style=flat-square)](https://circleci.com/gh/theKashey/react-focus-lock/tree/master)
[![npm](https://img.shields.io/npm/v/react-focus-lock.svg)](https://www.npmjs.com/package/react-focus-lock)
[![bundle size](https://badgen.net/bundlephobia/minzip/react-focus-lock)](https://bundlephobia.com/result?p=react-focus-lock)
[![downloads](https://badgen.net/npm/dm/react-focus-lock)](https://www.npmtrends.com/react-focus-lock)
  <hr/>  
</div>

It is a trap! We got your focus and will not let him out!

- Modal dialogs. You can not leave it with "Tab", ie do a "tab-out".
- Focused tasks. It will aways brings you back, as you can "lock" user inside a component.
- Any any other case, when you have to lock user _intention_ and _focus_, if that's what `a11y` is asking for.
   - Including programatic focus management and smart return focus 

### Trusted
Trusted by 
[Atlassian AtlasKit](https://atlaskit.atlassian.com), 
[ReachUI](https://ui.reach.tech/), 
[SmoothUI](https://smooth-ui.smooth-code.com/), 
[Storybook](https://storybook.js.org/)
and we will do our best to earn your trust too!
 
# Features
 - no keyboard control, everything is done watching a __focus behavior__, not emulating it. Focus-Locks works for all cases including positive tab indexes.
 - React __Portals__ support. Even if some data is in outer space - it is [still in lock](https://github.com/theKashey/react-focus-lock/issues/19).
 - _Scattered_ locks, or focus lock groups - you can setup different isolated locks, and _tab_ from one to another.
 - Controllable isolation level.
 - variable size bundle. Uses _sidecar_ to trim UI part down to 1.5kb. 
 
> 💡 __focus__ locks is part of a bigger whole, consider __scroll lock__ and __text-to-speech__ lock
you have to use to really "lock" the user.
Try [react-focus-on](https://github.com/theKashey/react-focus-on) to archive everything above, assembled in the right order. 
 
# How to use
Just wrap something with focus lock, and focus will be `moved inside` on mount.
```js
 import FocusLock from 'react-focus-lock';

 const JailForAFocus = ({onClose}) => (
    <FocusLock>
      You can not leave this form
      <button onClick={onClose} />
    </FocusLock>
 );
```
Demo - https://codesandbox.io/s/5wmrwlvxv4.

# API
> FocusLock would work perfectly even with no props set.

 FocusLock has few props to tune behavior, all props are optional:
  - `disabled`, to disable(enable) behavior without altering the tree.
  - `className`, to set the `className` of the internal wrapper.
  - `returnFocus`, to return focus into initial position on unmount
> By default `returnFocus` is disabled, so FocusLock __will not__ restore original focus on deactivation.
> This was done mostly to avoid breaking changes. We __strong recommend enabling it__, to provide a better user experience.
    
  This is expected behavior for Modals, but it is better to implement it by your self. See [unmounting and focus management](https://github.com/theKashey/react-focus-lock#unmounting-and-focus-management) for details
  - `persistentFocus=false`, requires any element to be focused. This also disables text selections inside, and __outside__ focus lock.
  - `autoFocus=true`, enables or disables focusing into on Lock activation. If disabled Lock will blur an active focus.
  - `noFocusGuards=false` disabled _focus guards_ - virtual inputs which secure tab index.
  - `group='''` named focus group for focus scattering aka [combined lock targets](https://github.com/theKashey/vue-focus-lock/issues/2)
  - `shards=[]` an array of `ref` pointing to the nodes, which focus lock should consider and a part of it. This is another way focus scattering.  
  - `whiteList=fn` you could _whitelist_ locations FocusLock should carry about. Everything outside it will ignore. For example - any modals.
  - `as='div'` if you need to change internal `div` element, to any other. Use ref forwarding to give FocusLock the node to work with.
  - `lockProps={}` to pass any extra props (except className) to the internal wrapper.
  - `hasPositiveIndices=false` to support a focus lock behavior when any elements tabIndex greater than 0.
  - `crossFrame=true` enables aggressive focus capturing within iframes

## Programmatic control
Focus lock exposes a few methods to control focus programmatically.
### Imperative API
- `useFocusInside(nodeRef)` - to move focus inside the given node
- `useFocusScope():{autofocus, focusNext, focusPrev}` - provides API to manage focus within the current lock
- `useFocusState()` - manages focus state of a given node
- `useFocusController(nodeRef)` - low level version of `useFocusScope` working without FocusLock 

### Declarative API
- `<AutoFocusInside/>` - causes autofocus to look inside the component
- `<MoveFocusInside/>` - wrapper around `useFocusInside`, forcibly moves focus inside on mount
- `<FreeFocusInside/>` - hides internals from FocusLock allowing unmanaged focus

#### Indirect API
Focus-lock behavior can be controlled via data-attributes. Declarative API above is working by setting them for you.
See [corresponding section in focus-lock](https://github.com/theKashey/focus-lock#declarative-control) for details



### Focusing in OSX (Safari/Firefox) is strange!
By default `tabbing` in OSX `sees` only controls, but not links or anything else `tabbable`. This is system settings, and Safari/Firefox obey.
Press Option+Tab in Safari to loop across all tabbables, or change the Safari settings. There is no way to _fix_ Firefox, unless change system settings (Control+F7). See [this issue](https://github.com/theKashey/react-focus-lock/issues/24) for more information.

## Set up
### Requirements
- version 1x is React 15/16 compatible
- version 2+ requires React 16.8+ (hooks)
### Import
`react-focus-lock` exposed __3 entry points__: for the classical usage, and a _sidecar_ one.
#### Default usage
- 4kb, `import FocusLock from 'react-focus-lock` would give you component you are looking for.

#### Separated usage
Meanwhile - you dont need any focus related logic until it's needed.
Thus - you may defer that logic till Lock activation and move all related code to a _sidecar_.

- UI, __1.5kb__, `import FocusLockUI from 'react-focus-lock/UI` - a DOM part of a lock.
- Sidecar, 3.5kb, `import Sidecar from 'react-focus-lock/sidecar` - which is the real focus lock.

```js
import FocusLockUI from "react-focus-lock/UI";
import {sidecar} from "use-sidecar";

// prefetch sidecar. data would be loaded, but js would not be executed
const FocusLockSidecar = sidecar(  
  () => import(/* webpackPrefetch: true */ "react-focus-lock/sidecar")
);

<FocusLockUI
    disabled={this.state.disabled}
    sideCar={FocusLockSidecar}
>
 {content}
</FocusLockUI> 
```
That would split FocusLock into two pieces, reducing app size and improving the first load.
The cost of focus-lock is just 1.5kb!

> Saved 3.5kb?! 🤷‍♂️ 3.5kb here and 3.5kb here, and your 20mb bundle is ready.

# Autofocus
 Use when you cannot use the native `autoFocus` prop - because you only want to autofocus once the Trap has been activated
      
 - prop `data-autofocus` on the element.
 - prop `data-autofocus-inside` on the element to focus on something inside.
 - `AutoFocusInside` component, as named export of this library.
```js
 import FocusLock, { AutoFocusInside } from 'react-focus-lock';
 
 <FocusLock>
   <button>Click</button>
   <AutoFocusInside>
    <button>will be focused</button>
   </AutoFocusInside>
 </FocusLock>
 // is the same as
 
 <FocusLock>
   <button>Click</button>
    <button data-autofocus>will be focused</button>
 </FocusLock>
 ```
 
 If there is more than one auto-focusable target - the first will be selected.
 If it is a part of radio group, and __rest of radio group element are also autofocusable__(just put them into AutoFocusInside) - 
 checked one fill be selected.
 
 `AutoFocusInside` will work only on Lock activation, and does nothing, then used outside of the lock.
 You can use `MoveFocusInside` to move focus inside with or without lock.
 
```js
 import { MoveFocusInside } from 'react-focus-lock';
    
 <MoveFocusInside>
  <button>will be focused</button>
 </MoveFocusInside>
 ```
 
# Portals
Use focus scattering to handle portals

- using `groups`. Just create a few locks (only one could be active) with a same group name
```js
const PortaledElement = () => (
   <FocusLock group="group42" disabled={true}>
     // "discoverable" portaled content
   </FocusLock>  
);

<FocusLock group="group42">
  // main content
</FocusLock>
```
- using `shards`. Just pass all the pieces to the "shards" prop. 
```js
const PortaledElement = () => (
   <div ref={ref}>
     // "discoverable" portaled content
   </div>  
);

<FocusLock shards={[ref]}>
  // main content
</FocusLock>
```
- without anything. FocusLock will not prevent focusing portaled element, but will not include them in to tab order 
```js
const PortaledElement = () => (
   <div>
     // NON-"discoverable" portaled content
   </div>  
);

<FocusLock shards={[ref]}>
  // main content
  <PortaledElement />
</FocusLock>
```

### Using your own `Components`
You may use `as` prop to change _what_ Focus-Lock will render around `children`.
```js
<FocusLock as="section">
    <button>Click</button>
    <button data-autofocus>will be focused</button>
 </FocusLock>
 
 <FocusLock as={AnotherComponent} lockProps={{anyAnotherComponentProp: 4}}>
    <button>Click</button>
    <span>Hello there!</span>
 </FocusLock>
``` 

### Programmatic Control
Let's take a look at the `Rowing Focus` as an example. 
```tsx
// Will set tabindex to -1 when is not focused
const FocusTrackingButton = ({ children }) => {
    const { active, onFocus, ref } = useFocusState();
    return (
        <button tabIndex={active ? undefined : -1} onFocus={onFocus} ref={ref}>
            {children}
        </button>
    );
};
const RowingFocusInternalTrap = () => {
    const { autoFocus, focusNext, focusPrev } = useFocusScope();
    // use useFocusController(divRef) if there is no FocusLock around

    useEffect(() => {
        autoFocus();
    }, []);

    const onKey = (event) => {
        if (event.key === 'ArrowDown') {
            focusNext({ onlyTabbable: false });
        }
        if (event.key === 'ArrowUp') {
            focusPrev({ onlyTabbable: false });
        }
    };
    
    return (
        <div
            onKeyDown={onKey}
            // ref={divRef} for  useFocusController
        >
            <FocusButton>Button1</FocusButton>
            <FocusButton>Button2</FocusButton>
            <FocusButton>Button3</FocusButton>
            <FocusButton>Button4</FocusButton>
        </div>
    );
};

// FocusLock, even disabled one
const RowingFocusTrap = () => (
    <FocusLock disabled>
        <RowingFocusInternalTrap />
    </FocusLock>
);
```

### Guarding
As you may know - FocusLock is adding `Focus Guards` before and after lock to remove some side effects, like page scrolling.
But `shards` will not have such guards, and it might be not so cool to use them - for example if no `tabbable` would be
defined after shard - you will tab to the browser chrome.

You may wrap shard  with `InFocusGuard` or just drop `InFocusGuard` here and there - that would solve the problem.
```js
import {InFocusGuard} from 'react-focus-lock';

// wrap with
<InFocusGuard>
  <button />
</InFocusGuard>

// place before and after
<InFocusGuard />
<button />
<InFocusGuard />
```
InFocusGuards would be active(tabbable) only when tabble, it protecting, is focused.

#### Removing Tailing Guard
If only your modal is the last tabble element on the body - you might remove the Tailing Guard,
to allow user _tab_ into address bar.
```js
<InFocusGuard/>
<button />  
// there is no "tailing" guard :)
```
 
# Unmounting and focus management
 - In case FocusLock has `returnFocus` enabled, and it's going to be unmounted - focus will be returned after zero-timeout.
 - In case `returnFocus` is set to `false`, and you are going to control focus change on your own - keep in mind
 >> React will first call Parent.componentWillUnmount, and next Child.componentWillUnmount
 
 This means - Trap will be still active by the time you _may_ want move(return) focus on componentWillUnmount. Please deffer this action with a zero-timeout.
 
 Similarly, if you are using the `disabled` prop to control FocusLock, you will need a zero-timeout to correctly restore focus.
 
```
<FocusLock
  disabled={isFocusLockDisabled}
  onDeactivation={() => {
    // Without the zero-timeout, focus will likely remain on the button/control
    // you used to set isFocusLockDisabled = true
    window.setTimeout(() => myRef.current.focus(), 0);
  }
>
```

## Return focus to another node
In some cases the original node that was focused before the lock was activated is not the desired node to return focus to.
Some times this node might not exists at all.

- first of all, FocusLock need a moment to record this node, please do not hide it onClick, but hide onBlur (Dropdown, looking at you)
- second, you may specify a callback as `returnFocus`, letting you decide where to return focus to.
```tsx
<FocusLock
    returnFocus={(suggestedNode) => {
        // somehow activeElement should not be changed
        if(document.activeElement.hasAttributes('main-content')) {
            // opt out from default behavior
            return false;
        }
        if (someCondition(suggestedNode)) {
            // proceed with the suggested node
            return true;
        } 
        // handle return focus manually
        document.getElementById('the-button').focus();
        // opt out from default behavior
        return false;
    }}
/>
````

## Return focus with no scroll
> read more at the [issue #83](https://github.com/theKashey/react-focus-lock/issues/83) or
[mdn article](https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/focus).

To return focus, but without _jumpy_ page scroll returning a focus you might specify a focus option
```js
<FocusLock
  returnFocus={{ preventScroll: false }} // working not in all browsers
>   
```  
Not supported by Edge and Safari.

## Focus fighting
Two different _focus-lock-managers_ or even different version of a single one, being active
simultaneously will FIGHT for the focus. This usually totally breaks user experience.

__React-Focus-Lock will automatically surrender__, letting another library to take the lead.

### Resolving focus fighting
You may wrap some render branch with `FreeFocusInside`, and react-focus-lock __will ignore__
any focus inside marked node. So in case focus moves to _uncontrolled location_ focus-lock will not trigger letting another library to act without interference in that another location.

```js
import { FreeFocusInside } from 'react-focus-lock';

<FreeFocusInside>
 <div id="portal-for-modals">
   in this div i am going to portal my modals, dont fight with them please
 </div>
</FreeFocusInside>
```
Another option for hybrid applications is to `whiteList` area where Focus-Lock should act, automatically allowing other managers in other areas.
The code below will scope Focus-Lock on inside the (react)`root` element, so anything jQuery can add to the body will be ignored.
```js
<FocusLock whiteList={node => document.getElementById('root').contains(node)}>
 ...
</FocusLock>
```

### Two Focus-Locks
React-Focus-Lock is expected to be a singleton.
__Use webpack or yarn resolution for force only one version of react-focus-lock used.

> webpack.conf
```js
 resolve: {    
    alias: {
      'react-focus-lock': path.resolve(path.join(__dirname, './node_modules/react-focus-lock'))
 ...
```

# WHY?
From [MDN Article about accessible dialogs](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/ARIA_Techniques/Using_the_dialog_role):
- The dialog must be properly labeled
- Keyboard __focus must be managed__ correctly

This one is about managing the focus.

I've got a good [article about focus management, dialogs and  WAI-ARIA](https://medium.com/@antonkorzunov/its-a-focus-trap-699a04d66fb5).

# Not only for React
Uses [focus-lock](https://github.com/theKashey/focus-lock/) under the hood. It does also provide support for Vue.js and Vanilla DOM solutions

# More
To create a "right" modal dialog you have to:
- manage a focus. Use this library
- block document scroll. Use [react-remove-scroll](https://github.com/theKashey/react-remove-scroll).
- hide everything else from screen readers. Use [aria-hidden](https://github.com/theKashey/aria-hidden)

You may use [react-focus-on](https://github.com/theKashey/react-focus-on) to achieve everything above, assembled in the right order.

# Licence
 MIT
 
 
