// Last module patch version validated against: 3.0.0

import { ZoomView } from "d3-interpolate";
import { Selection, TransitionLike, ValueFn } from "d3-selection";

// --------------------------------------------------------------------------
// Shared Type Definitions and Interfaces
// --------------------------------------------------------------------------

/**
 * ZoomedElementBaseType serves as an alias for the 'minimal' data type which can be selected
 * without 'd3-zoom' (and related code in 'd3-selection') trying to use properties internally which would otherwise not
 * be supported.
 */
export type ZoomedElementBaseType = Element;

/**
 * Minimal interface for a continuous scale.
 * This interface is used as a minimum contract for scale objects
 * that  can be passed into zoomTransform methods rescaleX and rescaleY
 */
export interface ZoomScale {
    domain(): number[] | Date[];
    domain(domain: Array<Date | number>): this;
    range(): number[];
    range(range: number[]): this;
    copy(): ZoomScale;
    invert(value: number): number | Date;
}

// --------------------------------------------------------------------------
// Zoom Behavior
// --------------------------------------------------------------------------

/**
 * A D3 Zoom Behavior
 *
 * The first generic refers to the type of reference element to which the zoom behavior is attached.
 * The second generic refers to the type of the datum of the reference element.
 */
export interface ZoomBehavior<ZoomRefElement extends ZoomedElementBaseType, Datum> extends Function {
    /**
     * Applies this zoom behavior to the specified selection, binding the necessary event listeners to
     * allow panning and zooming, and initializing the zoom transform on each selected element to the identity transform if not already defined. This function is typically not invoked directly,
     * and is instead invoked via selection.call.
     *
     * For details see: {@link https://github.com/d3/d3-zoom#_zoom}
     *
     * @param selection A D3 selection of elements.
     * @param args Optional arguments to be passed in.
     */
    (selection: Selection<ZoomRefElement, Datum, any, any>, ...args: any[]): void;
    /**
     * If selection is a selection, sets the current zoom transform of the selected elements to the specified transform, instantaneously emitting start, zoom and end events.
     * If selection is a transition, defines a “zoom” tween to the specified transform using d3.interpolateZoom, emitting a start event when the transition starts,
     * zoom events for each tick of the transition, and then an end event when the transition ends (or is interrupted).
     * The transition will attempt to minimize the visual movement around the specified point; if the point is not specified, it defaults to the center of the viewport extent.
     *
     * This function is typically not invoked directly, and is instead invoked via selection.call or transition.call.
     *
     * @param selection A selection or a transition.
     * @param transform A zoom transform or a function that returns a zoom transform.
     * If a function, it is invoked for each selected element, being passed the current event (event) and datum d, with the this context as the current DOM element.
     * @param point A two-element array [x, y] or a function that returns such an array.
     * If a function, it is invoked for each selected element, being passed the current event (event) and datum d, with the this context as the current DOM element.
     */
    transform(
        selection: Selection<ZoomRefElement, Datum, any, any> | TransitionLike<ZoomRefElement, Datum>,
        transform: ZoomTransform | ((this: ZoomRefElement, event: any, d: Datum) => ZoomTransform),
        point?: [number, number] | ((this: ZoomRefElement, event: any, d: Datum) => [number, number]),
    ): void;

    /**
     * If selection is a selection, translates the current zoom transform of the selected elements by x and y, such that the new tx1 = tx0 + kx and ty1 = ty0 + ky.
     * If selection is a transition, defines a “zoom” tween translating the current transform.
     * This method is a convenience method for zoom.transform.
     *
     * @param selection A selection or a transition.
     * @param x A number or a function that returns a number.
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     * @param y A number or a function that returns a number.
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     */
    translateBy(
        selection: Selection<ZoomRefElement, Datum, any, any> | TransitionLike<ZoomRefElement, Datum>,
        x: number | ValueFn<ZoomRefElement, Datum, number>,
        y: number | ValueFn<ZoomRefElement, Datum, number>,
    ): void;

    /**
     * If selection is a selection, translates the current zoom transform of the selected elements such that the given position ⟨x,y⟩ appears at given point p.
     * The new tx = px - kx and ty = py - ky. If p is not specified, it defaults to the center of the viewport extent.
     * If selection is a transition, defines a “zoom” tween translating the current transform. This method is a convenience method for zoom.transform.
     *
     * Translates the current zoom transform of the selected elements such that the specified position ⟨x,y⟩ appears at the center of the viewport extent.
     * The new tx = cx - kx and ty = cy - ky, where ⟨cx,cy⟩ is the center.
     *
     * x is provided as a constant for all elements.
     * y is provided as a constant for all elements.
     *
     * @param selection A selection or a transition.
     * @param x A number or a function that returns a number.
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     * @param y A number or a function that returns a number.
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     * @param p A two-element array [px,py] or a function
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     */
    translateTo(
        selection: Selection<ZoomRefElement, Datum, any, any> | TransitionLike<ZoomRefElement, Datum>,
        x: number | ValueFn<ZoomRefElement, Datum, number>,
        y: number | ValueFn<ZoomRefElement, Datum, number>,
        p?: [number, number] | ValueFn<ZoomRefElement, Datum, [number, number]>,
    ): void;

    /**
     * If selection is a selection, scales the current zoom transform of the selected elements by k, such that the new k₁ = k₀k.
     * The reference point p does move.
     * If p is not specified, it defaults to the center of the viewport extent.
     * If selection is a transition, defines a “zoom” tween translating the current transform.
     * This method is a convenience method for zoom.transform.
     *
     * @param selection A selection or a transition.
     * @param k Scale factor. A number or a function that returns a number.
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     * @param p A two-element array [px,py] or a function.
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     */
    scaleBy(
        selection: Selection<ZoomRefElement, Datum, any, any> | TransitionLike<ZoomRefElement, Datum>,
        k: number | ValueFn<ZoomRefElement, Datum, number>,
        p?: [number, number] | ValueFn<ZoomRefElement, Datum, [number, number]>,
    ): void;

    /**
     * If selection is a selection, scales the current zoom transform of the selected elements to k, such that the new k₁ = k.
     * The reference point p does move.
     * If p is not specified, it defaults to the center of the viewport extent.
     * If selection is a transition, defines a “zoom” tween translating the current transform.
     * This method is a convenience method for zoom.transform.
     *
     * @param selection: A selection or a transition.
     * @param k Scale factor. A number or a function that returns a number.
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     * @param p A two-element array [px,py] or a function.
     * If a function, it is invoked for each selected element, being passed the current datum d and index i, with the this context as the current DOM element.
     */
    scaleTo(
        selection: Selection<ZoomRefElement, Datum, any, any> | TransitionLike<ZoomRefElement, Datum>,
        k: number | ValueFn<ZoomRefElement, Datum, number>,
        p?: [number, number],
    ): void;

    /**
     * Returns the current constraint function.
     * The default implementation attempts to ensure that the viewport extent does not go outside the translate extent.
     */
    constrain(): (
        transform: ZoomTransform,
        extent: [[number, number], [number, number]],
        translateExtent: [[number, number], [number, number]],
    ) => ZoomTransform;
    /**
     * Sets the transform constraint function to the specified function and returns the zoom behavior.
     *
     * @param constraint A constraint function which returns a transform given the current transform, viewport extent and translate extent.
     * The default implementation attempts to ensure that the viewport extent does not go outside the translate extent.
     */
    constrain(
        constraint: (
            transform: ZoomTransform,
            extent: [[number, number], [number, number]],
            translateExtent: [[number, number], [number, number]],
        ) => ZoomTransform,
    ): this;

    /**
     * Returns the current filter function.
     */
    filter(): (this: ZoomRefElement, event: any, datum: Datum) => boolean;
    /**
     * Sets the filter to the specified filter function and returns the zoom behavior.
     * The filter function is invoked in the zoom initiating event handlers of each element to which the zoom behavior was applied.
     *
     * If the filter returns falsey, the initiating event is ignored and no zoom gesture is started.
     * Thus, the filter determines which input events are ignored. The default filter ignores mousedown events on secondary buttons,
     * since those buttons are typically intended for other purposes, such as the context menu.
     *
     * @param filter A filter function which is invoked in the zoom initiating event handlers of each element to which the zoom behavior was applied,
     * in order, being passed the current event (event) and datum d, with the this context as the current DOM element.
     * The function returns a boolean value.
     */
    filter(filter: (this: ZoomRefElement, event: any, datum: Datum) => boolean): this;

    /**
     * Returns the current touch support detector, which defaults to a function returning true,
     * if the "ontouchstart" event is supported on the current element.
     */
    touchable(): ValueFn<ZoomRefElement, Datum, boolean>;
    /**
     * Sets the touch support detector to the specified boolean value and returns the zoom behavior.
     *
     * Touch event listeners are only registered if the detector returns truthy for the corresponding element when the zoom behavior is applied.
     * The default detector works well for most browsers that are capable of touch input, but not all; Chrome’s mobile device emulator, for example,
     * fails detection.
     *
     * @param touchable A boolean value. true when touch event listeners should be applied to the corresponding element, otherwise false.
     */
    touchable(touchable: boolean): this;
    /**
     * Sets the touch support detector to the specified function and returns the zoom behavior.
     *
     * Touch event listeners are only registered if the detector returns truthy for the corresponding element when the zoom behavior is applied.
     * The default detector works well for most browsers that are capable of touch input, but not all; Chrome’s mobile device emulator, for example,
     * fails detection.
     *
     * @param touchable A touch support detector function, which returns true when touch event listeners should be applied to the corresponding element.
     * The function is evaluated for each selected element to which the zoom behavior was applied, in order, being passed the current datum (d),
     * the current index (i), and the current group (nodes), with this as the current DOM element. The function returns a boolean value.
     */
    touchable(touchable: ValueFn<ZoomRefElement, Datum, boolean>): this;

    /**
     * Returns the current wheelDelta function.
     */
    wheelDelta(): ValueFn<ZoomRefElement, Datum, number>;
    /**
     * Sets the wheel delta function to the specified function and returns the zoom behavior. The wheel delta function which is invoked in the wheel event handler
     * of each element to which the zoom behavior was applied.
     * The value Δ returned by the wheel delta function determines the amount of scaling applied in response to a WheelEvent.
     * The scale factor transform.k is multiplied by 2Δ; for example, a Δ of +1 doubles the scale factor, Δ of -1 halves the scale factor.
     *
     * @param delta Wheel delta function which is invoked in the wheel event handler of each element to which the zoom behavior was applied,
     * in order, being passed the wheel event that triggered the handler,
     * with this as the current DOM element. The function returns a numeric value.
     */
    wheelDelta(delta: ((event: WheelEvent) => number) | number): this;

    /**
     * Return the current extent accessor, which defaults to [[0, 0], [width, height]] where width is the client width of the element and height is its client height;
     * for SVG elements, the nearest ancestor SVG element’s width and height is used. In this case,
     * the owner SVG element must have defined width and height attributes rather than (for example) relying on CSS properties or the viewBox attribute;
     * SVG provides no programmatic method for retrieving the initial viewport size. Alternatively, consider using element.getBoundingClientRect.
     * (In Firefox, element.clientWidth and element.clientHeight is zero for SVG elements!)
     */
    extent(): (this: ZoomRefElement, datum: Datum) => [[number, number], [number, number]];
    /**
     * Set the viewport extent to the specified array of points [[x0, y0], [x1, y1]],
     * where [x0, y0] is the top-left corner of the viewport and [x1, y1] is the bottom-right corner of the viewport,
     * and return this zoom behavior.
     *
     * The viewport extent affects several functions: the center of the viewport remains fixed during changes by zoom.scaleBy and zoom.scaleTo;
     * the viewport center and dimensions affect the path chosen by d3.interpolateZoom; and the viewport extent is needed to enforce the optional translate extent.
     *
     * @param extent An extent specified as an array of two coordinates.
     */
    extent(extent: [[number, number], [number, number]]): this;
    /**
     * Set the viewport extent to the array of points [[x0, y0], [x1, y1]] returned by the
     * extent accessor function, and return this zoom behavior.
     * The extent accessor function is evaluated for each element.
     *
     * [x0, y0] is the top-left corner of the viewport and [x1, y1] is the bottom-right corner of the viewport.
     *
     * The viewport extent affects several functions: the center of the viewport remains fixed during changes by zoom.scaleBy and zoom.scaleTo;
     * the viewport center and dimensions affect the path chosen by d3.interpolateZoom; and the viewport extent is needed to enforce the optional translate extent.
     *
     * The default is [[0, 0], [width, height]] where width is the client width of the element and height is its client height;
     * for SVG elements, the nearest ancestor SVG element’s width and height is used.
     * In this case, the owner SVG element must have defined width and height attributes rather than (for example) relying on CSS properties or the viewBox attribute;
     * SVG provides no programmatic method for retrieving the initial viewport size. Alternatively, consider using element.getBoundingClientRect.
     * (In Firefox, element.clientWidth and element.clientHeight is zero for SVG elements!)
     *
     * @param extent An extent accessor function which is evaluated for each selected element, being passed the current datum d, with the this context as the current DOM element.
     * The function returns the extent array.
     */
    extent(extent: (this: ZoomRefElement, datum: Datum) => [[number, number], [number, number]]): this;

    /**
     * Return the current scale extent.
     */
    scaleExtent(): [number, number];
    /**
     * Set the scale extent to the specified array of numbers [k0, k1] where k0 is the minimum allowed scale factor and k1 is the maximum allowed scale factor,
     * and return this zoom behavior.
     *
     * The scale extent restricts zooming in and out. It is enforced on interaction and when using zoom.scaleBy, zoom.scaleTo and zoom.translateBy;
     * however, it is not enforced when using zoom.transform to set the transform explicitly.
     *
     * The default scale extent is [0, infinity].
     *
     * If the user tries to zoom by wheeling when already at the corresponding limit of the scale extent, the wheel events will be ignored and not initiate a zoom gesture.
     * This allows the user to scroll down past a zoomable area after zooming in, or to scroll up after zooming out.
     * If you would prefer to always prevent scrolling on wheel input regardless of the scale extent, register a wheel event listener to prevent the browser default behavior
     *
     * @param extent A scale extent array of two numbers representing the scale boundaries.
     */
    scaleExtent(extent: [number, number]): this;

    /**
     * Return the current translate extent.
     */
    translateExtent(): [[number, number], [number, number]];
    /**
     * Set the translate extent to the specified array of points [[x0, y0], [x1, y1]], where [x0, y0] is the top-left corner of the world and [x1, y1]
     * is the bottom-right corner of the world, and return this zoom behavior.
     *
     * The translate extent restricts panning, and may cause translation on zoom out. It is enforced on interaction and when using zoom.scaleBy, zoom.scaleTo and zoom.translateBy;
     * however, it is not enforced when using zoom.transform to set the transform explicitly.
     *
     * The default scale extent is [[-infinity, infinity], [-infinity, infinity]].
     *
     * @param extent A translate extent array, i.e. an array of two arrays, each representing a point.
     */
    translateExtent(extent: [[number, number], [number, number]]): this;

    /**
     * Return the current click distance threshold, which defaults to zero.
     */
    clickDistance(): number;
    /**
     * Set the maximum distance that the mouse can move between mousedown and mouseup that will trigger
     * a subsequent click event. If at any point between mousedown and mouseup the mouse is greater than or equal to
     * distance from its position on mousedown, the click event following mouseup will be suppressed.
     *
     * @param distance The distance threshold between mousedown and mouseup measured in client coordinates (event.clientX and event.clientY).
     * The default is zero.
     */
    clickDistance(distance: number): this;

    /**
     * Return the current tap distance threshold, which defaults to 10.
     */
    tapDistance(): number;
    /**
     * Sets the maximum distance that a double-tap gesture can move between first touchstart and second touchend that will trigger a subsequent double-click event.
     *
     * @param distance The distance threshold between mousedown and mouseup measured in client coordinates (event.clientX and event.clientY).
     * The default is 10.
     */
    tapDistance(distance: number): this;

    /**
     * Get the duration for zoom transitions on double-click and double-tap in milliseconds.
     */
    duration(): number;
    /**
     * Set the duration for zoom transitions on double-click and double-tap to the specified number of milliseconds and returns the zoom behavior.
     *
     * To disable double-click and double-tap transitions, you can remove the zoom behavior’s dblclick event listener after applying the zoom behavior to the selection.
     *
     * @param duration in milliseconds.
     */
    duration(duration: number): this;

    /**
     * Returns the current interpolation factory, which defaults to d3.interpolateZoom to implement smooth zooming.
     */
    interpolate<
        // eslint-disable-next-line @definitelytyped/no-unnecessary-generics
        InterpolationFactory extends (a: ZoomView, b: ZoomView) => (t: number) => ZoomView,
    >(): InterpolationFactory;

    /**
     * Sets the interpolation factory for zoom transitions to the specified function.
     * Use the default d3.interpolateZoom to implement smooth zooming.
     * To apply direct interpolation between two views, try d3.interpolate instead.
     *
     * Each view is defined as an array of three numbers: cx, cy and width. The first two coordinates cx, cy represent the center of the viewport;
     * the last coordinate width represents the size of the viewport.
     *
     * @param interpolatorFactory An interpolator factory to be used to generate interpolators between zooms for transitions.
     */
    interpolate(interpolatorFactory: (a: ZoomView, b: ZoomView) => (t: number) => ZoomView): this;

    /**
     * Return the first currently-assigned listener matching the specified typenames, if any.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after zooming begins [such as mousedown]), zoom (after a change to the zoom  transform [such as mousemove], or
     * end (after an active pointer becomes inactive [such as on mouseup].)
     */
    on(typenames: string): ((this: ZoomRefElement, event: any, d: Datum) => void) | undefined;
    /**
     * Remove the current event listeners for the specified typenames, if any, return the drag behavior.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after zooming begins [such as mousedown]), zoom (after a change to the zoom  transform [such as mousemove], or
     * end (after an active pointer becomes inactive [such as on mouseup].)
     * @param listener Use null to remove the listener.
     */
    on(typenames: string, listener: null): this;
    /**
     * Set the event listener for the specified typenames and return the zoom behavior.
     * If an event listener was already registered for the same type and name,
     * the existing listener is removed before the new listener is added.
     * When a specified event is dispatched, each listener will be invoked with the same context and arguments as selection.on listeners.
     *
     * @param typenames The typenames is a string containing one or more typename separated by whitespace.
     * Each typename is a type, optionally followed by a period (.) and a name, such as "drag.foo"" and "drag.bar";
     * the name allows multiple listeners to be registered for the same type. The type must be one of the following:
     * start (after zooming begins [such as mousedown]), zoom (after a change to the zoom  transform [such as mousemove], or
     * end (after an active pointer becomes inactive [such as on mouseup].)
     * @param listener An event listener function which is evaluated for each selected element,
     * in order, being passed the current event (event) and datum d, with the this context as the current DOM element.
     */
    on(typenames: string, listener: (this: ZoomRefElement, event: any, d: Datum) => void): this;
}

/**
 * Creates a new zoom behavior. The returned behavior, zoom, is both an object and a function,
 * and is typically applied to selected elements via selection.call.
 *
 * The first generic refers to the type of reference element to which the zoom behavior is attached.
 * The second generic refers to the type of the datum of the reference element.
 */
// eslint-disable-next-line @definitelytyped/no-unnecessary-generics
export function zoom<ZoomRefElement extends ZoomedElementBaseType, Datum>(): ZoomBehavior<ZoomRefElement, Datum>;

// --------------------------------------------------------------------------
// Zoom Event
// --------------------------------------------------------------------------

/**
 * A D3 Zoom Event
 *
 * The first generic refers to the type of reference element to which the zoom behavior is attached.
 * The second generic refers to the type of the datum of the reference element.
 */
export interface D3ZoomEvent<ZoomRefElement extends ZoomedElementBaseType, Datum> {
    /**
     * The ZoomBehavior associated with the event
     */
    target: ZoomBehavior<ZoomRefElement, Datum>;
    /**
     * The event type for the zoom event
     */
    type: "start" | "zoom" | "end" | string; // Leave failsafe string type for cases like 'zoom.foo'
    /**
     * The current zoom transform
     */
    transform: ZoomTransform;
    /**
     * The underlying input event, such as mousemove or touchmove.
     */
    sourceEvent: any;
}

// --------------------------------------------------------------------------
// Zoom Transforms
// --------------------------------------------------------------------------

/**
 * A zoom transform
 *
 * The zoom behavior stores the zoom state on the element to which the zoom behavior was applied, not on the zoom behavior itself.
 * This is because the zoom behavior can be applied to many elements simultaneously, and each element can be zoomed independently.
 * The zoom state can change either on user interaction or programmatically via zoom.transform.
 *
 * To retrieve the zoom state, use event.transform on the current zoom event within a zoom event listener (see zoom.on), or use d3.zoomTransform for a given node.
 * The latter is particularly useful for modifying the zoom state programmatically,
 * say to implement buttons for zooming in and out.
 *
 * For details see {@link https://github.com/d3/d3-zoom#zoom-transforms}
 */
export class ZoomTransform {
    /**
     * Returns a transform with scale k and translation (x, y).
     */
    constructor(k: number, x: number, y: number);

    /**
     * The translation amount tx along the x-axis.
     * This property should be considered read-only; instead of mutating a transform,
     * use transform.scale and transform.translate to derive a new transform.
     * Also see zoom.scaleBy, zoom.scaleTo and zoom.translateBy for convenience methods on the zoom behavior.
     */
    readonly x: number;

    /**
     * The translation amount ty along the y-axis
     * This property should be considered read-only; instead of mutating a transform,
     * use transform.scale and transform.translate to derive a new transform.
     * Also see zoom.scaleBy, zoom.scaleTo and zoom.translateBy for convenience methods on the zoom behavior.
     */
    readonly y: number;

    /**
     * The scale factor k.
     * This property should be considered read-only; instead of mutating a transform,
     * use transform.scale and transform.translate to derive a new transform.
     * Also see zoom.scaleBy, zoom.scaleTo and zoom.translateBy for convenience methods on the zoom behavior.
     */
    readonly k: number;

    /**
     * Return the transformation of the specified point which is a two-element array of numbers [x, y].
     * The returned point is equal to [xk + tx, yk + ty].
     *
     * @param point Point coordinates [x, y]
     */
    apply(point: [number, number]): [number, number];

    /**
     * Return the transformation of the specified x-coordinate, xk + tx.
     *
     * @param x Value of x-coordinate.
     */
    applyX(x: number): number;

    /**
     * Return the transformation of the specified y-coordinate, yk + ty.
     *
     * @param y Value of y-coordinate.
     */
    applyY(y: number): number;

    /**
     * Return the inverse transformation of the specified point which is a two-element array of numbers [x, y].
     * The returned point is equal to [(x - tx) / k, (y - ty) / k].
     *
     * @param point Point coordinates [x, y]
     */
    invert(point: [number, number]): [number, number];

    /**
     * Return the inverse transformation of the specified x-coordinate, (x - tx) / k.
     *
     * @param x Value of x-coordinate.
     */
    invertX(x: number): number;

    /**
     * Return the inverse transformation of the specified y-coordinate, (y - ty) / k.
     *
     * @param y Value of y-coordinate.
     */
    invertY(y: number): number;

    /**
     * Returns a copy of the continuous scale x whose domain is transformed.
     * This is implemented by first applying the inverse x-transform on the scale’s range,
     * and then applying the inverse scale to compute the corresponding domain
     *
     * The scale x must use d3.interpolateNumber; do not use continuous.rangeRound as this
     * reduces the accuracy of continuous.invert and can lead to an inaccurate rescaled domain.
     * This method does not modify the input scale x; x thus represents the untransformed scale,
     * while the returned scale represents its transformed view.
     *
     * @param xScale A continuous scale for x-dimension.
     */
    rescaleX<S extends ZoomScale>(xScale: S): S;

    /**
     * Returns a copy of the continuous scale y whose domain is transformed.
     * This is implemented by first applying the inverse y-transform on the scale’s range,
     * and then applying the inverse scale to compute the corresponding domain
     *
     * The scale y must use d3.interpolateNumber; do not use continuous.rangeRound as this
     * reduces the accuracy of continuous.invert and can lead to an inaccurate rescaled domain.
     * This method does not modify the input scale x; x thus represents the untransformed scale,
     * while the returned scale represents its transformed view.
     *
     * @param yScale A continuous scale for y-dimension.
     */
    rescaleY<S extends ZoomScale>(yScale: S): S;

    /**
     * Return a transform whose scale k1 is equal to k0 × k, where k0 is this transform’s scale.
     *
     * @param k A scale factor.
     */
    scale(k: number): ZoomTransform;

    /**
     * Return a string representing the SVG transform corresponding to this transform.
     */
    toString(): string;

    /**
     * Returns a transform whose translation tx1 and ty1 is equal to tx0 + tkx and ty0 + tky,
     * where tx0 and ty0 is this transform’s translation and tk is this transform’s scale.
     *
     * @param x Amount of translation in x-direction.
     * @param y Amount of translation in y-direction.
     */
    translate(x: number, y: number): ZoomTransform;
}

/**
 * Returns the current transform for the specified node. Note that node should typically be a DOM element, and not a selection.
 * (A selection may consist of multiple nodes, in different states, and this function only returns a single transform.) If you have a selection, call selection.node first.
 * In the context of an event listener, the node is typically the element that received the input event (which should be equal to event.transform), "this".
 * Internally, an element’s transform is stored as element.__zoom; however, you should use this method rather than accessing it directly.
 * If the given node has no defined transform, returns the identity transformation.
 * The returned transform represents a two-dimensional transformation matrix
 *
 * For details see {@link https://github.com/d3/d3-zoom#zoom-transforms}
 *
 * @param node An element for which to retrieve its current zoom transform.
 */
export function zoomTransform(node: ZoomedElementBaseType): ZoomTransform;

/**
 * The identity transform, where k = 1, tx = ty = 0.
 */
export const zoomIdentity: ZoomTransform;
