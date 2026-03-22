// Last module patch version validated against: 3.0.1

/** helper function, maps over a union type */
type MapUnion<K extends keyof T, T> = K extends any ? T[K] : never;

export namespace Dispatch {
    /** given a string like `a.1 b c.2`, it returns a union like `'a' | 'b' | 'c'` */
    type ExtractEventNames<Input extends string> = Input extends "" ? never
        : Input extends `${infer A} ${infer B}` // multiple events
            ? ExtractEventNames<A> | ExtractEventNames<B>
        : Input extends `${infer A}.${string}` // single event with a name
            ? A
        : Input; // single event with no name

    /**
     * defines all the events that can be emitted.
     * Each property is the arguments for that event.
     */
    interface GenericEventMap {
        [eventName: string]: any[];
    }
}

export interface Dispatch<This extends object, EventMap extends Dispatch.GenericEventMap = Dispatch.GenericEventMap> {
    /**
     * Like `function.apply`, invokes each registered callback for the specified type,
     * passing the callback the specified arguments, with `that` as the `this` context.
     *
     * @param type A specified event type.
     * @param that The `this` context for the callback.
     * @param args Additional arguments to be passed to the callback.
     * @throws "unknown type" on unknown event type.
     */
    apply<U extends keyof EventMap>(type: U, that?: This, args?: EventMap[U]): void;

    /**
     * Like `function.call`, invokes each registered callback for the specified type,
     * passing the callback the specified arguments, with `that` as the `this` context.
     * See dispatch.apply for more information.
     *
     * @param type A specified event type.
     * @param that The `this` context for the callback.
     * @param args Additional arguments to be passed to the callback.
     * @throws "unknown type" on unknown event type.
     */
    call<U extends keyof EventMap>(type: U, that?: This, ...args: EventMap[U]): void;

    /**
     * Returns a copy of this dispatch object.
     * Changes to this dispatch do not affect the returned copy and vice versa.
     */
    copy(): Dispatch<This, EventMap>;

    /**
     * Returns the callback for the specified typenames, if any.
     * If multiple typenames are specified, the first matching callback is returned.
     */
    on<Source extends string>(
        typenames: Source,
    ): Dispatch.ExtractEventNames<Source> extends keyof EventMap
        ? ((this: This, ...args: MapUnion<Dispatch.ExtractEventNames<Source>, EventMap>) => void) | undefined
        : never;

    /**
     * Adds or removes the callback for the specified typenames.
     * If a callback function is specified, it is registered for the specified (fully-qualified) typenames.
     * If a callback was already registered for the given typenames, the existing callback is removed before the new callback is added.
     * The specified typenames is a string, such as start or end.foo.
     * The type may be optionally followed by a period (.) and a name; the optional name allows multiple callbacks to be registered to receive events of the same type, such as start.foo and start.bar.
     * To specify multiple typenames, separate typenames with spaces, such as start end or start.foo start.bar.
     * To remove all callbacks for a given name foo, say dispatch.on(".foo", null).
     */
    on<Source extends string>(
        typenames: Source,
        callback: Dispatch.ExtractEventNames<Source> extends keyof EventMap
            ? ((this: This, ...args: MapUnion<Dispatch.ExtractEventNames<Source>, EventMap>) => void) | null
            : never,
    ): this;
}

/**
 * Creates a new dispatch for the specified event types. Each type is a string, such as "start" or "end".
 *
 * @param types The event types.
 * @throws "illegal type" on empty string or duplicated event types.
 */
/* eslint-disable @definitelytyped/no-unnecessary-generics */
export function dispatch<
    This extends object,
    EventMap extends Record<EventNames, any[]>,
    const EventNames extends keyof any = keyof EventMap,
>(
    ...types: EventNames[]
): Dispatch<This, EventMap>;

export {};
