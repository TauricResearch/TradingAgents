# Framesync

A tiny frame scheduler for performantly batching reads, updates and renders.

Segregating actions that read and write to the DOM will avoid [layout thrashing](https://developers.google.com/web/fundamentals/performance/rendering/avoid-large-complex-layouts-and-layout-thrashing).

It's also a way of ensuring order of execution across a frame. For instance, [Framer Motion](https://github.com/framer/motion) batches animations on the `update` step, and renders on the `render` step, allowing independent animation of `transform` properties.

## Install

```bash
npm install framesync
```

## Usage

Framesync splits a frame into discrete `read`, `update`, `preRender`, `render` and `postRender` steps.

### Scheduling functions

Functions can be scheduled to different parts of the render loop with `sync`.

```javascript
import sync from 'framesync';
```

It provides four functions, one for scheduling a function to run on each part of the frame:

```javascript
sync.update(() => {});
```

### Frame data

Each function is provided data about the current frame:

```javascript
sync.update(({ delta, timestamp }) => {});
```

- `delta`: Time since last frame (in milliseconds)
- `timestamp`: Timestamp of the current frame.

This object is recycled across frames, so values should be destructured if intended to be used asynchronously.

### Keep alive

We can run a function as an ongoing process by passing `true` as the second parameter:

```javascript
let count = 0;

sync.update(() => count++, true);
```

This will keep the process running until it's actively cancelled.

### Run immediately

The third parameter, `immediate`, can be used to sync a function on the **current frame step**.

By default, Framesync will schedule functions to run the next time that frame step is fired:

```javascript
sync.update(({ timestamp }) => {
  // The following function will run on the subsequent frame:
  sync.update((frame) => frame.timestamp !== timestamp);
});
```

By setting `immediate` to `true`, we can add this at the end of the current step:

```javascript
sync.update(({ timestamp }) => {
  // The following function will run on the **current** frame:
  sync.update(
    (frame) => frame.timestamp === timestamp,
    false,
    true
  );
});
```

### Cancelling

Synced processes can be cancelled with the `cancelSync` function:

```javascript
import sync, { cancelSync } from 'framesync';

let count = 0;

const process = sync.render(() => {
  count++;
  if (count >= 10) cancelSync.render(process);
}, true);
```
