// Last module patch version validated against: 3.0.1

/**
 * Returns the current time as defined by performance.now if available, and Date.now if not.
 * The current time is updated at the start of a frame; it is thus consistent during the frame, and any timers scheduled during the same frame will be synchronized.
 * If this method is called outside of a frame, such as in response to a user event, the current time is calculated and then fixed until the next frame,
 * again ensuring consistent timing during event handling.
 */
export function now(): number;

export interface Timer {
    /**
     * Restart a timer with the specified callback and optional delay and time.
     * This is equivalent to stopping this timer and creating a new timer with the specified arguments,
     * although this timer retains the original invocation priority.
     *
     * @param callback A callback function to be invoked and passed in the apparent
     * elapsed time since the timer became active in milliseconds.
     * @param delay An optional numeric delay in milliseconds (default = 0) relative to time.
     * @param time An optional time in milliseconds relative to which the delay is calculated (default = now).
     */
    restart(callbackFn: (elapsed: number) => void, delay?: number, time?: number): void;

    /**
     * Stop the timer.
     */
    stop(): void;
}

/**
 * Schedules and returns a new timer, invoking the specified callback repeatedly until the timer is stopped.
 * The callback is passed the (apparent) elapsed time since the timer became active.
 *
 * @param callback A callback function to be invoked and passed in the apparent
 * elapsed time since the timer became active in milliseconds.
 * @param delay An optional numeric delay in milliseconds (default = 0) relative to time.
 * @param time An optional time in milliseconds relative to which the delay is calculated (default = now).
 */
export function timer(callback: (elapsed: number) => void, delay?: number, time?: number): Timer;

/**
 * Immediately invoke any eligible timer callbacks.
 */
export function timerFlush(): void;

/**
 * Schedules and returns a new timer, invoking the specified callback. The timer is stopped automatically
 * on its first callback. The callback is passed the (apparent) elapsed time since the timer became active.
 *
 * @param callback A callback function to be invoked and passed in the apparent
 * elapsed time since the timer became active in milliseconds.
 * @param delay An optional numeric delay in milliseconds (default = 0) relative to time.
 * @param time An optional time in milliseconds relative to which the delay is calculated (default = now).
 */
export function timeout(callback: (elapsed: number) => void, delay?: number, time?: number): Timer;

/**
 * Schedules and returns a new timer, invoking the specified callback repeatedly every 'delay' milliseconds
 * until the timer is stopped.
 * The callback is passed the (apparent) elapsed time since the timer became active.
 *
 * @param callback A callback function to be invoked and passed in the apparent
 * elapsed time since the timer became active in milliseconds.
 * @param delay An optional numeric delay in milliseconds between repeat invocations of the callback.
 * If not specified, the interval timer behaves like the regular timer.
 * @param time An optional time in milliseconds relative to which the initial delay is calculated (default = now).
 */
export function interval(callback: (elapsed: number) => void, delay?: number, time?: number): Timer;
