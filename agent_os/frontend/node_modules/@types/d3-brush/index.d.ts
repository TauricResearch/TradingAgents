// Last module patch version validated against: 3.0.0

import { Selection, TransitionLike, ValueFn } from "d3-selection";

/**
 * Type alias for a BrushSelection. For a two-dimensional brush, it must be defined as [[x0, y0], [x1, y1]],
 * where x0 is the minimum x-value, y0 is the minimum y-value, x1 is the maximum x-value, and y1 is the maximum y-value.
 * For an x-brush, it must be defined as [x0, x1]; for a y-brush, it must be defined as [y0, y1].
 */
export type BrushSelection = [[number, number], [number, number]] | [number, number];

/**
 * A D3 brush behavior
 *
 * The generic refers to the type of the datum for the group element on which brush behavior is defined.
 */
export interface BrushBehavior<Datum> {
    /**
     * Applies the brush to the specified group, which must be a selection of SVG G elements.
     * This function is typically not invoked directly, and is instead invoked via selection.call.
     *
     * For details see: {@link https://github.com/d3/d3-brush#_brush}
     *
     * @param group A D3 selection of SVG G elements.
     * @param args Optional arguments to be passed in.
     */
    (group: Selection<SVGGElement, Datum, any, any>, ...args: any[]): void;
    /**
     * Clear the active selection of the brush on the specified SVG G element(s) selection.
     *
     * @param group A selection or a transition of SVG G elements
     * @param selection The selection must be defined as an array of numbers, or null to clear the brush selection.
     * For a two-dimensional brush, it must be defined as [[x0, y0], [x1, y1]], where x0 is the minimum x-value, y0 is the minimum y-value, x1 is the maximum x-value, and y1 is the maximum y-value.
     * For an x-brush, it must be defined as [x0, x1]; for a y-brush, it must be defined as [y0, y1].
     * The selection may also be specified as a function which returns such an array;
     * if a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     * The returned array defines the brush selection for that element.
     * @param event
     */
    move(
        group: Selection<SVGGElement, Datum, any, any> | TransitionLike<SVGGElement, Datum>,
        selection: null | BrushSelection | ValueFn<SVGGElement, Datum, BrushSelection>,
        event?: Event,
    ): void;

    /**
     * Clear the active selection of the brush on the specified SVG G element(s) selection.
     *
     * @param group A D3 selection of SVG G elements.
     * @param event
     */
    clear(group: Selection<SVGGElement, Datum, any, any>, event?: Event): void;

    /**
     * Returns the current extent accessor.
     */
    extent(): ValueFn<SVGGElement, Datum, [[number, number], [number, number]]>;
    /**
     * Set the brushable extent to the specified array of points and returns this brush.
     *
     * The brush extent determines the size of the invisible overlay and also constrains the brush selection;
     * the brush selection cannot go outside the brush extent.
     *
     * @param extent array of points [[x0, y0], [x1, y1]], where [x0, y0] is the top-left corner
     * and [x1, y1] is the bottom-right corner.
     */
    extent(extent: [[number, number], [number, number]]): this;
    /**
     * Set the brushable extent to the specified array of points returned by the accessor function
     * evaluated for each element in the selection/transition and returns this brush.
     *
     * The brush extent determines the size of the invisible overlay and also constrains the brush selection;
     * the brush selection cannot go outside the brush extent.
     *
     * @param extent An extent accessor function which is evaluated for each selected element,
     * in order, being passed the current datum (d), the current index (i), and the current group (nodes),
     * with this as the current DOM element. The function returns an array of points [[x0, y0], [x1, y1]],
     * where [x0, y0] is the top-left corner and [x1, y1] is the bottom-right corner.
     */
    extent(extent: ValueFn<SVGGElement, Datum, [[number, number], [number, number]]>): this;

    /**
     * Returns the current filter function.
     */
    filter(): (this: SVGGElement, event: any, d: Datum) => boolean;
    /**
     * Sets the filter to the specified filter function and returns the brush.
     *
     * If the filter returns falsey, the initiating event is ignored and no brush gesture is started.
     * Thus, the filter determines which input events are ignored. The default filter ignores mousedown events on secondary buttons,
     * since those buttons are typically intended for other purposes, such as the context menu.
     *
     * @param filterFn A filter function which is evaluated for each selected element,
     * in order, being passed the current event `event` and datum `d`, with the `this` context as the current DOM element.
     * The function returns a boolean value.
     */
    filter(filterFn: (this: SVGGElement, event: any, d: Datum) => boolean): this;

    /**
     * Returns the current touch support detector, which defaults to a function returning true,
     * if the "ontouchstart" event is supported on the current element.
     */
    touchable(): ValueFn<SVGGElement, Datum, boolean>;
    /**
     * Sets the touch support detector to the specified boolean value and returns the brush.
     *
     * Touch event listeners are only registered if the detector returns truthy for the corresponding element when the brush is applied.
     * The default detector works well for most browsers that are capable of touch input, but not all; Chrome’s mobile device emulator, for example,
     * fails detection.
     *
     * @param touchable A boolean value. true when touch event listeners should be applied to the corresponding element, otherwise false.
     */
    touchable(touchable: boolean): this;
    /**
     * Sets the touch support detector to the specified function and returns the drag behavior.
     *
     * Touch event listeners are only registered if the detector returns truthy for the corresponding element when the brush is applied.
     * The default detector works well for most browsers that are capable of touch input, but not all; Chrome’s mobile device emulator, for example,
     * fails detection.
     *
     * @param touchable A touch support detector function, which returns true when touch event listeners should be applied to the corresponding element.
     * The function is evaluated for each selected element to which the brush was applied, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element. The function returns a boolean value.
     */
    touchable(touchable: ValueFn<SVGGElement, Datum, boolean>): this;

    /**
     * Returns the current key modifiers flag.
     */
    keyModifiers(): boolean;
    /**
     * Sets the key modifiers flag and returns the brush.
     *
     * The key modifiers flag determines whether the brush listens to key events during brushing.
     * The default value is true.
     *
     * @param modifiers New value for key modifiers flag.
     */
    keyModifiers(modifiers: boolean): this;

    /**
     * Returns the current handle size, which defaults to six.
     */
    handleSize(): number;
    /**
     * Sets the size of the brush handles to the specified number and returns the brush.
     *
     * This method must be called before applying the brush to a selection;
     * changing the handle size does not affect brushes that were previously rendered.
     * The default size is 6.
     *
     * @param size Size of the handle.
     */
    handleSize(size: number): this;

    /**
     * Returns the first currently-assigned listener matching the specified typenames, if any.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "brush.foo"" and "brush.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (at the start of a brush gesture, such as on mousedown), brush (when the brush moves, such as on mousemove), or
     * end (at the end of a brush gesture, such as on mouseup.)
     */
    on(typenames: string): ((this: SVGGElement, event: any, d: Datum) => void) | undefined;
    /**
     * Removes the current event listeners for the specified typenames, if any.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "brush.foo"" and "brush.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (at the start of a brush gesture, such as on mousedown), brush (when the brush moves, such as on mousemove), or
     * end (at the end of a brush gesture, such as on mouseup.)
     * @param listener Use null to remove the listener.
     */
    on(typenames: string, listener: null): this;
    /**
     * Sets the event listener for the specified typenames and returns the brush.
     * If an event listener was already registered for the same type and name,
     * the existing listener is removed before the new listener is added.
     * When a specified event is dispatched, each listener will be invoked with the same context and arguments as selection.on listeners.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "brush.foo"" and "brush.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (at the start of a brush gesture, such as on mousedown), brush (when the brush moves, such as on mousemove), or
     * end (at the end of a brush gesture, such as on mouseup.)
     * @param listener An event listener function which is evaluated for each selected element,
     * in order, being passed the current event `event` and datum `d`, with the `this` context as the current DOM element.
     */
    on(typenames: string, listener: (this: SVGGElement, event: any, d: Datum) => void): this;
}

/**
 * Create a new two-dimensional brush.
 *
 * The generic "Datum" refers to the type of the data of the selected svg:g element to
 * which the returned BrushBehavior will be applied.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function brush<Datum>(): BrushBehavior<Datum>;
/**
 * Creates a new one-dimensional brush along the x-dimension.
 *
 * The generic "Datum" refers to the type of the data of the selected svg:g element to
 * which the returned BrushBehavior will be applied.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function brushX<Datum>(): BrushBehavior<Datum>;
/**
 * Creates a new one-dimensional brush along the y-dimension.
 *
 * The generic "Datum" refers to the type of the data of the selected svg:g element to
 * which the returned BrushBehavior will be applied.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function brushY<Datum>(): BrushBehavior<Datum>;

/**
 * Return the current brush selection for the specified node. Internally, an element’s brush state is stored as element.__brush;
 * however, you should use this method rather than accessing it directly. If the given node has no selection, returns null.
 * Otherwise, the selection is defined as an array of numbers.
 *
 * @param node The node for which the brush selection should be returned.
 */
export function brushSelection(node: SVGGElement): BrushSelection | null;

/**
 * D3 brush event
 *
 * The generic refers to the type of the datum for the group element on which brush was defined.
 */
export interface D3BrushEvent<Datum> {
    /**
     * The BrushBehavior associated with the event
     */
    target: BrushBehavior<Datum>;
    /**
     * The event type for the BrushEvent
     */
    type: "start" | "brush" | "end" | string; // Leave failsafe string type for cases like 'brush.foo'
    /**
     * The current brush selection associated with the event.
     * This is null when the selection is empty.
     */
    selection: BrushSelection | null;
    /**
     * The underlying input event, such as mousemove or touchmove.
     */
    sourceEvent: any;
    /**
     * The mode of the brush.
     */
    mode: "drag" | "space" | "handle" | "center";
}
